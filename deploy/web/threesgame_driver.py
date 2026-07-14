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
COLC = [331, 523, 716, 908]                 # tile-centre px, device_scale_factor=3
ROWC = [512, 771, 1029, 1288]
NEXT_XY = (616, 214)                        # next-tile preview (top centre)
BOARD_CLIP = {"x": 231, "y": 382, "width": 777, "height": 1036}
_SKIP = json.load(open(os.path.join(os.path.dirname(__file__), "threesgame_skip_tutorial.json")))


GAME_CLIP = {"x": 0, "y": 0, "width": 1080, "height": 1500}   # board+next; keeps coords


def _png(pg, clip):
    """Screenshot a clip with a short timeout + one retry — the official Threes
    canvas animates continuously and an occasional full-frame grab hangs."""
    for _ in range(2):
        try:
            return pg.screenshot(type="png", clip=clip, timeout=8000, animations="disabled")
        except Exception:
            pg.wait_for_timeout(300)
    return pg.screenshot(type="png", clip=clip, timeout=15000, animations="disabled")


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
    from PIL import Image, ImageChops
    prev = None
    for _ in range(tries):
        im = Image.open(io.BytesIO(_png(pg, BOARD_CLIP))).convert("L").resize((60, 80))
        if prev is not None and sum(ImageChops.difference(im, prev).getdata()) < 300:
            return
        prev = im
        pg.wait_for_timeout(gap)


def board_signature(pg):
    from PIL import Image
    return Image.open(io.BytesIO(_png(pg, BOARD_CLIP))).convert("L").resize((44, 60)).tobytes()


def snap(pg):
    from PIL import Image
    return Image.open(io.BytesIO(_png(pg, GAME_CLIP))).convert("RGB")


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
        ctx.add_init_script(f"try{{localStorage.setItem({json.dumps(_SKIP['localStorage_key'])},"
                            f"{json.dumps(_SKIP['localStorage_value'])});}}catch(e){{}}")
        pg = ctx.new_page()
        pg.goto("https://play.threesgame.com/", wait_until="domcontentloaded", timeout=30000)

        def begin():
            pg.wait_for_timeout(4000)
            pg.keyboard.press("Space")          # "PLAY THREES"
            pg.wait_for_timeout(1500)

        def read_stable():
            wait_stable(pg)
            for _ in range(3):
                im = snap(pg)
                bd, nx = read_board(im)
                if all(v >= 0 for row in bd for v in row):
                    return im, bd, nx
                pg.wait_for_timeout(200)
            return im, bd, nx

        def play_one_game():
            rec = GameRecorder(agent="threesgame-web-expectimax", depth_cap=a.depth_cap)
            deck = DeckTracker()
            board = None
            for _ in range(8):
                _, bv, nxt = read_stable()
                if any(v > 0 for row in bv for v in row):
                    board = [[INDEX.get(v, 0) for v in row] for row in bv]
                    break
                pg.wait_for_timeout(500)
            if board is None:
                rec.finish([[0] * 4 for _ in range(4)]); return 0, 0, rec, 0
            best_tile, desyncs = 0, 0
            for step in range(a.moves):
                vals = [[VALUE[v] for v in row] for row in board]
                best_tile = max(best_tile, max(VALUE[v] for row in board for v in row))
                nv = nxt if nxt in (1, 2, 3) else 0
                best = mc.ask(vals, next_val=nv, deck=deck.remaining())
                if best < 0:
                    rec.finish(vals); return step, best_tile, rec, desyncs
                rec.record(vals, nv, best)
                if nv in (1, 2, 3):
                    deck.note(nv)
                sig0 = board_signature(pg)
                pg.keyboard.press(ARROW[best]); time.sleep(a.move_delay)
                wait_stable(pg)
                im = snap(pg)
                if board_signature(pg) == sig0:
                    desyncs += 1
                    if rec.steps:
                        rec.steps.pop()
                    bv, nxt = read_board(im)
                    if any(v > 0 for row in bv for v in row):
                        board = [[INDEX.get(v, 0) for v in row] for row in bv]
                    continue
                nb, changed, _ = apply_move(board, best)
                for li in range(4):
                    if not changed[li]:
                        continue
                    r, c = _lane_cells(best, li)[3]
                    cv = _classify(im, COLC[c], ROWC[r])
                    if cv != 0:
                        sv = nv if nv in (1, 2, 3) else cv
                        nb[r][c] = INDEX.get(sv, 0)
                        break
                board = nb
                _, nxt = read_board(im)
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
            shot = _png(pg, GAME_CLIP)          # game-over settlement screen
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
