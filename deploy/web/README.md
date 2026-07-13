# Web scoring driver (Phase 4)

Automate a live web Threes (threesjs.io, play.threesgame.com) with the strong Go
agent: read the board from the page → ask the Go `moveserver` for the best move →
inject it → loop, restarting on game over.

## Pieces
- `../../cmd/moveserver` — Go HTTP endpoint wrapping the strong agent
  (`ExpectSearchBB`, deck-aware). `POST /move {board(values), next, deck}` → `{move}`.
- `driver.py` — Playwright browser loop + a `DeckTracker` (counts tiles to play
  deck-aware on the real site). The **site-specific** `read_board` / `inject_move`
  / `restart` are stubbed with TODOs.

## Run
```bash
# 1) start the agent server
go run ../../cmd/moveserver -addr :9010 -depthcap 5 -deckaware

# 2) sanity-check the server without a browser
python driver.py --dry-run

# 3) full run (after wiring read_board for the site)
pip install -r requirements.txt && playwright install chromium
python driver.py --url https://threesjs.io/
```

### macOS build note (`missing LC_UUID` / `Killed: 9`)
On recent macOS (Sequoia+/Tahoe) the Go 1.21 *internal* linker can emit a binary
without an `LC_UUID`, which the stricter dyld refuses to run
(`dyld: missing LC_UUID load command`). Upgrading to Go 1.22+ fixes this; if you
must stay on 1.21, build with the external linker and ad-hoc sign it:
```bash
go build -ldflags=-linkmode=external -o ../../bin/moveserver ../../cmd/moveserver
codesign -s - -f ../../bin/moveserver      # avoids the kernel's "Killed: 9"
../../bin/moveserver -addr :9010 -depthcap 5 -deckaware
```
(Linux — including the cloud boxes — is unaffected; plain `go run`/`go build` works there.)

## Wiring `read_board` (the one site-specific step)
- **threesjs.io / open JS clones — JS-state hook (preferred):** run
  `playwright codegen https://threesjs.io/`, inspect the page for the board state
  (a JS global, a framework store, or `data-*` tile attributes), then read it with
  `page.evaluate(...)`. Exact and robust.
- **play.threesgame.com / canvas — OCR:** the board is a `<canvas>` with no
  accessible state; screenshot the board region and classify tiles by template
  match (reuse `android/ocr`'s exemplar matcher). Detect the game-over overlay.

## Notes
- Deck-aware on the real site relies on `DeckTracker` counting every 1/2/3 as it
  appears (reset each 12-tile bag). Start tracking from a fresh game for accuracy.
- Bonus "+" previews: send `next <= 0`; the server averages over the bonus range.
- Automating leaderboards may bump into a site's ToS — this is a research/hobby
  tool; use responsibly.
