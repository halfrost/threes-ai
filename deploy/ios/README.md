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
python driver.py --dry-run                        # check the brain first
python driver.py --model 'iPhone_14' --scale 3
```

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
