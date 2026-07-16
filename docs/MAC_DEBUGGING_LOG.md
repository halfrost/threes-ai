# Driving native Threes on a Mac — a debugging journal

> The blow-by-blow of getting the **official iOS Threes app, running natively on an
> Apple-Silicon Mac**, to play itself to a real game over, sign a leaderboard name, and
> screenshot the settlement — fully hands-off. This is the *detailed* log (symptom →
> wrong guesses → root cause → fix → lesson); the condensed version lives in
> [`WEB_SCORING_WARSTORIES.md`](WEB_SCORING_WARSTORIES.md) Part 5. It is deliberately
> honest about the dead ends, because on this target the dead ends *were* the work.

The setup: `vo.threes.exclaim`, an iOS app run through Apple's "iPhone/iPad apps on
Mac" runtime; the binary lives in `.../Wrapper/Threes.app`. Everything is drawn on a
Metal surface — no DOM, no accessibility tree for the game, no `localStorage` we could
decode (unlike the web targets). We drive it with `deploy/mac/driver.py`: read the
board off screenshots, ask the Go moveserver for a move, send input, record the game.

The engine we drive with is the deck-aware expectimax moveserver (depth-4). The hard
part was never the AI. It was the six-inch gap between "the AI picked UP" and "the app
actually moved up, and I know it did."

---

## Act 1 — The false game over at 945 points

**Symptom.** The very first full run stopped after 76 moves with `max 96, score 945,
20 desyncs`. The "settlement" screenshot we saved was a board with *empty cells and
obvious legal moves* — clearly not a dead game.

**Wrong guess.** "The app's game-over screen ignores keys, so if 4 keystrokes in a row
don't change the board, the game is over." That was the original driver's rule, and it
sounds reasonable. It's wrong.

**Root cause.** The board read had drifted, so the moveserver was handed a *stale*
board and returned a move that was legal on the stale board but a **no-op on the real
screen**. Four keystrokes changed nothing — not because the game was over, but because
the move was a no-op. We interpreted "input did nothing" as "game over."

**Fix.** Decide game over by the *actual rule*, never by a failed input. In Threes the
game is over only when the board is completely full (16 tiles) with no mergeable pair;
with any empty cell a slide is always legal. So a stuck input became "re-read the board
and retry," not "declare a settlement at 945 points."

**Lesson.** "My input had no effect" and "the game is over" are different propositions.
Never collapse them.

---

## Act 2 — Reading drift, and the glyph trap (45% desync)

**Symptom.** Even after Act 1, the tracked board disagreed with the screen on ~45% of
moves (`desync` counter). The AI was playing half-blind.

**Wrong guess.** "Just OCR every tile each move and trust the screen." We built a
fixed-crop glyph template matcher for the white tiles (`3, 6, 12, 24, 48, …`). It read
a fresh board perfectly (11/11) — and then drifted anyway on real games.

**Root cause.** The handwritten Threes font, cropped to a fixed box and downscaled,
makes the multi-digit tiles **look alike**: `12 / 24 / 48 / 96` collapse toward each
other, and `768` isn't even in the seed library so it gets matched to its nearest
neighbour, `384`. Every uncertain glyph is a chance to write the wrong value into the
tracked board.

**Fix — the key insight of the whole project.** *Never glyph-read a high tile.* A
merge's value is deterministic, so `apply_move` already knows every existing tile's
value exactly. The only genuinely new information on screen after a move is the single
**spawned** tile — and its value is exactly the `next` we previewed *before* the move
(always a 1/2/3, which colour tells us unambiguously: blue=1, red=2, white=3). So:
engine owns the board; the screen is read only to (a) confirm a move landed and (b)
place that one spawn. `desync` went to **0**.

**Lesson.** Don't OCR what you can *derive*. Vision is for the one bit the simulator
can't know (where/what spawned), not for re-reading state you already hold exactly.

---

## Act 3 — The engine-trust cascade (a clean 180-move game turns to garbage)

