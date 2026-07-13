# Deployment — score on real Threes (Phase 4)

Play the strong Go agent on live Threes and chase the leaderboards. Every target
shares one brain and one loop; only *capture* and *input* are platform-specific.

```
             read board            ask move             inject move
  web    DOM position / OCR  ─┐                    ┌─  arrow keys (Playwright)
  android  adb screencap ────┤─►  moveserver  ─────┤─  adb input swipe
  ios      WDA screenshot ───┘   (Go, deck-aware)  └─  WDA drag
                                       ▲
              android/ocr  ───────────┘  (screenshot → 4×4 indices + next)
```

- **`common.py`** — the shared core: `MoveClient` (talks to `../cmd/moveserver`),
  `DeckTracker` (deck-aware play on a real device), and the tile index↔value maps.
- **`../cmd/moveserver`** — the Go agent over HTTP: `POST /move
  {board, next|nextset, deck}` → `{move}`.
- **`../android/ocr`** — the exemplar OCR (screenshot → board + next), reused by
  the Android and iOS drivers.

| target | dir | reading | input | needs |
|---|---|---|---|---|
| threesjs.io + DOM clones | [`web/`](web) | DOM tile positions | arrow keys | Playwright |
| play.threesgame.com | [`web/`](web) | canvas → OCR | arrow keys | Playwright + OCR calib |
| Threes Android | [`android/`](android) | adb screencap → OCR | adb input swipe | adb + emulator/phone |
| Threes iOS | [`ios/`](ios) | WDA screenshot → OCR | WDA drag | Mac + Xcode + device |

Start the brain once, then run any driver:
```bash
go run ../cmd/moveserver -addr :9010 -deckaware
python web/driver.py --dry-run        # same --dry-run on every platform
```
See each subdirectory's README for the one-time, target-specific setup.
