"""Play the OFFICIAL Threes (play.threesgame.com) with the strong Go agent.

Same methodology as threesjs_driver, adapted to the official game:
  - It's a fixed-size (316x476) JS canvas (Threes.min.js) on Google Cloud Storage;
    we render at device_scale_factor=3 so the tiles are big enough to read, and
    pass --ignore-certificate-errors (the bare domain's cert is for *.googleapis).
  - The multi-stage tutorial is skipped PERMANENTLY by injecting a saved-slot
    localStorage value with CompletedTutorial=true (deploy/web/threesgame_skip_
    tutorial.json) via add_init_script — no profile, no manual clearing. Start a
    game with the Spacebar.
  - Colours: 1=blue, 2=red, 3=white, empty=teal (note: 1/2 are SWAPPED vs
    threesjs.io). Only 1/2/3 ever need reading and they are read by COLOUR, so
    the stylised Threes font (which tesseract can't read) is never OCR'd.
  - ENGINE-IN-THE-LOOP: OCR the initial low-tile board once, then track the true
    board with the Threes engine (apply_move + spawn placement). High tiles are
    tracked, never OCR'd -> exact board, score and replay. Records the best game
    via deploy/recorder.py (best.json plays in web/replay.html; best.png = the
    game-over screen).

Run:
  go run ../../cmd/moveserver -addr :9010 -deckaware &
  SSL_CERT_FILE=~/.threes-ca.pem python threesgame_driver.py \
      --record-dir ../../results/replays/threesgame --games 5
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "rl"))
from common import MoveClient, DeckTracker, VALUE, INDEX, MOVE_NAME  # noqa: E402
from recorder import GameRecorder, BestKeeper  # noqa: E402
from threes_env import apply_move, _lane_cells  # noqa: E402

ARROW = {0: "ArrowUp", 1: "ArrowDown", 2: "ArrowLeft", 3: "ArrowRight"}
# Coordinates are in the canvas.toDataURL image (948x1428 at device_scale_factor=3).
# We read the WebGL canvas directly with toDataURL, NOT page.screenshot — the latter
# hangs on this continuously-animating GPU canvas after many grabs. toDataURL is fast
# and stable once the drawing buffer is preserved (via _PATCH below).
COLC = [187, 379, 572, 764]
ROWC = [446, 705, 963, 1222]
NEXT_XY = (472, 148)
BOARD_BOX = (87, 316, 864, 1352)            # canvas crop for the move-change signature
_SKIP = json.load(open(os.path.join(os.path.dirname(__file__), "threesgame_skip_tutorial.json")))
# Force preserveDrawingBuffer so canvas.toDataURL returns the rendered frame (else black).
_PATCH = ("(()=>{const o=HTMLCanvasElement.prototype.getContext;"
          "HTMLCanvasElement.prototype.getContext=function(t,a){"
          "if(t==='webgl'||t==='webgl2'||t==='experimental-webgl'){"
          "a=Object.assign({},a,{preserveDrawingBuffer:true});}"
          "return o.call(this,t,a);};})();")


def read_canvas(pg, tries=4):
    """The game canvas as a PIL image via toDataURL. Repeated GPU read-back can
    eventually stall, so each call has the page's (short) timeout + retries."""
    import base64
    from PIL import Image
    for _ in range(tries):
        try:
            u = pg.evaluate("()=>{const c=document.querySelector('canvas');return c?c.toDataURL('image/png'):'';}")
        except Exception:
            pg.wait_for_timeout(500); continue
        if u.startswith("data:image"):
            return Image.open(io.BytesIO(base64.b64decode(u.split(',', 1)[1]))).convert("RGB")
        pg.wait_for_timeout(200)
    return None


def _mean(im, x, y, h):
    px = list(im.crop((x - h, y - h, x + h, y + h)).resize((10, 10)).getdata())
    n = len(px)
    return tuple(sum(p[k] for p in px) / n for k in range(3))


def _classify(im, x, y, h=48):
    """Colour-only tile read: 1=blue, 2=red, 3=white, 0=empty. Higher white tiles
    never need this (the engine tracks them); only 1/2/3 ever appear as the board
    start / next / spawn, and those are unambiguous by colour."""
    r, g, b = _mean(im, x, y, h)
    if b > g + 18 and b > r + 40 and r < 175:
        return 1                                     # blue
    if r > g + 30 and r > b + 30 and g < 170:
        return 2                                     # red
    if r > 195 and g > 195 and b > 185 and abs(r - g) < 25:
        return 3                                     # white
    return 0                                         # teal / empty


def wait_stable(pg, tries=7, gap=80):
    """Read the canvas until the board region settles; returns the settled image."""
    from PIL import ImageChops
    prev, im = None, None
    for _ in range(tries):
        im = read_canvas(pg)
        if im is None:
            pg.wait_for_timeout(gap); continue
        cur = im.crop(BOARD_BOX).convert("L").resize((60, 80))
        if prev is not None and sum(ImageChops.difference(cur, prev).getdata()) < 300:
            return im
        prev = cur
        pg.wait_for_timeout(gap)
    return im


def board_sig(im):
    return im.crop(BOARD_BOX).convert("L").resize((44, 60)).tobytes()


def read_board(im):
    board = [[_classify(im, COLC[c], ROWC[r]) for c in range(4)] for r in range(4)]
    return board, _classify(im, NEXT_XY[0], NEXT_XY[1], 30)