**Symptom.** With engine-trust reading, a game tracked *perfectly* — `occ_mis=0` — for
~180 moves at max 192… and then, in a few moves, the tracked board exploded into
nonsense (a phantom `768`, spawn-detection finding 6 "new" tiles at once) and the game
died.

**Root cause.** As the board fills, a single move can trigger a long *cascade* of
merges, and the slide animation runs longer than our fixed post-move delay. We were
reading a **mid-animation frame** — tiles caught between cells look like extra tiles.
One bad read corrupted the engine board, and because engine-trust *trusts* itself, the
error cascaded.

**Fix.** Only ever read a **settled** frame: capture repeatedly until two consecutive
colour grids are identical (and none is mid-transition), *then* parse. And when the
occupancy check does show drift, resync from the settled screen — but keep the engine's
high-tile values (re-read only occupancy + low tiles), so recovery can't *re-introduce*
the glyph error it's trying to fix.

**Lesson.** A tracker that trusts itself must be religious about never ingesting a
transient. "Wait for stability" beats "sample faster."

---

## Act 4 — The keyboard dies, and a mouse *drag* saves the day

**Symptom.** Arrow keys (`osascript … key code`) drove the game fine at first — then,
after we restarted the app ourselves, **every arrow key silently stopped working**.
Not `osascript`, not low-level `CGEventPost` to the HID tap, nothing. `set frontmost`,
`AXRaise`, clicking the title bar — none restored it.

**Wrong guess (twice).** First: "synthetic keyboard works, synthetic mouse doesn't"
(the buttons never responded to synthetic *clicks* early on). Both halves were
half-true and cost hours.

**Root cause.** The app honours synthetic **arrow keys only while its window holds
*genuine* keyboard first-responder** — which it had at first *because a human had been
playing it*. The moment we took over (kill/relaunch, or a synthetic menu click), the
window came up frontmost but not key/first-responder, and the OS dropped our synthetic
keys on the floor. There was no synthetic way to grant that focus.

**Fix — the breakthrough.** A synthetic **mouse drag** — a `CGEvent` mouse-down, a
*series* of `LeftMouseDragged` points, then mouse-up — registers as a board swipe
**regardless of focus**. (The earlier "mouse doesn't work" was about single *clicks* on
buttons vs. *drags* on the board — different things.) So we drive the entire game by
mouse: drag from the board centre to move. And menu/game-over **buttons** *do* accept a
synthetic single click. Keyboard was abandoned for gameplay entirely.

**Lesson.** When synthetic keys are ignored, the app is probably gating on genuine
first-responder that you can't fake — but pointer events often flow through a different,
ungated path. Try the drag.

---

## Act 5 — The menu-state maze (why "restart" is hard)

Getting a *fresh* game turned out to be its own project, because the app has a small
state machine and reacts to relaunch in non-obvious ways:

- **Relaunch RESUMES an in-progress game.** `kill -9` + `open` does *not* give you a
  fresh board if a game is mid-play — it drops you right back into it. The start menu
  ("PLAY THREES") only appears if the previous game already **ended**.
- **"PLAY THREES" is a mouse target, not a key.** We spent time mashing Return/Space at
  the menu (an old note claimed Return fired it). It doesn't, post-takeover — but a
  synthetic **click** on the button does.
- **Abandoning a live game needs a confirm.** `retry` on an in-progress board pops an
  **"Are you sure? — END GAME / KEEP PLAYING"** dialog; you must click END GAME, which
  drops you to the start menu, then PLAY THREES.
- **The game-over screen is a carousel.** After a game ends you land on a "signed by"
  name card; swiping scrolls a high-score carousel of *past* games, each with its own
  retry/gamecenter/share. Easy to get lost in.

