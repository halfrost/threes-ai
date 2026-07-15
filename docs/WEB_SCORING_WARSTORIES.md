# Web scoring war stories — driving live Threes with the expectimax agent

Notes-for-the-blog on everything that fought back while wiring the Go
deck-aware expectimax (`cmd/moveserver`) into the two live web versions of Threes:
**threesjs.io** (Unity WebGL) and **play.threesgame.com** (the official WebGL
demo). Kept in the words/level of detail a post can lift directly. Two themes:
(1) *how do you even read the board*, and (2) *how do you keep a wedge-prone WebGL
page playing to the end*.

---

## Part 1 — How do you read the board? (every method we tried)

The agent needs, each move: the 4×4 board (tile values), the next tile, and
whether the game is over. On a native app you'd screenshot + OCR. On the web it
turned into a ladder of increasingly-invasive methods, each defeated by something.

1. **DOM tiles (the easy case that didn't apply).** The generic `driver.py`
   assumes tiles are DOM elements: find every numbered node, take the smallest
   ancestor that bounds them all as the board container, and bucket each tile into
   `(row,col)` by where its centre falls. Selector-tolerant, handles empty cells,
   exact. **Worked for DOM clones; both real sites render to a `<canvas>`, so there
   are no tile nodes to read.** Dead end for the real targets.

2. **Canvas screenshot + colour classifier (threesjs).** Screenshot the board
   region, sample each of the 16 cell centres, classify by colour: 1 = blue,
   2 = red, empty = teal, ≥3 = white → OCR the number. Works, but fragile:
   - white ≥3 tiles were read as empty (colour guard too loose),
   - a pink "24" pulled the red mean and misread,
   - multi-digit tiles failed OCR intermittently,
   - and a value↔index conversion bug double-mapped tiles.
   Every misread corrupts the board → the agent plays a move that's wrong for the
   *real* board → the tracked state desyncs and the score is garbage.

3. **Engine-in-the-loop (the fix for OCR fragility).** Stop trusting vision for
   the running board. OCR only the *initial* board + the *next-tile preview* + the
   *spawn position* — all of which are **low tiles** (1/2/3) that OCR reads
   reliably — and then track the true board ourselves by applying each move with
   the Threes engine (`rl/threes_env.apply_move`). High tiles (48, 96, 384…) are
   never OCR'd; they're derived. This made threesjs solid: the per-step score and
   the replay stay exact even when the canvas is briefly unreadable. **This is the
   threesjs.io approach that shipped (9,993).**

4. **Canvas capture for the official site → the stall.** For play.threesgame.com
   we tried the same screenshot approach and hit a wall: **repeatedly capturing the
   continuously-animating WebGL canvas stalls the renderer.** `page.screenshot`
   *and* a JS `canvas.toDataURL` both stall after ~20–100 grabs, at
   `device_scale_factor` 1 and 3, headless and headed. A synchronous `toDataURL`
   can't be interrupted (a CDP timeout does nothing), and to make it worse the
   readback came back **black** until we injected a `preserveDrawingBuffer` patch.
   Capturing the board every move was simply not viable here.

5. **Read the game's own saved state (the winning idea).** The official game
   persists the *live* game to `localStorage["com.underscorediscovery/Threes/
   slot.0"]` every move. Decoding it gives the **exact** board — every high tile —
   with no OCR and no canvas capture at all. The value is haxe-serialized:
   strings are `y<len>:<url-encoded-base64>` (also cached in order), and `R<n>`
   references the n-th cached string; keys/values alternate. Out of it fall
   `Grid0..15`, `NextValue`, `NumMoves`, `InProgress`. We wrote a ~20-line decoder
   and suddenly had a pixel-perfect board for free. **This is the play.threesgame.com
   approach that shipped (23,634).**

6. **…but reading it through `page.evaluate` re-hit the stall.** First cut read
   slot.0 with `page.evaluate(() => localStorage.getItem(k))`. That runs on the
   renderer's JS thread — the same thread the WebGL loop can peg — and
   `page.evaluate` has **no timeout**, so when the renderer stalled the read hung
   *forever*. Same bug, different door.

7. **Read localStorage from the browser process (CDP DOMStorage).** Switch to CDP
   `DOMStorage.getDOMStorageItems`, which queries the browser process's storage
   service directly and **doesn't execute page JS**, so it survives a pegged
   renderer. Gotcha: **don't call `DOMStorage.enable`** — enabling subscribes you
   to a `domStorageItemUpdated` event for every write, and this game writes
   localStorage constantly, which floods and wedges the CDP pipe. `getDOMStorageItems`
   works fine without `enable`. This is the final board-read path.

**Score-line, in order:** DOM tiles → canvas colour+OCR → engine-in-the-loop →
(canvas capture: dead) → localStorage via page.evaluate → localStorage via CDP
DOMStorage. Six methods; the last two are what ship.

---

## Part 2 — Keeping a wedge-prone page alive: the watchdog, step by step

Even with board reads solved, play.threesgame.com **intermittently wedges** the
Chrome↔Playwright channel: some in-flight call — a keypress, a read — blocks
forever. It can strike at move 3 or move 60, at startup or mid-game. The journey to
a supervisor that survives it:

1. **First, prove it's uninterruptible.** Confirmed the hang by sampling the
   process: the main thread sits in a greenlet `g_switch → kevent`, i.e. the sync
   Playwright dispatcher waiting on a browser reply that never comes. Then ruled out
   every in-process rescue:
   - `page.set_default_timeout` / action timeouts — don't cover `evaluate` and
     don't fire against a stuck greenlet.
   - CDP call timeouts — the browser side is what's stuck.
   - **`SIGALRM`** — tested directly (fire an alarm during a 60 s
     `wait_for_timeout`): PEP 475 should surface `EINTR` as an exception, but
     greenlet's event loop swallows it and the call runs to completion. So a signal
     can't interrupt it either.
   Conclusion: **the only reliable interrupt is killing the whole process.**

2. **So make the kill recoverable.** For "kill and restart" to work, the game
   state has to live *outside* the process. It does: the game persists to
   localStorage slot.0. Verified the linchpin experimentally — **play 12 moves,
   close the browser, relaunch the same persistent profile: it resumes the exact
   in-progress board and the next keypress advances it.** (Later also verified a
   *hard SIGKILL* — not a clean close — resumes fine too, so a wedged browser is
   safe to kill.) Resume works ⇒ a watchdog is viable.

3. **Two processes, because you can't watchdog yourself.** A sync-Playwright script
   can't watch its own hung greenlet. So split it:
   - **inner** (`threesgame_driver.py`) plays *one* game on a persistent profile
     and appends every confirmed move to a JSONL log (the log's mtime is the
     heartbeat). Game over = moveserver returns −1.
   - **supervisor** (`threesgame_supervisor.py`) runs the inner in its own process
     group; when the JSONL heartbeat stalls past a timeout it `SIGKILL`s the group
     (plus any Chrome on that profile) and relaunches. The relaunched inner resumes
     from slot.0 and keeps appending. On a clean exit-0 (real game over) the
     supervisor **assembles the whole replay from the JSONL** across all restarts.
   The 23,634 game took **47 relaunches through 22 wedges**; 11/407 replay steps
   show a one-ply seam where a move landed just before a kill.

4. **Bug found by the watchdog #1 — the 0-move limbo.** A game wedged at *0 moves*
   (right after the intro, before the first move banks) reloads into a state that
   accepts localStorage reads but ignores keystrokes — resume is stuck forever.
   Fix: until ≥2 moves are safely banked, treat every stall as **wipe and start
   fresh** (a 0-move restart loses nothing); after that, resume.

5. **Bug found by the watchdog #2 — the board was upside-down.** The real
   head-scratcher. Runs kept getting *permanently* stuck partway in: moveserver
   returned a move, we pressed it, and `NumMoves` never incremented. Diagnosed by
   **diffing engine legality against the game**: for the stuck board the engine said
   `UP` legal / `DOWN` illegal, but the game accepted `DOWN` and rejected `UP` —
   exactly inverted on the vertical axis, `LEFT`/`RIGHT` agreeing. Cause:
   **`Grid0..3` in slot.0 is the *bottom* screen row, not the top.** We'd been
   feeding moveserver a vertically-flipped board. Most of the time both vertical
   directions are legal so play looked fine (it was just a mirror of the intended
   line), but the moment a board had "engine-UP legal, game-UP a no-op" the run
   stalled. Fix is one line — read rows bottom-to-top — and it also makes the
   recorded replay correctly oriented. Flipping the read made engine legality match
   the game exactly. (Earlier a "multi-direction fallback" had been masking this by
   trying other keys when the best was a no-op — which also risked double-moves.)

6. **Bug found by the watchdog #3 — the spawn lands a beat late.** After a move,
   slot.0's `NumMoves` increments *before* the newly spawned tile is written. Read
   too eagerly and you hand moveserver a board missing one tile; it returns a move
   that's a no-op on the real board and the run "gets stuck". Fix: after a move
   registers, keep reading until the board is **stable across two reads** (spawn
   settled) before asking for the next move.

7. **Bug found by the watchdog #4 — resume needs a beat to become interactive.**
   A freshly loaded (esp. resumed) game accepts localStorage reads immediately but
   ignores keystrokes for ~a second while it finishes rendering. Pressing too early
   is a silent no-op that stranded every resume on its first move. Fix: a settle
   wait before the first post-load move.

With all four fixed, plies grow monotonically across restarts and the game reaches
a genuine game over.

---

## Part 3 — Screenshotting the score-settlement screen

Both sites end on a score screen; capturing it had its own traps.

- **threesjs.io (Unity).** The Unity canvas screenshots normally, and the game-over
  screen auto-shows `Your score: N` (OCR'd it and it matched the engine score
  exactly, desync 0). The only trap: the *timing* — wait for the "Out of moves!"
  page to render before grabbing, else you screenshot the last board frame.

- **play.threesgame.com (WebGL).** Two traps stacked:
  1. **Black readback.** The WebGL context clears its drawing buffer after
     compositing, so screenshots read back black. Fix: inject, *before* the page's
     scripts run, a `getContext` patch that forces `preserveDrawingBuffer:true`.
     A single grab is then correct (repeated grabs still stall — but one is enough).
  2. **The reveal only arms on a *live* game over.** The end screen shows
     "Out of moves! / MOVE TO SEE YOUR SCORE"; a move then flips every tile to its
     point value and tallies the total (`+19,683` for the 768, etc.) — exactly like
     the app. But this only responds at a **live** game over. On a *reloaded*
     game-over state, no arrow key / mouse swipe / touch swipe does anything (we
     tried all three). So the driver triggers the reveal *in the same session* the
     moment moveserver returns −1, then screenshots the `23,634` settlement.
  For a while we even suspected the web demo just withheld the score to push app
  downloads (those App Store / Google Play badges sit right under the board) — it
  doesn't; it's purely the live-vs-reload thing.

---

## Part 4 — Mobile (Android app + iOS app)

The native apps reuse the exact same brain and recorder; only capture and input
change. Notes/gotchas:

- **One core, two transports.** `deploy/mobile_core.py` holds the whole loop
  (read → moveserver → swipe → record → best-keep → settlement shot). Android's
  driver is a thin `AdbDevice` (`adb exec-out screencap` to read, `adb shell input
  swipe` to move); iOS's is a thin `WdaDevice` talking to **WebDriverAgent** over
  HTTP (`GET /screenshot`, `dragfromtoforduration`). No Appium/Selenium stack —
  just urllib + the shared exemplar OCR.
- **Read the whole board via OCR here, not partial-OCR-plus-engine.** The web
  threesgame path tracks the board with the engine because its canvas is hostile;
  the apps render clean tiles, so the exemplar OCR (`android/ocr`) reads all 16
  cells (incl. high tiles) reliably, and reading each step naturally hands the
  recorder the board *before* the move. Simpler, and no orientation surprises.
- **iOS units bite you.** WDA screenshots are in **pixels**, but WDA touch is in
  **points** — divide the OCR geometry by the device `--scale` (3 on modern
  iPhones, 2 on SE/older) or every swipe lands in the wrong place.
- **The leaderboard name is the OS account, not an in-game field.** Threes submits
  scores to **Google Play Games** (Android) / **Game Center** (iOS) under the
  signed-in account. So "Github halfrost" is the *device account nickname*, not
  something the driver types; `submit_name` only types into an in-game field if you
  pass `--name-tap "x,y"`. Easy to assume otherwise and build a name-entry step
  that never fires.
- **You can't test the real apps in CI.** No `adb`/emulator in the sandbox, and
  **App Store iOS builds don't run on the Simulator** (wrong arch) — real iOS needs
  a physical device + WebDriverAgent. So the deliverable is an **`EngineDevice`**:
  the Python Threes engine implements the same `Device` interface (`read`/`swipe`/
  `screenshot_png`), and `--self-test` runs the entire scoring pipeline offline.
  It caught real wiring bugs and proves the replay/best-keeper/settlement path end
  to end (an 811-move self-test game played back cleanly in `web/replay.html`)
  without any hardware.
- **Swipe geometry is derived from the OCR config** — one `CONFIGS['<model>']`
  entry (tile origin/pitch) drives both reading and input. If a swipe doesn't
  register, widen the pitch or raise the duration rather than hand-tuning two sets
  of coordinates.

## Part 5 — The native Mac app (iOS Threes on Apple Silicon)

The official **paid Threes** runs natively on Apple-Silicon Macs ("iPhone/iPad
apps on Mac", `~/Library/Containers/vo.threes.exclaim`, the binary lives in a
`.../Wrapper/Threes.app`). `deploy/mac/driver.py` drives it. A pile of surprises:

- **Capture: screenshot the window by ID.** `screencapture -l<windowID>` (window
  id from CoreGraphics `CGWindowListCopyWindowInfo`, permission-free) grabs the
  window's backing store even when it's partly off-screen. System Events' `size of
  window 1` returns a bogus height for these windows, so don't use it.
- **Synthetic KEYBOARD works; synthetic MOUSE does not.** Arrow keys sent via
  `osascript ... key code` move tiles. But *nothing* clicks the on-screen buttons:
  `cliclick`, raw Quartz `CGEventPost`, `CGEventPostToPid`, and AX `AXPress` all
  fail — the buttons aren't even in the accessibility tree (drawn on a Metal
  surface). So the game-over **"retry" button is untappable by automation.**
  (Verified the cursor was dead-on the button and the click still did nothing.)
- **…so restart the game with the keyboard, not the mouse.** Kill the process →
  `open -b` relaunches to the **start menu** → the **Return** key fires
  "PLAY THREES" (Space does *not*; and an Escape beforehand breaks it). That's a
  no-mouse full-auto loop: kill → relaunch → Return → play → game over → repeat.
- **Off-screen windows silently eat clicks anyway.** Three displays with negative
  origins meant the window sat mostly below the main display; even correct global
  coords landed off-screen. `AXUIElement set position` (this one AX call *does*
  work) moves it back on-screen.
- **The board can't be read exactly — the ceiling.** Colour reads {empty, 1=blue,
  2=red, white≥3} perfectly, but a **white tile's value (3 vs 6 vs 12…) is
  unknowable from colour**, and tesseract misreads the handwritten font (a "3" as
  "2"). Tracking high tiles with the engine from a fresh start drifts (≈11 bad
  cells over 130 moves), which corrupts the recorded score and makes game-over fire
  early. The exact board *is* in the app's plist (`Grid0..15`, like the web
  slot.0) — but it's deliberately **obfuscated** (each cell a `(value,id)` string
  like `"GU7"`, `"<IEJ:"`), and cfprefsd caches it, so per-move exact reads are out
  without reversing the format. Net: the full-auto plumbing (restart, keyboard
  play, replay recording, settlement screenshot) all works; a *strong, accurate*
  Mac score is gated on exact board reading, which the obfuscated save blocks.

## One-line lessons

- On a `<canvas>` game, look for a **saved-state side channel** (localStorage /
  IndexedDB) before reaching for OCR — it's often exact and free.
- Read that side channel from the **browser process (CDP DOMStorage)**, not
  `page.evaluate`, so a pegged renderer can't hang you; and don't `enable` the
  domain (event flood).
- If a page can wedge the automation channel uninterruptibly, stop trying to
  interrupt — **persist state, kill the process, resume.**
- Trust the **engine as the source of truth** for the running board; use vision /
  saved-state only to seed and to detect terminal.
- When a "legal" move is a no-op in the real game, suspect a **board-orientation
  mismatch** — diff your engine's legality against the game's acceptance to catch it.
- WebGL screenshots need `preserveDrawingBuffer`; some end screens only respond to
  input **live**, not on reload.