def play(a):
    mc = MoveClient(a.server)
    print("moveserver:", mc.ping())
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not a.headed,
                                    args=["--ignore-certificate-errors"])
        ctx = browser.new_context(viewport={"width": 420, "height": 760}, device_scale_factor=3)
        ctx.add_init_script(_PATCH)             # preserveDrawingBuffer, BEFORE the WebGL context
        ctx.add_init_script(f"try{{localStorage.setItem({json.dumps(_SKIP['localStorage_key'])},"
                            f"{json.dumps(_SKIP['localStorage_value'])});}}catch(e){{}}")
        pg = ctx.new_page()
        pg.set_default_timeout(6000)            # so a stalled toDataURL evaluate fails fast
        pg.goto("https://play.threesgame.com/", wait_until="domcontentloaded", timeout=30000)

        def begin():
            pg.wait_for_timeout(4000)
            pg.keyboard.press("Space")          # "PLAY THREES"
            pg.wait_for_timeout(1500)

        def canvas_png():
            import base64
            u = pg.evaluate("()=>{const c=document.querySelector('canvas');return c?c.toDataURL('image/png'):'';}")
            return base64.b64decode(u.split(',', 1)[1]) if u.startswith("data:image") else None

        def play_one_game():
            rec = GameRecorder(agent="threesgame-web-expectimax", depth_cap=a.depth_cap)
            deck = DeckTracker()
            board, nxt = None, -1
            for _ in range(8):
                im = wait_stable(pg)
                if im is not None:
                    bv, nxt = read_board(im)
                    if any(v > 0 for row in bv for v in row):
                        board = [[INDEX.get(v, 0) for v in row] for row in bv]
                        break
                pg.wait_for_timeout(500)
            if board is None:
                rec.finish([[0] * 4 for _ in range(4)]); return 0, 0, rec, 0
            best_tile, desyncs, fails = 0, 0, 0
            for step in range(a.moves):
                vals = [[VALUE[v] for v in row] for row in board]
                best_tile = max(best_tile, max(VALUE[v] for row in board for v in row))
                nv = nxt if nxt in (1, 2, 3) else 0
                best = mc.ask(vals, next_val=nv, deck=deck.remaining())
                if best < 0:
                    rec.finish(vals); return step, best_tile, rec, desyncs
                # Verify the move by the SPAWN, not by OCR'ing the whole board (the
                # colour reader can't tell 3/6/12/... apart, so a full re-read would
                # destroy the engine's high tiles). A real move drops a new tile on
                # a changed lane's edge cell. Press the best move; if no spawn shows
                # (a no-op on the real board), fall through the other legal
                # directions. The engine board is never overwritten from OCR.
                moved, capture_dead = False, False
                for j, m in enumerate([best] + [d for d in (0, 1, 2, 3) if d != best]):
                    nb, changed, eng_moved = apply_move(board, m)
                    if not eng_moved:
                        continue
                    pg.keyboard.press(ARROW[m])
                    time.sleep(a.move_delay)
                    pg.wait_for_timeout(200)
                    im2 = read_canvas(pg)
                    if im2 is None:
                        capture_dead = True; break
                    spawn = None
                    for li in range(4):
                        if not changed[li]:
                            continue
                        r, c = _lane_cells(m, li)[3]
                        if _classify(im2, COLC[c], ROWC[r]) != 0:
                            spawn = (r, c); break
                    if spawn is None:
                        if j > 0:
                            desyncs += 1
                        continue                       # no spawn -> real board unchanged, try next dir
                    r, c = spawn
                    sv = nv if nv in (1, 2, 3) else _classify(im2, COLC[c], ROWC[r])
                    nb[r][c] = INDEX.get(sv, 0)
                    rec.record(vals, nv, m)            # exact board BEFORE + the move that actually applied
                    if nv in (1, 2, 3):
                        deck.note(nv)
                    board, im = nb, im2
                    _, nxt = read_board(im2)
                    moved = True
                    break
                if capture_dead:
                    fails += 1
                    if fails > 6:
                        rec.finish(vals); return step, best_tile, rec, desyncs
                    pg.wait_for_timeout(600); continue
                fails = 0
                if not moved:                          # no direction changed the real board -> game over
                    rec.finish(vals); return step, best_tile, rec, desyncs
                if step % 20 == 0:
                    print(f"  step {step}: max {best_tile} score {rec.final_score()} "
                          f"next {nv} move {MOVE_NAME[best]} desync {desyncs}")
            rec.finish([[VALUE[v] for v in row] for row in board])
            return a.moves, best_tile, rec, desyncs

        begin()
        keeper = BestKeeper(a.record_dir) if a.record_dir else None
        for game in range(a.games):
            steps, best_tile, rec, desyncs = play_one_game()
            pg.wait_for_timeout(900)
            shot = canvas_png()                 # game-over settlement screen (the canvas)
            score = rec.final_score()           # engine score is exact (board is engine-tracked)
            msg = (f"game {game+1}/{a.games}: {steps} moves, max {best_tile}, "
                   f"score {score}, desync {desyncs}")
            if keeper:
                saved, sc, best = keeper.consider(rec.replay_dict(), shot)
                msg += f" | best {best}" + (" -> NEW BEST saved" if saved else "")
            print(msg, flush=True)
            if game + 1 < a.games:
                pg.keyboard.press("Space"); pg.wait_for_timeout(800)   # dismiss game-over
                begin()                                                # start the next game
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--moves", type=int, default=6000)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--record-dir", default="")
    ap.add_argument("--depth-cap", type=int, default=5)
    ap.add_argument("--move-delay", type=float, default=0.26)
    a = ap.parse_args()
    play(a)


if __name__ == "__main__":
    main()
