# Web scoring driver (Phase 4)

Automate a live web Threes (threesjs.io, play.threesgame.com) with the strong Go
agent: read the board from the page → ask the Go `moveserver` for the best move →
press the arrow key → loop, restarting on game over. Deck-aware via `DeckTracker`.

## Pieces
- `../../cmd/moveserver` — Go HTTP endpoint wrapping the strong agent
  (`ExpectSearchBB`, deck-aware). `POST /move {board(values), next|nextset, deck}` → `{move}`.
- `../common.py` — shared core (moveserver client, `DeckTracker`, tile maps),
  reused by the Android and iOS drivers too.
- `driver.py` — Playwright loop. Reads the board by mapping each numbered tile's
  on-screen position into the board container's 4×4 rectangle (selector-tolerant,
  handles empty cells). Injects arrow keys.
- `probe.py` — run once against the live page to discover the three selectors.

## Run
```bash
# 1) start the brain
go run ../../cmd/moveserver -addr :9010 -depthcap 5 -deckaware

# 2) sanity-check it without a browser
python driver.py --dry-run

# 3) discover the live page's selectors
pip install -r requirements.txt && playwright install chromium
python probe.py --url https://threesjs.io/       # prints a --board-selector suggestion

# 4) play (fill in the selectors probe printed)
python driver.py --site threesjs --url https://threesjs.io/ \
    --board-selector '.board' --next-selector '.next' --gameover-selector '.game-over'
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

## threesjs.io is Unity WebGL — use `threesjs_driver.py`
It turned out threesjs.io renders the board with **Unity WebGL** (a `<canvas>`,
no DOM tiles), so the generic DOM `driver.py` doesn't apply to it. Use the
dedicated, verified `threesjs_driver.py`, which screenshots the canvas and reads
tiles by colour+OCR, then presses arrow keys. First do the one-time environment
setup (corporate-proxy CA + system Chrome):
```bash
bash setup_env.sh                     # keychain CA -> ~/.threes-ca.pem, deps, system Chrome
go run ../../cmd/moveserver -addr :9010 -deckaware &
# the agent plays through the one-time tutorial itself; the profile saves it so
# later runs start straight in free play.
SSL_CERT_FILE=~/.threes-ca.pem python threesjs_driver.py --user-data-dir ~/.threes-profile
# grind games, submit under a leaderboard name, and keep the best game's replay:
SSL_CERT_FILE=~/.threes-ca.pem python threesjs_driver.py --user-data-dir ~/.threes-profile \
    --games 100 --player-name "Github halfrost" --record-dir ../../results/replays/threesjs
```

`--record-dir` keeps only the single highest-scoring game (via `../recorder.py`,
shared with the Android/iOS drivers): `best.json` (a replay in the exact
`engine/replay.go` schema — plays directly in `web/replay.html`) and `best.png`
(the game-over settlement screenshot). It's overwritten only when a game beats
the best score so far; the score compared is the authoritative "Your score: N"
read off the game-over screen. Replay it with:
`web/replay.html?replay=<path-to-best.json>` (served over http).
Verified live (headless): launches the system Chrome, dismisses the portal loader
(`none_loadding()`), collapses the sidebar, starts the game, **auto-clears the
first-time tutorial**, then plays free games — reading the board and the next-tile
preview cleanly (1=red, 2=blue, empty=teal, >=3 via OCR) and moving with arrow
keys until game over. Unity keeps tutorial completion in IndexedDB, so the
persistent `--user-data-dir` means only the first run spends moves on it.

## How board reading works (two strategies)
- **threesjs.io / DOM clones (`--site threesjs`, exact):** tiles are DOM elements.
  `probe.py` finds every numbered tile and the smallest element that bounds them
  all — that ancestor is the board container. The driver then reads the
  container's rectangle each step and assigns each tile to `(row,col)` by where
  its centre falls, so it works without knowing class names and handles empty
  cells. Selectors are only needed to *locate* the container / next / game-over;
  pass them with `--board-selector` etc.
- **play.threesgame.com / WebGL (`threesgame_driver.py` + `threesgame_supervisor.py`):**
  no OCR and no canvas capture — the game persists its live board to
  `localStorage["com.underscorediscovery/Threes/slot.0"]` every move (haxe-serialized
  `Grid0..15` / `NextValue` / `NumMoves` / `InProgress`), read browser-side over CDP
  `DOMStorage`. See below.

## play.threesgame.com — `threesgame_supervisor.py` (localStorage + watchdog)
The official web is a WebGL `<canvas>` with no DOM, but it saves the exact live game
to `localStorage` slot.0, so we decode that instead of reading pixels:
```bash
go run ../../cmd/moveserver -addr :9053 -deckaware &      # (macOS: see build note above)
SSL_CERT_FILE=~/.threes-ca.pem python threesgame_supervisor.py \
    --server http://127.0.0.1:9053 --games 1 \
    --record-dir ../../results/replays/threesgame
```
- `threesgame_driver.py` plays ONE resumable game: seeds the tutorial-skip value
  (`threesgame_skip_tutorial.json`) only when slot.0 is absent, presses Space, then
  each move reads+decodes slot.0, asks the moveserver, presses the arrow, waits for
  the move to register **and the spawned tile to settle**, and appends the ply to a
  JSONL log. Game over = moveserver returns -1 (no legal move).
  - **Orientation gotcha:** `Grid0..3` is the *bottom* screen row. Read rows
    bottom-to-top, else the board is vertically flipped and UP/DOWN invert — moveserver
    then returns a move that's a no-op in the real game and the run gets stuck.
- `threesgame_supervisor.py` exists because automating this animating WebGL page
  intermittently **wedges** the Chrome↔Playwright channel (an in-flight keypress/read
  blocks forever; page/CDP timeouts and SIGALRM can't interrupt the sync greenlet). It
  runs the driver on a persistent profile and, when the JSONL heartbeat stalls, SIGKILLs
  and relaunches — the game resumed itself from slot.0, so play continues. The full
  replay is assembled from the JSONL across restarts. Until 2 moves are safely banked
  it wipes and starts fresh (a game wedged at 0 moves reloads into a non-interactive
  limbo). The settlement screenshot reads back black (WebGL), so a clean settlement
  card is rendered from the replay's terminal board instead.

## Notes
- Deck-aware relies on `DeckTracker` counting every 1/2/3 as it appears (resets
  each 12-tile bag). Start from a fresh game for accuracy. Bonus "+" previews →
  the server models the range; an exact OCR next set can be sent as `nextset`.
- Automating leaderboards may bump into a site's ToS — this is a research/hobby
  tool; use responsibly.
