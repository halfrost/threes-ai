# iOS scoring driver (Phase 4)

Drive the real Threes iOS app with the strong Go agent. iOS has no `adb input`,
so input goes through **WebDriverAgent (WDA)** — the on-device automation server
Appium uses — but we talk to it directly over HTTP, so the driver stays as
self-contained as the others (urllib + the shared OCR, no Appium/Selenium stack).

Loop: WDA `GET /screenshot` → OCR (`android/ocr`) → `moveserver` → WDA
`dragfromtoforduration` swipe → deck-track → repeat; restart on game over.

## Requirements & setup (needs a Mac + Xcode + a real device)
App Store apps do **not** run on the iOS Simulator, so scoring the real app needs
a physical iPhone/iPad.
1. **WebDriverAgent** on the device: open WDA in Xcode (or Appium's copy), set a
   signing team, and run the `WebDriverAgentRunner` test so it launches on the
   device.
2. **Port-forward** WDA to the Mac: `iproxy 8100 8100` (from `libimobiledevice`)
   or via Xcode. Check: `curl http://localhost:8100/status`.
3. **OCR config**: add a `CONFIGS['<model>']` entry to
   `../../android/ocr/devices.py` with the PIXEL geometry, measured from a WDA
   screenshot, and bootstrap exemplars (see `../android/README.md`). The same
   matcher serves all platforms.
4. **Scale**: pass `--scale` = the device's pixel scale (3 for most modern
   iPhones, 2 for SE/older). Screenshots are pixels; WDA touch is points.

## Run
```bash
go run ../../cmd/moveserver -addr :9010 -deckaware &
python driver.py --dry-run                                  # brain only, no device
python driver.py --self-test --record-dir /tmp/it           # FULL flow, no device (engine stands in)
python driver.py --model 'iPhone_14' --scale 3 \
    --player-name 'Github halfrost' --record-dir ../../results/replays/ios
```

## Deliverables (same standard as the web drivers)
Via `deploy/mobile_core` (shared with Android), a scoring run:
- records the **best game** as an `engine/replay.go` replay (`best.json`, plays in
  `web/replay.html`) and its **game-over screenshot** (`best.png`), keeping only the
  highest-scoring game (`deploy/recorder.py` BestKeeper);
- takes the **settlement screenshot** straight from the device (WDA screenshot),
  i.e. the real game-over screen;
- `--player-name` — but note Threes submits to **Game Center under the signed-in
  Apple ID**, so the leaderboard name is the account nickname, not typed in-game;
  `submit_name` only types into an in-game field if you pass `--name-tap "x,y"`.

**`--self-test` runs this entire pipeline offline** (the Python Threes engine
stands in for the phone), so moveserver → play → record → best-keep → settlement is
CI-able with no Mac/device. Verified: an 811-move self-test game recorded a valid
replay that plays in `web/replay.html`.

## Alternative: iOS Safari playing threesjs.io
If you only need a *web* score on iOS, skip the native app: open threesjs.io in
Mobile Safari and use the web DOM driver (`../web`) — Safari can be automated
with WDA too, but the desktop `../web/driver.py` against threesjs.io already
gets the same leaderboard.

## Notes
- WDA coordinates are in points; the driver divides the OCR pixel geometry by
  `--scale`. If swipes miss, check the scale and widen the pitch.
- Deck-aware and the `nextset` handling are identical to the Android driver — the
  brain and OCR are shared; only capture (WDA screenshot) and input (WDA drag)
  differ.
