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
  - a first-time TUTORIAL gates free play. Unity stores completion in IndexedDB,
    so use a persistent --user-data-dir and clear the tutorial ONCE in --headed
    mode; afterwards headless runs go straight to scoring.
  - tiles: 1 = red, 2 = blue, empty = pale teal (classified by mean colour);
    >= 3 are white tiles whose digit is read by tesseract. Arrow keys move.

Board geometry is calibrated for a 1100x1000 viewport.

Run:
  go run ../../cmd/moveserver -addr :9010 -deckaware &
  SSL_CERT_FILE=~/.threes-ca.pem python threesjs_driver.py --headed --user-data-dir ~/.threes-profile   # once
  SSL_CERT_FILE=~/.threes-ca.pem python threesjs_driver.py --user-data-dir ~/.threes-profile             # then
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
    crop.resize((crop.width * 3, crop.height * 3)).save(scratch)
    out = subprocess.run(["tesseract", scratch, "-", "--psm", "7",
                          "-c", "tessedit_char_whitelist=0123456789"],
                         capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() and int(out) in VALUE else -1


NEXT_XY = (549, 60)   # next-tile preview, top-centre (1100x1000 viewport)


def read_board(pg, scratch):
    from PIL import Image
    im = Image.open(io.BytesIO(pg.screenshot(type="png"))).convert("RGB")
    board = [[_classify(im, COLC[c], ROWC[r], scratch) for c in range(4)] for r in range(4)]
    nxt = _classify(im, NEXT_XY[0], NEXT_XY[1], scratch)   # 1/2/value, or -1 (bonus "+"/unknown)
    return board, nxt


def start_game(pg):
    """Dismiss the portal loader, collapse the sidebar, click PLAY THREES."""
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
    pg.mouse.click(550, 500)   # PLAY THREES on the Unity canvas
    pg.wait_for_timeout(2500)


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
        start_game(pg)
        if a.headed and a.tutorial_pause:
            input("Clear the one-time tutorial in the browser, then press Enter here to hand over...")
        deck = DeckTracker()
        empties = 0

        def read_stable():
            for _ in range(3):   # retry past mid-animation frames (unreadable -1)
                bd, nx = read_board(pg, scratch)
                if all(v >= 0 for row in bd for v in row):
                    return bd, nx
                pg.wait_for_timeout(250)
            return bd, nx

        for step in range(a.moves):
            board, nxt = read_stable()
            filled = sum(1 for row in board for v in row if v > 0)
            if filled == 0:
                empties += 1
                if empties > 5:
                    print("no tiles for 5 steps — tutorial not cleared or game over."); break
                pg.wait_for_timeout(700); continue
            empties = 0
            vals = [[v if v >= 0 else 0 for v in row] for row in board]  # _classify returns VALUES
            nv = nxt if nxt in (1, 2, 3) else 0   # base tile known; else bonus/unread -> range
            best = mc.ask(vals, next_val=nv, deck=deck.remaining())
            if best < 0:
                print(f"game over at step {step} (no legal move)."); break
            # press the best move; if a misread made it a no-op on the real board,
            # fall back through the other directions until the board actually
            # changes. Only if NO direction changes it is the game truly over.
            moved = False
            for m in [best] + [d for d in (0, 1, 2, 3) if d != best]:
                pg.keyboard.press(ARROW[m])
                time.sleep(a.move_delay)
                after, _ = read_stable()
                if after != board:
                    moved = True
                    break
            if not moved:
                print(f"game over at step {step} (no direction changes the board)."); break
            if nv in (1, 2, 3):
                deck.note(nv)
            if step % 10 == 0:
                mx = max((v for row in board for v in row if v > 0), default=0)
                print(f"step {step}: tiles={filled} maxtile={mx} next={nv} move={MOVE_NAME[best]}")
        closer.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--user-data-dir", default="", help="persistent Chrome profile (skips the one-time tutorial after first run)")
    ap.add_argument("--headed", action="store_true", help="visible browser (use for the one-time tutorial)")
    ap.add_argument("--tutorial-pause", action="store_true", help="with --headed, pause so you can clear the tutorial by hand")
    ap.add_argument("--moves", type=int, default=2000)
    ap.add_argument("--move-delay", type=float, default=0.35)
    a = ap.parse_args()
    play(a)


if __name__ == "__main__":
    main()
