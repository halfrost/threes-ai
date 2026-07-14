"""Play threesjs.io with the strong Go agent (Phase 4, web).

threesjs.io turned out to be a **Unity WebGL** game (no DOM board), so this drives
it by screenshotting the canvas and reading tiles by colour + OCR, then pressing
arrow keys — all verified working headlessly via the system Chrome. The generic
DOM driver (driver.py) is for real DOM clones; use THIS for threesjs.io.

What was reverse-engineered (all confirmed live):
  - launch the system Google Chrome (channel="chrome") — Playwright's own
    Chromium download is blocked by the corporate proxy; run setup_env.sh first.
  - the portal shows a loader with a "Play" button that just calls none_loadding()
    to reveal the already-running Unity game; collapse the right sidebar via its
    ">>" toggle so the board isn't occluded; click "PLAY THREES" on the canvas.
  - a first-time TUTORIAL precedes free play; the AGENT plays through it on its
    own (no manual step). Unity stores completion in IndexedDB, so pass a
    persistent --user-data-dir and later runs start straight in free play (board
    + next preview read cleanly there — verified).
  - tiles: 1 = red, 2 = blue, empty = pale teal (classified by mean colour);
    >= 3 are white tiles whose digit is read by tesseract. Arrow keys move.

Board geometry is calibrated for a 1100x1000 viewport.

Run:
  go run ../../cmd/moveserver -addr :9010 -deckaware &
  # first run plays through the tutorial itself and saves it to the profile;
  # every later run then starts directly in free play.
  SSL_CERT_FILE=~/.threes-ca.pem python threesjs_driver.py --user-data-dir ~/.threes-profile
"""
from __future__ import annotations
import argparse
import io
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import MoveClient, DeckTracker, VALUE, MOVE_NAME  # noqa: E402

ARROW = {0: "ArrowUp", 1: "ArrowDown", 2: "ArrowLeft", 3: "ArrowRight"}
# 4 column / 4 row tile-centre pixels for a 1100x1000 viewport (measured live).
COLC = [367, 489, 610, 731]
ROWC = [211, 382, 551, 721]
_OCR_CACHE = {}   # cell-image -> value; a tile renders identically so OCR once


def _mean_rgb(im, x, y, h=28):
    px = list(im.crop((x - h, y - h, x + h, y + h)).resize((10, 10)).getdata())
    n = len(px)
    return (sum(p[0] for p in px) / n, sum(p[1] for p in px) / n, sum(p[2] for p in px) / n)


def _classify(im, x, y, scratch):
    r, g, b = _mean_rgb(im, x, y)
    # A 1/2 tile is a fully saturated red/blue cell (low other channels). A white
    # tile with a coloured digit (e.g. pink "24", red "96") also skews red/blue in
    # the mean, so require the tile body itself to be dark in the other channels.
    if r > g + 30 and r > b + 30 and g < 170:
        return 1                                    # red tile
    if b > g + 18 and b > r + 40 and r < 175:
        return 2                                    # blue tile
    if g > r + 12 and b > r + 12 and g > 165 and abs(g - b) < 22:
        return 0                                    # empty cell: teal tint (R clearly below G~=B)
    # white/coloured tile (>=3): threshold at <210 grey to catch dark AND coloured
    # (e.g. pink "24") anti-aliased digits, autocrop, scale up, OCR one line.
    from PIL import ImageOps
    crop = im.crop((x - 52, y - 52, x + 52, y + 52)).convert("L").point(lambda v: 0 if v < 210 else 255)
    bbox = ImageOps.invert(crop).getbbox()
    if bbox:
        crop = crop.crop(bbox)
    key = (crop.size, crop.tobytes())    # a given tile renders identically -> cache the OCR
    if key in _OCR_CACHE:
        return _OCR_CACHE[key]
    crop.resize((crop.width * 3, crop.height * 3)).save(scratch)
    out = subprocess.run(["tesseract", scratch, "-", "--psm", "7",
                          "-c", "tessedit_char_whitelist=0123456789"],
                         capture_output=True, text=True).stdout.strip()
    val = int(out) if out.isdigit() and int(out) in VALUE else -1
    _OCR_CACHE[key] = val
    return val