**Fix.** A small state-machine `restart()` with per-screen detectors (is-fresh-board,
is-sign-card, is-"are-you-sure" [pink END GAME pixel], is-start-menu [all-white deco
board]) that clicks the right button for wherever it finds itself and verifies a fresh
low-tile board appeared. Still the flakiest piece (see Act 11's postscript).

**Lesson.** For a stateful UI, "click the button" is not an action — "detect which
screen I'm on, then click *its* button, then verify the transition" is.

---

## Act 6 — A real 30,285… with a corrupted replay and the wrong name

Before the reading was fully hardened, one game got *lucky on the reads* and played all
the way to a genuine game over: **30,285 points, a 768 tile**, and — crucially — the
app's own settlement screen rendered it, so we captured a real 30k screenshot.

Two stings, though:
- The **replay was corrupted**: the recorder had tracked a diverged board in the
  endgame, so the saved replay said `165`. The *game* was real; our *recording* wasn't.
- The name on the card was **"Helen"** — the Mac's existing account name. At this point
  we still (wrongly) believed the name was an un-settable Game Center nickname.

This game is why we kept going: it proved the app *could* be driven to a strong, real,
screenshotted result — the remaining work was making it repeatable, accurate, and
correctly named.

---

## Act 7 — Focus thieves and the phantom "crashes"

**Symptom.** Runs kept "dying." Sometimes `find_window` threw "no on-screen window";
sometimes the driver just sat at move 0 forever; once a run cascaded to garbage at
move 125.

**Wrong guess.** "The iOS-on-Mac runtime is crashing." We even added crash-report
checks. But `pgrep` often showed the app very much alive.

**Root cause.** Two separate things wearing one disguise:
1. **A background app stole focus and covered the window.** When Lark or Chrome popped
   to the front, our mouse drag landed on *that* window's coordinates, so the game
   silently stopped advancing — while `screencapture -l <windowid>` still returned the
   game's *backing store*, so it *looked* like the game was up but frozen. (Frontmost
   was literally reported as "Lark.")
2. **`screencapture -l` transiently fails** ("could not create image from window") when
   the window id goes momentarily stale (space switch, another app raising over it).

**Fix.** (1) Re-activate Threes *before every drag*, so a drag always lands on the game
even if something popped over it. (2) Wrap the capture in a retry that re-resolves the
window id and nudges the window forward. The "crashes" vanished.

**Lesson.** On a shared desktop, an automated GUI driver is fighting every notification
and chat ping for the pointer. Assume the window is *not* yours and re-assert it
constantly. And a screenshot succeeding is not proof the window is interactive.

---

## Act 8 — The endgame drift you can't see (768 read as 384)

**Symptom.** High-scoring games (those that reach 384/768) end with the tracked score
*far below* the real one — e.g. the app shows **7,776** but the replay records **2,283**.
Short games (max ≤192) track perfectly (app 3,390 vs replay 3,381).

**Root cause.** Two compounding things, both about high tiles:
- The template library tops out below 768, so any glyph read of a 768 returns **384**.
- Our occupancy-based resync only checks *which cells are filled*, not their *values* —
  so a `384`-where-`768`-should-be passes the occupancy check invisibly, and the
  "stuck-direction escape" (Act 10) does a full glyph re-read that bakes the error in.

**Status — honest.** This is the one *unsolved* piece. The settlement screenshot and
the signed name are always real (they're the app's own pixels); it's the *replay* that
under-counts on high-score games. Games that stay short track exactly. A perfect
*high-score* replay needs value-accurate reads of a packed board of big tiles — the
last real CV problem here.

**Lesson.** An integrity check that only covers *structure* (occupancy) will happily
pass *value* corruption. If values can drift, check values.

---

## Act 9 — The false end at move 27 (one dark pixel)

**Symptom.** After adding game-over detection, a game false-ended at move 27 on a board
that plainly had empty cells.

