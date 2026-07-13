"""Playwright web driver for Threes leaderboard scoring (Phase 4).

Loop: read the board from the live page -> ask the Go moveserver for the best
move -> press the arrow key -> track the deck -> repeat; restart on game over.

Board reading (two strategies, pick with --site):
  threesjs  (DOM, exact): threesjs.io and most JS clones render tiles as DOM
     elements. We read the board CONTAINER's rectangle and every numbered tile's
     screen position, then map each tile to a (row,col) by where its centre falls
     in the container — selector-tolerant and it handles empty cells. Configure
     the three selectors (board / next / game-over) with --board-selector etc.;
     run `python probe.py` once to discover them on the live page.
  threesgame  (canvas, OCR): the official play.threesgame.com draws to a <canvas>
     with no DOM to read, so we screenshot the board region and OCR it with the
     shared exemplar matcher (android/ocr). Needs a one-time calibration.

Start the brain first:  go run ../../cmd/moveserver -addr :9010 -deckaware
Dry run (no browser):   python driver.py --dry-run
Live:                   python driver.py --site threesjs --url https://threesjs.io/
"""
from __future__ import annotations
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import MoveClient, DeckTracker, MOVE_NAME, VALUE  # noqa: E402

ARROW = {0: "ArrowUp", 1: "ArrowDown", 2: "ArrowLeft", 3: "ArrowRight"}
TILE_VALUES = [str(v) for v in VALUE if v >= 1]

# Selector config per site. These are sensible defaults / guesses; finalize them
# for the live page with probe.py and pass --board-selector / --next-selector /
# --gameover-selector to override.
SITES = {
    "threesjs": dict(
        url="https://threesjs.io/",
        board_selector=".board, #board, .grid, .game-board",
        next_selector=".next, .next-tile, #next, .deck",
        gameover_selector=".game-over, .gameover, .lose, .end",
        restart_selector=".new-game, .restart, .try-again, button",
    ),
}

# Injected into the page: return every numbered tile with its on-screen centre,
# skipping ancestor elements that merely contain a tile's text.
SCAN_JS = r"""
(vals) => {
  const want = new Set(vals);
  const out = [];
  for (const el of document.querySelectorAll('*')) {
    const t = (el.textContent || '').trim();
    if (!want.has(t)) continue;
    if ([...el.children].some(c => (c.textContent || '').trim() === t)) continue; // not a leaf
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    out.push({v: parseInt(t, 10), cx: r.left + r.width / 2, cy: r.top + r.height / 2});
  }
  return out;
}
"""


def rect_of(page, selector):
    """boundingClientRect of the first matching element, or None."""
    return page.evaluate(
        """(sel) => { for (const s of sel.split(',')) {
              const el = document.querySelector(s.trim());
              if (el) { const r = el.getBoundingClientRect();
                return {x:r.left, y:r.top, w:r.width, h:r.height}; } }
            return null; }""", selector)


def read_board_dom(page, cfg):
    """Return (board_values_4x4, next_preview_text) or (None, None) if game over."""
    if page.query_selector(cfg["gameover_selector"]):
        return None, None
    box = rect_of(page, cfg["board_selector"])
    if not box or box["w"] < 8:
        return None, None
    tiles = page.evaluate(SCAN_JS, TILE_VALUES)
    board = [[0, 0, 0, 0] for _ in range(4)]
    cw, ch = box["w"] / 4.0, box["h"] / 4.0
    for t in tiles:
        # only tiles whose centre is inside the board box are grid tiles
        col = int((t["cx"] - box["x"]) / cw)
        row = int((t["cy"] - box["y"]) / ch)
        if 0 <= row < 4 and 0 <= col < 4:
            board[row][col] = t["v"]
    if not any(any(r) for r in board):
        return None, None  # nothing read -> treat as over / not ready
    # next-tile preview: text of the next element (a value, or "+" for a bonus)
    nxt = page.evaluate(
        """(sel) => { for (const s of sel.split(',')) {
              const el = document.querySelector(s.trim());
              if (el) return (el.textContent || '').trim(); } return ''; }""",
        cfg["next_selector"])
    return board, nxt


def next_arg(nxt):
    """Map the next-preview text to (next_val, next_set) for MoveClient.ask."""
    if nxt and nxt.isdigit():
        return int(nxt), None       # a concrete tile value (1/2/3 or higher)
    return 0, None                  # "+" bonus or unknown -> server models the range


def play_loop(args, cfg):
    from playwright.sync_api import sync_playwright
    mc = MoveClient(args.server)
    print("moveserver:", mc.ping())
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.goto(args.url or cfg["url"])
        page.wait_for_timeout(2500)
        page.click("body")  # focus so arrow keys register
        for g in range(args.games):
            deck = DeckTracker()
            moves = 0
            while True:
                board, nxt = read_board_dom(page, cfg)
                if board is None:
                    break
                nv, ns = next_arg(nxt)
                move = mc.ask(board, next_val=nv, next_set=ns, deck=deck.remaining())
                if move < 0:
                    break
                if isinstance(nxt, str) and nxt.isdigit():
                    deck.note(int(nxt))
                page.keyboard.press(ARROW[move])
                moves += 1
                time.sleep(args.move_delay)
            print(f"game {g+1}: {moves} moves, over.", flush=True)
            if args.games > 1 and cfg.get("restart_selector"):
                el = page.query_selector(cfg["restart_selector"])
                if el:
                    el.click()
                    page.wait_for_timeout(1500)
        browser.close()


def dry_run(server):
    mc = MoveClient(server)
    print("moveserver:", mc.ping())
    board = [[1, 2, 0, 0], [3, 6, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    m = mc.ask(board, next_val=1, deck=[3, 3, 4])
    print(f"dry-run: move={m} ({MOVE_NAME.get(m, 'none')})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="threesjs", choices=list(SITES))
    ap.add_argument("--url", default="")
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--move-delay", type=float, default=0.12)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--board-selector", default="")
    ap.add_argument("--next-selector", default="")
    ap.add_argument("--gameover-selector", default="")
    ap.add_argument("--restart-selector", default="")
    a = ap.parse_args()
    if a.dry_run:
        dry_run(a.server)
        return
    cfg = dict(SITES[a.site])
    for k in ("board", "next", "gameover", "restart"):
        v = getattr(a, f"{k}_selector")
        if v:
            cfg[f"{k}_selector"] = v
    play_loop(a, cfg)


if __name__ == "__main__":
    main()
