"""Android scoring driver (Phase 4): drive the real Threes app via ADB.

Loop: `adb screencap` -> OCR the board+next with the repo's exemplar matcher
(android/ocr) -> ask the Go moveserver for the best move -> `adb input swipe` ->
track the deck -> repeat; restart on game over.

Reuses:
  - android/ocr        the battle-tested exemplar OCR (screenshot -> 4x4 indices
                       + next-tile set). Needs a per-device CONFIGS entry in
                       android/ocr/devices.py and a one-time exemplar bootstrap
                       (it prompts for unknown tiles the first time).
  - deploy/common.py   moveserver client + DeckTracker + tile maps.

Swipe geometry is derived from the SAME OCR config (x0,y0,dx,dy), so one entry
serves both reading and input.

Setup:
  adb devices                     # confirm the emulator/phone is attached
  pip install pillow numpy
  # add a CONFIGS['<model>'] entry (screen + tile geometry) in android/ocr/devices.py
Run:
  go run ../../cmd/moveserver -addr :9010 -deckaware &
  python driver.py --model 'Pixel_7_API_34' --serial emulator-5554
"""
from __future__ import annotations
import argparse
import io
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))          # deploy/common.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))    # repo root -> android.ocr
from common import MoveClient, DeckTracker, to_values, MOVE_NAME, VALUE  # noqa: E402


def adb_base(serial):
    return ["adb"] + (["-s", serial] if serial else [])


def screencap(serial):
    """Grab the screen as a PIL image (exec-out keeps the PNG bytes intact)."""
    from PIL import Image
    png = subprocess.run(adb_base(serial) + ["exec-out", "screencap", "-p"],
                         capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png))


def swipe_points(cfg):
    """Board centre and swipe delta (in px) from the OCR geometry.
    Returns (cx, cy, dist). Swipes go a bit over one tile pitch from centre."""
    cx = cfg.x0 + 1.5 * cfg.dx + cfg.w / 2
    cy = cfg.y0 + 1.5 * cfg.dy + cfg.h / 2
    dist = 1.2 * min(cfg.dx, cfg.dy)
    return cx, cy, dist


# move int -> (dx, dy) direction for the swipe
SWIPE_DIR = {0: (0, -1), 1: (0, 1), 2: (-1, 0), 3: (1, 0)}  # UP DOWN LEFT RIGHT


def do_swipe(serial, cfg, move, duration_ms=60):
    cx, cy, dist = swipe_points(cfg)
    dx, dy = SWIPE_DIR[move]
    x1, y1 = int(cx), int(cy)
    x2, y2 = int(cx + dx * dist), int(cy + dy * dist)
    subprocess.run(adb_base(serial) + ["shell", "input", "swipe",
                   str(x1), str(y1), str(x2), str(y2), str(duration_ms)], check=True)


def next_values(tileset):
    """OCR next-tile set (list of indices) -> candidate VALUES for moveserver."""
    return [VALUE[i] for i in tileset]


def play_loop(a):
    from android.ocr import OCR
    from android.ocr.devices import CONFIGS
    if a.model not in CONFIGS:
        sys.exit(f"no CONFIGS['{a.model}'] in android/ocr/devices.py — add screen+tile geometry first")
    cfg = CONFIGS[a.model]
    ocr = OCR(a.model)
    mc = MoveClient(a.server)
    print("moveserver:", mc.ping())
    for g in range(a.games):
        deck = DeckTracker()
        moves = 0
        while True:
            board_idx, tileset = ocr.ocr(screencap(a.serial))
            if board_idx is None:            # game over
                break
            board = to_values([list(r) for r in board_idx])
            nset = next_values(tileset) if tileset else None
            move = mc.ask(board, next_set=nset, deck=deck.remaining())
            if move < 0:
                break
            if nset and len(nset) == 1 and nset[0] in (1, 2, 3):
                deck.note(nset[0])
            do_swipe(a.serial, cfg, move)
            moves += 1
            time.sleep(a.move_delay)
        print(f"game {g+1}: {moves} moves, over.", flush=True)
        if a.games > 1 and a.restart_tap:
            x, y = (int(v) for v in a.restart_tap.split(","))
            subprocess.run(adb_base(a.serial) + ["shell", "input", "tap", str(x), str(y)], check=True)
            time.sleep(2)


def dry_run(server):
    mc = MoveClient(server)
    print("moveserver:", mc.ping())
    board = [[1, 2, 0, 0], [3, 6, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    m = mc.ask(board, next_val=1, deck=[3, 3, 4])
    print(f"dry-run: move={m} ({MOVE_NAME.get(m, 'none')})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="key into android/ocr/devices.py CONFIGS")
    ap.add_argument("--serial", default="", help="adb device serial (e.g. emulator-5554)")
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--move-delay", type=float, default=0.25)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--restart-tap", default="", help="'x,y' of the new-game button for multi-game runs")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.dry_run:
        dry_run(a.server)
    elif not a.model:
        ap.error("--model is required (or use --dry-run)")
    else:
        play_loop(a)


if __name__ == "__main__":
    main()