NEXT_XY = (549, 60)   # next-tile preview, top-centre (1100x1000 viewport)
BOARD_CLIP = {"x": 300, "y": 115, "width": 500, "height": 710}   # the 4x4 grid region


def wait_stable(pg, tries=7, gap=90):
    """Block until the board region stops animating (two frames ~identical), so
    OCR runs on a settled frame instead of a mid-slide/merge frame."""
    from PIL import Image, ImageChops
    prev = None
    for _ in range(tries):
        im = Image.open(io.BytesIO(pg.screenshot(type="png", clip=BOARD_CLIP))).convert("L").resize((60, 84))
        if prev is not None and sum(ImageChops.difference(im, prev).getdata()) < 250:
            return
        prev = im
        pg.wait_for_timeout(gap)


def board_signature(pg):
    """A cheap fingerprint of the board region (no OCR) — for detecting whether a
    move actually changed the board without a full 16-cell OCR read."""
    from PIL import Image
    return Image.open(io.BytesIO(pg.screenshot(type="png", clip=BOARD_CLIP))).convert("L").resize((44, 62)).tobytes()


def read_board(pg, scratch):
    from PIL import Image
    im = Image.open(io.BytesIO(pg.screenshot(type="png"))).convert("RGB")
    board = [[_classify(im, COLC[c], ROWC[r], scratch) for c in range(4)] for r in range(4)]
    nxt = _classify(im, NEXT_XY[0], NEXT_XY[1], scratch)   # 1/2/value, or -1 (bonus "+"/unknown)
    return board, nxt


MENU_NAME_XY = (549, 430)   # the Unity menu's "Enter your name" field
PLAY_XY = (550, 500)        # PLAY THREES button on the Unity menu
RETRY_XY = (262, 50)        # "retry" control on the game-over screen


def start_game(pg, name=""):
    """Dismiss the portal loader, collapse the sidebar, optionally set the
    leaderboard name, and click PLAY THREES. The name field only exists on the
    Unity menu (fresh profile); with a saved profile it goes straight to a board,
    where these menu clicks are harmless no-ops."""
    for _ in range(16):
        pg.wait_for_timeout(4000)
        if pg.evaluate("()=>typeof none_loadding==='function' && document.querySelector('#div_btn') "
                       "&& document.querySelector('#div_btn').offsetParent!==null"):
            break
    pg.evaluate("()=>none_loadding()")
    pg.wait_for_timeout(1200)
    tog = pg.evaluate("""()=>{for(const el of document.querySelectorAll('*')){
        const t=(el.textContent||'').trim();
        if((t==='>>'||t==='\\u00bb')&&el.children.length===0){const r=el.getBoundingClientRect();
          return {x:r.left+r.width/2,y:r.top+r.height/2};}}return null;}""")
    if tog:
        pg.mouse.click(tog["x"], tog["y"])
        pg.wait_for_timeout(800)
    _wait_menu_rendered(pg)              # Unity draws its menu a beat after none_loadding
    if name:
        pg.mouse.click(*MENU_NAME_XY)     # focus the name field
        pg.wait_for_timeout(600)          # let Unity register focus (else the 1st char drops)
        pg.keyboard.type(name, delay=40)  # the Unity input captures typed chars
        pg.wait_for_timeout(300)
    pg.mouse.click(*PLAY_XY)              # PLAY THREES on the Unity canvas
    pg.wait_for_timeout(2500)


def _wait_menu_rendered(pg, tries=24, gap=500):
    """Wait until the Unity canvas stops being the dark loading colour, i.e. the
    menu (light background) has actually rendered — otherwise clicks/typing land
    on a black frame and do nothing."""
    from PIL import Image
    for _ in range(tries):
        im = Image.open(io.BytesIO(pg.screenshot(type="png",
             clip={"x": 470, "y": 380, "width": 160, "height": 120}))).convert("L")
        data = list(im.getdata())
        if sum(data) / len(data) > 90:   # dark loading frame ~35; menu bg is light
            return
        pg.wait_for_timeout(gap)