**Root cause.** The "are we on the sign-your-name card?" detector sampled a **single
pixel** for the card's big dark panel. On a live board, that pixel landed on a tile's
dark **"monster mouth"** (the little teeth at a tile's base), which is dark enough to
look like the panel.

**Fix.** Require a *uniform* dark area: **four** spread-out points (which map to four
different board cells) all dark at once. A tile mouth darkens one; only the real panel
darkens all four.

**Lesson.** A one-pixel classifier will find a one-pixel doppelgänger. Sample an area,
or several disjoint points, for anything you're using as a mode switch.

---

## Act 10 — The stuck direction, and the "it hung on the name screen" bug

Two user-spotted issues, one root.

**"It kept swiping right and nothing moved."** When the tracked board drifts, the
moveserver keeps choosing a direction that's legal on the *drifted* board but a no-op on
the *real* one — forever. **Fix (user's suggestion):** if the requested direction won't
move the screen after a few tries, *try the other directions*; whichever actually moves
the board wins, then do a full re-read to recover.

**"It looked stuck on the name-entry screen."** When the game ends, the score-reveal /
sign / settlement carousel reads — to a board parser — like a plausible *drifted* board,
so the driver "kept playing" and swiped itself deep into the menus. **Fix:** two robust
"we left the game board" signals stop it: the uniform dark panel (Act 9) *and* a
**whole-board occupancy jump** (a real move changes 1–2 cells; flipping to a menu
screen changes ~14). Above that threshold ⇒ the game is over, hand off to the signer.

**Lesson.** A parser that always returns *something* will happily parse the wrong
screen. Give it an explicit "this isn't my screen" signal.

---

## Act 11 — The name: typed, but never submitted

**The crack.** The Mac game-over shows a real **"SWIPE & SIGN YOUR NAME"** text field
(default "Threeby"). We'd assumed the name was an un-settable Game Center nickname —
wrong, there's an in-app field. But the same focus wall applied: `osascript keystroke`
and raw keycodes were ignored by it. What *did* land: a `CGEvent` keyboard event with
**`CGEventKeyboardSetUnicodeString`** — set the unicode string on the event, post it to
the HID tap, and the characters appear. So: navigate to the card (dark-panel probe),
backspace the default, type `Github halfrost`.

**The bug the user caught.** Typing filled the box — but the name never *posted*. It sat
in the edit field with the cursor still blinking; our "settlement" screenshot was that
mid-edit screen. **Fix:** press **Return (CGEvent keycode 36)** to commit. Return flips
the edit card to the final settlement card — name in **orange, no cursor**, with
retry/gamecenter/share and the score. Verified end-to-end: app **9,117**, name posted
"Github halfrost."

**Lesson.** Filling a text field is not submitting it. A form needs its commit action,
and "it looks right on screen" (a name in a box) is not "it's saved."

---

## The final flow (what actually works, hands-off)

1. `restart()` → a fresh board (mouse clicks through whatever menu state we're in).
2. Loop: read the **settled** board → ask the moveserver → **mouse-drag** the move →
   confirm the colour grid changed → update the **engine** board + place the one spawn.
   If a direction won't move, **switch directions**; if the whole board flips, we've
   **left the game** → stop.
3. Game over → navigate to the sign card → **CGEvent-type** the name → **Return** to
   commit → screenshot the committed settlement card.
4. Record the replay; keep the best.

## Scorecard

| game | app score | max | replay (tracked) | name | note |
|---|---:|---:|---:|---|---|
| 30,285 | 30,285 | 768 | corrupted (165) | Helen | real settlement, pre-fixes |
| 9,117 | 9,117 | 384 | 2,595 (drift) | **Github halfrost** ✓ committed | best signed |
| 7,776 | 7,776 | 384 | 2,283 (drift) | Github halfrost ✓ | signed |
| 3,390 | 3,390 | 192 | **3,381 (occ_mis=0)** | Github halfrost ✓ | best *clean* replay |

Signed settlement shots + replays under `results/replays/mac/` (gitignored).

## The five lessons, distilled

1. **"Input had no effect" ≠ "game over."** Decide terminal state by the game's real
   rule, on a board you trust.
2. **Don't OCR what you can derive.** Track state in the simulator; read the screen only
   for the one thing it can't know (the spawn). A value you never read can't drift.
3. **Only ingest settled frames.** A self-trusting tracker dies on one mid-animation
   read.
4. **Pointer events often flow where synthetic keys are gated.** A mouse *drag* beat a
   dead keyboard; a *click* commits a form the keyboard couldn't reach.
5. **Filling ≠ submitting; occupancy ≠ value; one pixel ≠ a mode.** Every "it looks
   right" hid a missing commit, an unchecked value, or a lookalike pixel.
