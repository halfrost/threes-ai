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
- **The input twist: keyboard works — until it doesn't; mouse-*drag* always does.**
  Our first read was "synthetic KEYBOARD works, synthetic MOUSE doesn't": arrow keys
  via `osascript key code` moved tiles, while `cliclick` / `CGEventPost` /
  `CGEventPostToPid` / AX `AXPress` never pressed a button. Both halves were half-true
  and it cost hours. The full picture:
  - The app honours synthetic **arrow keys only while its window holds *genuine*
    keyboard first-responder.** The game we first drove had that because a human had
    been playing it. The moment we restarted it ourselves (kill/relaunch, or a
    synthetic menu click), the window came up frontmost but *not* key/first-responder
    — and every arrow key, `osascript` **and** low-level `CGEventPost` to the HID tap
    alike, silently did nothing. No amount of `set frontmost`, `AXRaise`, or clicking
    the title bar restored it.
  - A synthetic **single click** *is* honoured by the menu/game-over **buttons**
    (`PLAY THREES`, `retry`) — the earlier "mouse doesn't work" was about in-game
    swipes, not buttons.
  - And a synthetic **mouse *drag*** — a `CGEvent` mouse-down, a series of
    `LeftMouseDragged` points, mouse-up — registers as a board swipe **regardless of
    focus.** That's the unlock: **drive the whole game by mouse.** Drag from the board
    centre to move; click `retry`/`PLAY THREES` to restart. No keyboard, no relaunch,
    fully hands-off. (The old kill→relaunch→Return loop is dead; a synthetic Return
    never fires PLAY THREES once you're the one who launched the app.)
- **Off-screen windows silently eat clicks.** Three displays with negative origins
  put the window mostly below the main display; `AXUIElement set position` (the one AX
  call that *does* work) moves it back so drag/click coordinates land.
- **The board CAN be read exactly — the "ceiling" was wrong.** The earlier verdict
  ("strong accurate Mac score is gated on exact reading, which the obfuscated plist
  blocks") turned out to be beatable without touching the save file. Two ideas:
  1. **Never glyph-read a high tile.** Colour gives {empty, 1, 2, white≥3} perfectly;
     the *value* of a white tile is unknowable from colour and OCR misreads the
     handwritten font — so don't ask. A merge's value is deterministic, so `apply_move`
     already knows every high tile. Read the screen only to (a) confirm the move landed
     and (b) place the single **spawned** tile, whose value is the `next` we previewed
     (a 1/2/3 by colour). Engine owns the high tiles; the screen owns only the spawn.
  2. **Read only *settled* frames.** Wait until two consecutive colour grids are
     identical before trusting a read — a full board's long merge cascade otherwise
     shows phantom tiles mid-animation (this exact bug cascaded one clean 180-move game
     into garbage before we added the wait).
  With those, `occ_mis` (engine-vs-screen occupancy disagreement) is **0 across a whole
  game**, and the drivers reach a genuine game over — decided the real way, a full
  16-tile board with no legal move, never by a failed input. Result: **30,285, tile
  768.** The residual weakness is the deep endgame: a packed board can develop a
  *value* drift the occupancy check can't see (a 768 read as 384 because the glyph
  library tops out below it) — mitigated by a resync that keeps the engine's high-tile
  values and only re-reads low tiles, but a truly packed high-tile board is the last CV
  frontier here.
- **The board false-ends if you trust a failed input.** Four dropped swipes ≠ game
  over. In Threes the game is over *only* on a full 16-tile board with no mergeable
  pair; with any empty cell a slide is always legal. Decide game-over by that rule on
  the tracked board, and a stuck input becomes "re-read and retry", not a premature
  settlement at 945 points.
- **Signing the leaderboard name — the input wall, cracked.** We first concluded the
  Mac name was an un-settable Game Center nickname. Wrong: game over shows a "SWIPE &
  SIGN YOUR NAME" card with a real text field (default "Threeby"). The catch is the
  same as the arrow keys — `osascript keystroke` and raw keycode CGEvents are ignored
  by the field (no genuine key focus). What *does* land: a CGEvent keyboard event with
  **`CGEventKeyboardSetUnicodeString`** — set the unicode string on the event and post
  it to the HID tap, and the characters appear. So we navigate to the card (swipe until
  a dark-panel probe fires), backspace the default, type `Github halfrost`, **and press
  Return (CGEvent) to COMMIT** — typing alone leaves the name blinking in the edit box
  and never posts (the bug the user caught: "you typed it but didn't submit it"); Return
  flips the edit card to the final settlement card with the name in orange and the
  score. Lesson: when synthetic keycodes are ignored, post the **unicode string**
  directly — and remember the field still needs its **commit** keystroke.
- **Detect "we left the game board", or the driver wanders the menus.** When the game
  ends, the score-reveal / sign / settlement carousel reads (to a board parser) like a
  plausible-ish drifted board, so the driver keeps "playing" and swipes itself deep
  into the menus (looked like it hung on the name screen). Two robust "not a live
  board" signals stop it: a **uniform dark panel** (four spread-out points all dark —
  one point catches a tile's dark monster-mouth and false-fires) and a **whole-board
  occupancy jump** (a real move changes 1–2 cells; a screen flip changes ~14).

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
- On a Metal/iOS-on-Mac app that ignores synthetic input, **a mouse *drag* (with
  intermediate `MouseDragged` points) beats keys** — keys need genuine first-responder
  a synthetic launch never grants; a drag is honoured regardless of focus.
- **Read only settled frames** (two identical consecutive reads) — a mid-animation
  frame of a cascading board looks like phantom tiles and will cascade into garbage.
- Don't OCR what you can *derive*: track high tiles with the engine's deterministic
  merges and read the screen **only for the spawn**; a value you never read can't drift.
- Game-over is a **property of the board** (full + no merge), never "N inputs did
  nothing" — the latter false-ends the game a few moves early, or 200 moves early.