def play(a):
    scratch = os.path.join(os.path.dirname(__file__), "_cell.png")
    mc = MoveClient(a.server)
    print("moveserver:", mc.ping())
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        vp = {"width": 1100, "height": 1000}
        if a.user_data_dir:
            ctx = p.chromium.launch_persistent_context(a.user_data_dir, channel="chrome",
                                                       headless=not a.headed, viewport=vp)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            closer = ctx
        else:
            b = p.chromium.launch(channel="chrome", headless=not a.headed)
            pg = b.new_page(viewport=vp)
            closer = b
        pg.goto("https://threesjs.io/", wait_until="domcontentloaded", timeout=30000)
        start_game(pg, a.player_name)
        if a.headed and a.tutorial_pause:
            input("Clear the one-time tutorial in the browser, then press Enter here to hand over...")

        def read_stable():
            wait_stable(pg)      # let the slide/merge animation settle first
            for _ in range(3):   # then retry past any residual unreadable (-1) cell
                bd, nx = read_board(pg, scratch)
                if all(v >= 0 for row in bd for v in row):
                    return bd, nx
                pg.wait_for_timeout(200)
            return bd, nx

        def play_one_game():
            deck = DeckTracker()
            empties = 0
            best_tile = 0
            board, nxt = read_stable()
            for step in range(a.moves):
                filled = sum(1 for row in board for v in row if v > 0)
                if filled == 0:                      # board not readable: over / not ready
                    empties += 1
                    if empties > 6:
                        return step, best_tile
                    pg.wait_for_timeout(600); board, nxt = read_stable(); continue
                empties = 0
                best_tile = max(best_tile, max((v for row in board for v in row), default=0))
                vals = [[v if v >= 0 else 0 for v in row] for row in board]  # _classify returns VALUES
                nv = nxt if nxt in (1, 2, 3) else 0   # base tile known; else bonus/unread -> range
                best = mc.ask(vals, next_val=nv, deck=deck.remaining())
                if best < 0:
                    return step, best_tile
                # press the best move; if a misread made it a no-op on the real
                # board, fall back through the other directions until the board
                # actually changes (cheap pixel check, no OCR). If NO direction
                # changes it, the game is over.
                sig0 = board_signature(pg)
                moved = False
                for m in [best] + [d for d in (0, 1, 2, 3) if d != best]:
                    pg.keyboard.press(ARROW[m])
                    time.sleep(a.move_delay)
                    wait_stable(pg)
                    if board_signature(pg) != sig0:
                        moved = True
                        break
                if not moved:
                    return step, best_tile
                if nv in (1, 2, 3):
                    deck.note(nv)
                if step % 20 == 0:
                    print(f"  step {step}: tiles={filled} maxtile={best_tile} next={nv} move={MOVE_NAME[best]}")
                board, nxt = read_stable()           # one OCR read after the move that worked
            return a.moves, best_tile

        for game in range(a.games):
            steps, best_tile = play_one_game()
            print(f"game {game+1}/{a.games}: {steps} moves, max tile {best_tile}.", flush=True)
            if game + 1 < a.games:
                pg.mouse.click(*RETRY_XY)     # "retry" on the game-over screen
                pg.wait_for_timeout(2500)
        closer.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--user-data-dir", default="", help="persistent Chrome profile (skips the one-time tutorial after first run)")
    ap.add_argument("--headed", action="store_true", help="visible browser (use for the one-time tutorial)")
    ap.add_argument("--tutorial-pause", action="store_true", help="with --headed, pause so you can clear the tutorial by hand")
    ap.add_argument("--moves", type=int, default=4000, help="safety cap on moves per game")
    ap.add_argument("--games", type=int, default=1, help="games to play back-to-back (retry between)")
    ap.add_argument("--player-name", default="", help="leaderboard name to type on the start menu")
    ap.add_argument("--move-delay", type=float, default=0.32)
    a = ap.parse_args()
    play(a)


if __name__ == "__main__":
    main()
