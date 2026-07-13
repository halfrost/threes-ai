"""Playwright web driver for Threes leaderboard scoring (Phase 4).

Loop: read the board from the live page -> ask the Go moveserver for the best
move -> inject the move -> repeat; restart on game over. Works against any web
Threes (threesjs.io, play.threesgame.com) once `read_board` is wired to that
site's DOM/canvas.

Two board-reading strategies (pick per site, both stubbed below):
  A. JS-state hook (preferred, exact): eval JS in the page to pull the game's
     internal board array. Best for open JS clones like threesjs.io — use the
     browser devtools / `playwright codegen` to find the global or DOM node.
  B. Canvas OCR: screenshot the board region and classify tiles (reuse the
     android/ocr exemplar approach). Needed when the board is a <canvas> with no
     accessible state (e.g. the official play.threesgame.com).

The Go agent runs in `cmd/moveserver` (start it first). This file is a scaffold:
the browser plumbing and the loop are here; the site-specific `read_board` and
`inject_move` details are marked TODO.

Setup:  pip install -r requirements.txt && playwright install chromium
Run:    go run ../../cmd/moveserver -addr :9010 -depthcap 5 -deckaware &
        python driver.py --url https://threesjs.io/
Dry run (no browser, tests the moveserver): python driver.py --dry-run
"""
from __future__ import annotations
import argparse
import time
import urllib.request
import json

MOVE_KEYS = {0: "ArrowUp", 1: "ArrowDown", 2: "ArrowLeft", 3: "ArrowRight"}


def ask_move(server, board, next_val, deck=None):
    """POST the board to the Go moveserver; return the move (0..3) or -1."""
    body = json.dumps({"board": board, "next": next_val, "deck": deck or []}).encode()
    req = urllib.request.Request(server + "/move", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["move"]


class DeckTracker:
    """Tracks the remaining 1/2/3 bag by counting tiles as they appear, so we can
    play deck-aware on the real site. Reset the count when the bag empties (every
    12 base tiles). Returns pre-preview counts (what the search expects)."""
    def __init__(self):
        self.drawn = [0, 0, 0]

    def note(self, value):
        if value in (1, 2, 3):
            self.drawn[value - 1] += 1
            if sum(self.drawn) >= 12:
                self.drawn = [0, 0, 0]

    def remaining(self):
        return [4 - self.drawn[i] for i in range(3)]


# ---------------------------------------------------------------------------
# SITE-SPECIFIC: implement these two for the target site.
# ---------------------------------------------------------------------------
def read_board(page):
    """Return (board_values_4x4, next_value) or (None, None) if game over.

    TODO (Strategy A, threesjs.io): use page.evaluate() to read the game's board
    array from its JS state, e.g.:
        state = page.evaluate("() => window.__THREES_STATE__ || null")
    Inspect the site with `playwright codegen https://threesjs.io/` to find where
    the board lives (a global, a Vue/React store, or data-* attributes on tiles).

    TODO (Strategy B, canvas / official site): screenshot the board region and OCR
    each tile (reuse android/ocr's exemplar matcher). Detect game over from the
    'game over' overlay.
    """
    raise NotImplementedError(
        "wire read_board to the target site (see the docstring: JS hook or OCR)")


def inject_move(page, move):
    """Send the move to the page. Most web Threes accept arrow keys; some need a
    swipe (mouse drag). TODO: verify which the target site uses."""
    page.keyboard.press(MOVE_KEYS[move])
    # swipe fallback (uncomment / adjust for touch-only sites):
    # box = page.locator(".board").bounding_box()
    # cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
    # dx, dy = {0:(0,-120),1:(0,120),2:(-120,0),3:(120,0)}[move]
    # page.mouse.move(cx, cy); page.mouse.down(); page.mouse.move(cx+dx, cy+dy, steps=8); page.mouse.up()


def restart(page):
    """TODO: click the site's 'new game' / 'try again' button after game over."""
    raise NotImplementedError("wire restart to the target site's new-game control")


def play_loop(url, server, move_delay, games):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(2000)
        for g in range(games):
            deck = DeckTracker()
            while True:
                board, next_val = read_board(page)
                if board is None:
                    break  # game over
                move = ask_move(server, board, next_val, deck.remaining())
                if move < 0:
                    break
                if next_val in (1, 2, 3):
                    deck.note(next_val)
                inject_move(page, move)
                time.sleep(move_delay)
            print(f"game {g+1} finished", flush=True)
            restart(page)
        browser.close()


def dry_run(server):
    """Test the moveserver with a fixed board, no browser."""
    board = [[1, 2, 0, 0], [3, 6, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    move = ask_move(server, board, next_val=1)
    print(f"dry-run: moveserver returned move={move} "
          f"({['UP','DOWN','LEFT','RIGHT'][move] if move>=0 else 'none'})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://threesjs.io/")
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--move-delay", type=float, default=0.15)
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        dry_run(args.server)
    else:
        play_loop(args.url, args.server, args.move_delay, args.games)


if __name__ == "__main__":
    main()
