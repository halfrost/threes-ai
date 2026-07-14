"""Play ONE resumable game of the OFFICIAL Threes (play.threesgame.com).

The board is read straight from the game's own saved state, NOT from pixels:
play.threesgame.com (Threes.min.js) persists the live game to localStorage
`com.underscorediscovery/Threes/slot.0` every move — a small haxe-serialized
object holding Grid0..Grid15 (the 16 cells, as printed values), NextValue,
NumMoves and InProgress. Decoding that gives the EXACT board (high tiles and all)
with no OCR and no canvas capture.

Why a supervisor (threesgame_supervisor.py) drives this: repeatedly automating
this continuously-animating WebGL page intermittently wedges the Chrome<->driver
channel — any in-flight Playwright/CDP call (a keypress, a read) then blocks
forever, and neither page timeouts, CDP timeouts, nor SIGALRM can interrupt the
sync greenlet. The ONLY reliable recovery is to kill the whole process. So this
script plays with a PERSISTENT profile and appends every confirmed move to a
JSONL log; when the supervisor kills a wedged run it relaunches us, and because
the game persisted itself to slot.0 (verified: a fresh load resumes the exact
in-progress board, no Space needed) we continue seamlessly, appending to the same
log. The supervisor assembles the full replay from that log on game over.

Flow: launch persistent profile -> if slot.0 has an in-progress game, RESUME it
(do not clobber it / do not press Space); else inject the tutorial-skip value and
press Space -> each move: read+decode slot.0 -> ask the Go moveserver -> press the
arrow -> confirm NumMoves incremented -> append ply to the JSONL log. On game over
write the settlement screenshot, append a terminal line, exit 0.

Exit codes: 0 = game over reached; 3 = move budget hit (still in progress);
nonzero/other = crash or killed (supervisor relaunches -> resume).
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import MoveClient, DeckTracker, MOVE_NAME  # noqa: E402

ARROW = {0: "ArrowUp", 1: "ArrowDown", 2: "ArrowLeft", 3: "ArrowRight"}
_SKIP = json.load(open(os.path.join(os.path.dirname(__file__), "threesgame_skip_tutorial.json")))
_KEY = _SKIP["localStorage_key"]
_ORIGIN = "https://play.threesgame.com"
_DBG = bool(os.environ.get("TG_DEBUG"))


def _decode_slot(inner):
    """Decode the haxe serialization used by Threes.min.js into a field dict.
    Strings are `y<len>:<url-encoded-base64>` (also cached in order); `R<n>`
    references the n-th cached string. Keys and values alternate."""
    i, cache, toks = 0, [], []
    while i < len(inner):
        ch = inner[i]
        if ch == "y":
            colon = inner.index(":", i)
            ln = int(inner[i + 1:colon])
            raw = inner[colon + 1:colon + 1 + ln]
            i = colon + 1 + ln
            try:
                val = base64.b64decode(urllib.parse.unquote(raw) + "===").decode("utf-8", "replace")
            except Exception:
                val = raw
            cache.append(val)
            toks.append(val)
        elif ch == "R":
            j = i + 1
            while j < len(inner) and inner[j].isdigit():
                j += 1
            n = int(inner[i + 1:j])
            toks.append(cache[n] if n < len(cache) else "")
            i = j
        else:
            i += 1
    return {toks[k]: toks[k + 1] for k in range(0, len(toks) - 1, 2)}


def _read_slot(cdp):
    """Read localStorage[_KEY] via the CDP DOMStorage domain. This queries the
    browser process's storage service directly and does NOT execute page JS, so it
    keeps working even when the WebGL render loop has the renderer's JS main thread
    pegged — unlike page.evaluate(), which has no timeout and hangs forever on a
    frozen renderer. That stall is exactly the bug that made canvas capture fail."""
    try:
        res = cdp.send("DOMStorage.getDOMStorageItems",
                       {"storageId": {"securityOrigin": _ORIGIN, "isLocalStorage": True}})
    except Exception:
        return None
    for k, val in res.get("entries", []):
        if k == _KEY:
            return val
    return None


def read_state(cdp):
    """The live game state from localStorage: exact 4x4 board (printed values),
    next tile, move count, and whether the game is still in progress."""
    v = _read_slot(cdp)
    if not v:
        return None
    try:
        d = _decode_slot(base64.b64decode(v).decode("utf-8", "replace"))
    except Exception:
        return None
    g = [int(d.get(f"Grid{n}", "0") or "0") for n in range(16)]
    # Grid0..3 is the BOTTOM screen row, so read rows bottom-to-top to match the
    # game's real orientation. Getting this wrong vertically flips the board, which
    # inverts UP/DOWN: moveserver then returns a move that is legal on the flipped
    # board but a no-op in the actual game, and the run gets permanently stuck.
    return {
        "board": [g[(3 - r) * 4:(3 - r) * 4 + 4] for r in range(4)],
        "next": int(d.get("NextValue", "0") or "0"),
        "moves": int(d.get("NumMoves", "0") or "0"),
        "over": d.get("InProgress") != "true",
    }


def _deck_from_log(path):
    """Rebuild the deck tracker from a resume log's already-recorded `n` (next)
    values so deck-aware play stays accurate across a supervisor restart. Also
    return how many plies were already recorded (for logging)."""
    deck = DeckTracker()
    n = 0
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if "terminal" in rec:
                    continue
                n += 1
                nv = rec.get("n", 0)
                if nv in (1, 2, 3):
                    deck.note(nv)
    except OSError:
        pass
    return deck, n


def play(a):
    mc = MoveClient(a.server)
    print("moveserver:", mc.ping(), flush=True)
    deck, prior = _deck_from_log(a.resume_log)
    log = open(a.resume_log, "a", buffering=1)     # line-buffered append; survives restarts

    def emit(rec):
        log.write(json.dumps(rec) + "\n")
        log.flush()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            a.profile, channel="chrome", headless=not a.headed,
            args=["--ignore-certificate-errors"], viewport={"width": 420, "height": 760})
        # Only seed the tutorial-skip value when slot.0 is ABSENT — never clobber an
        # in-progress game we are resuming.
        ctx.add_init_script(
            f"try{{if(!localStorage.getItem({json.dumps(_KEY)}))"
            f"localStorage.setItem({json.dumps(_KEY)},{json.dumps(_SKIP['localStorage_value'])});}}"
            f"catch(e){{}}")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.set_default_timeout(8000)
        pg.goto(_ORIGIN + "/", wait_until="domcontentloaded", timeout=30000)
        cdp = ctx.new_cdp_session(pg)       # read localStorage browser-side (see _read_slot).
        # NB: deliberately NOT DOMStorage.enable — getDOMStorageItems works without it,
        # and enabling floods the pipe with domStorageItemUpdated events (this game
        # writes localStorage constantly), which wedges the CDP channel.

        # Startup: resume an in-progress game if slot.0 has one, else start fresh.
        st = None
        for _ in range(12):
            st = read_state(cdp)
            if st and not st["over"] and any(v > 0 for row in st["board"] for v in row):
                break
            pg.wait_for_timeout(400)
        resuming = bool(st and not st["over"] and any(v > 0 for row in st["board"] for v in row))
        if resuming:
            print(f"resume: in-progress game at {st['moves']} moves, log has {prior} plies",
                  flush=True)
        else:
            print("fresh game: pressing Space", flush=True)
            pg.wait_for_timeout(3000)
            pg.keyboard.press("Space")          # "PLAY THREES"
            pg.wait_for_timeout(1200)
            for _ in range(12):
                st = read_state(cdp)
                if st and not st["over"] and any(v > 0 for row in st["board"] for v in row):
                    break
                pg.wait_for_timeout(400)
            if not st or st["over"]:
                print("could not start a game", flush=True)
                ctx.close(); sys.exit(4)

        # Let the page become input-ready before the first move. A freshly loaded
        # (esp. RESUMED) game accepts localStorage reads immediately but ignores
        # keystrokes for a beat while it finishes rendering — pressing too early is
        # a silent no-op, which used to strand every resume on its first move.
        pg.wait_for_timeout(3000)
        best_tile = 0
        over = False
        for step in range(a.moves):
            board = st["board"]
            if st["over"]:
                over = True
                break
            best_tile = max(best_tile, max(v for row in board for v in row))
            nv = st["next"] if st["next"] in (1, 2, 3) else 0
            best = mc.ask(board, next_val=nv, deck=deck.remaining())
            if best < 0:
                over = True            # moveserver: no legal move == real game over
                break
            m0 = st["moves"]
            if _DBG:
                print(f"    [dbg s{step}] press {ARROW[best]}", file=sys.stderr, flush=True)
            pg.keyboard.press(ARROW[best])
            # `best` is the best LEGAL move for this exact board, so it WILL advance
            # the game. Two things must complete before we ask for the next move:
            #   1. NumMoves increments (the slide/merge saved), and
            #   2. the newly SPAWNED tile lands — it's written a beat AFTER NumMoves,
            #      so reading too early yields a stale board missing one tile, and
            #      moveserver then returns a move that is a no-op on the real board
            #      (this is what made moves spuriously "not register").
            # So we poll until NumMoves increments AND the board is stable across two
            # reads (spawn settled). A wedged read just hangs -> supervisor resumes.
            registered = False
            st_new = None
            for _ in range(12):            # up to ~3.6s
                pg.wait_for_timeout(300)
                s = read_state(cdp)
                if not s:
                    continue
                if not registered:
                    if s["moves"] > m0 or s["over"]:
                        registered, st_new = True, s
                elif s["over"] or s["board"] == st_new["board"]:
                    st_new = s
                    break
                else:
                    st_new = s
            if _DBG:
                print(f"    [dbg s{step}] registered={registered} "
                      f"moves={st_new and st_new.get('moves')} m0={m0}",
                      file=sys.stderr, flush=True)
            if not registered:
                print(f"stall: move {prior+step+1} didn't register — bail for resume",
                      flush=True)
                ctx.close()
                sys.exit(3)
            st = st_new
            emit({"b": board, "n": nv, "m": best})   # board BEFORE + the move applied
            if nv in (1, 2, 3):
                deck.note(nv)
            if step % 20 == 0:
                print(f"  move {prior+step+1}: max {best_tile} next {nv} "
                      f"move {MOVE_NAME[best]}", flush=True)
            if st["over"]:
                over = True
                break

        # Terminal: record the final board, grab the settlement screenshot, exit.
        emit({"terminal": st["board"]})
        try:
            shot = pg.screenshot(type="png", timeout=8000)   # ONE grab, game already over
            with open(a.gameover_png, "wb") as f:
                f.write(shot)
        except Exception:
            pass
        print(f"game over={over} at {st['moves']} moves, max {best_tile}", flush=True)
        ctx.close()
        sys.exit(0 if over else 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--moves", type=int, default=2000)
    ap.add_argument("--profile", required=True, help="persistent Chrome user-data-dir")
    ap.add_argument("--resume-log", required=True, help="JSONL ply log (appended across restarts)")
    ap.add_argument("--gameover-png", default="/tmp/threesgame_gameover.png")
    ap.add_argument("--depth-cap", type=int, default=5)
    a = ap.parse_args()
    play(a)


if __name__ == "__main__":
    main()
