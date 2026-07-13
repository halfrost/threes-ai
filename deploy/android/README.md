# Android scoring driver (Phase 4)

Drive the real Threes Android app (on an emulator or a phone) with the strong Go
agent, over ADB: `screencap` → OCR → ask `moveserver` → `input swipe` → repeat.

## Pieces
- `../../android/ocr` — the repo's exemplar OCR: a screenshot → 4×4 tile indices
  + the next-tile set. Reused as-is.
- `../common.py` — moveserver client, `DeckTracker`, tile maps (shared with web/iOS).
- `driver.py` — the ADB loop; swipe geometry is derived from the OCR config.

## One-time setup
1. **ADB + a device**: start the Android emulator (or plug in a phone with USB
   debugging), install Threes, and confirm `adb devices` lists it.
2. **Python deps**: `pip install pillow numpy`.
3. **Device config**: add a `CONFIGS['<model>']` entry to
   `../../android/ocr/devices.py` with the screen size and tile geometry
   (`x0,y0` = first tile's top-left, `w,h` = tile sample size, `dx,dy` = tile
   pitch, `tx,ty,tw,th` = the next-preview rectangle). Grab a screenshot with
   `adb exec-out screencap -p > shot.png` and measure it. The same geometry
   drives both OCR and the swipes.
4. **Exemplars**: the first run OCRs unknown tiles interactively — it shows a
   crop and asks you to type the value, then remembers it under
   `android/ocr/exemplars/<model>/`. Play a few games to fill the set.

## Run
```bash
go run ../../cmd/moveserver -addr :9010 -deckaware &
python driver.py --dry-run                              # check the brain first
python driver.py --model 'Pixel_7_API_34' --serial emulator-5554
# multi-game: pass the new-game button location
python driver.py --model 'Pixel_7_API_34' --games 20 --restart-tap '540,1600'
```

## Notes
- Swipes use `adb shell input swipe` from the board centre; if a swipe doesn't
  register, widen it (increase the pitch in the config) or raise the duration.
- Deck-aware: `DeckTracker` counts each 1/2/3 the OCR reports as the next tile.
  Start from a fresh game so the bag count is correct.
- The OCR's next-preview can be a set (bonus "+"); it is sent to the server as
  `nextset` so the search sees the exact candidates.
