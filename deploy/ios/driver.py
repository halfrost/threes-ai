"""iOS scoring driver (Phase 4): drive the real Threes iOS app via WebDriverAgent.

iOS has no `adb input`, so we talk to WebDriverAgent (WDA) — Facebook's on-device
automation server (the same one Appium uses) — directly over HTTP. That keeps the
iOS driver as self-contained as the others (just urllib + the shared OCR): no
Appium/Selenium Python stack required.

Loop: WDA `GET /screenshot` -> OCR (android/ocr) -> ask moveserver -> WDA
`dragfromtoforduration` swipe -> deck-track -> repeat; restart on game over.

Coordinates: the screenshot is in PIXELS, WDA touch is in POINTS, so we divide by
the device scale (--scale, 3 for most modern iPhones, 2 for older/SE).

One-time setup (needs a Mac + Xcode + a real device — App Store apps don't run on
the Simulator):
  1. Build & launch WebDriverAgentRunner on the device (via Xcode, or
     `xcodebuild ... -scheme WebDriverAgentRunner test`).
  2. Forward its port to your Mac:  iproxy 8100 8100   (from libimobiledevice)
  3. Verify:  curl http://localhost:8100/status
  4. Add a CONFIGS['<model>'] entry (pixel geometry) to android/ocr/devices.py,
     measured from a WDA screenshot, and bootstrap exemplars (see ../android).
Run:
  go run ../../cmd/moveserver -addr :9010 -deckaware &
  python driver.py --model 'iPhone_14' --scale 3
"""
from __future__ import annotations
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))          # deploy/common.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))    # repo root -> android.ocr
from common import MoveClient, DeckTracker, to_values, MOVE_NAME, VALUE  # noqa: E402

SWIPE_DIR = {0: (0, -1), 1: (0, 1), 2: (-1, 0), 3: (1, 0)}  # UP DOWN LEFT RIGHT


class WDA:
    """Minimal WebDriverAgent HTTP client."""
    def __init__(self, base="http://localhost:8100"):
        self.base = base.rstrip("/")
        self.sid = None

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    def session(self):
        v = self._req("POST", "/session", {"capabilities": {}})
        self.sid = v.get("sessionId") or v.get("value", {}).get("sessionId")
        return self.sid

    def screenshot(self):
        from PIL import Image
        v = self._req("GET", "/screenshot")["value"]
        return Image.open(io.BytesIO(base64.b64decode(v)))

    def drag(self, x1, y1, x2, y2, duration=0.1):
        self._req("POST", f"/session/{self.sid}/wda/dragfromtoforduration",
                  {"fromX": x1, "fromY": y1, "toX": x2, "toY": y2, "duration": duration})

    def tap(self, x, y):
        self._req("POST", f"/session/{self.sid}/wda/tap/0", {"x": x, "y": y})


def swipe_points(cfg, scale):
    """Board centre and swipe delta in POINTS (pixels / scale) from the OCR geometry."""
    cx = (cfg.x0 + 1.5 * cfg.dx + cfg.w / 2) / scale
    cy = (cfg.y0 + 1.5 * cfg.dy + cfg.h / 2) / scale
    dist = 1.2 * min(cfg.dx, cfg.dy) / scale
    return cx, cy, dist


def next_values(tileset):
    return [VALUE[i] for i in tileset]


def play_loop(a):
    from android.ocr import OCR
    from android.ocr.devices import CONFIGS
    if a.model not in CONFIGS:
        sys.exit(f"no CONFIGS['{a.model}'] in android/ocr/devices.py — add pixel geometry first")
    cfg = CONFIGS[a.model]
    ocr = OCR(a.model)
    mc = MoveClient(a.server)
    print("moveserver:", mc.ping())
    wda = WDA(a.wda)
    wda.session()
    cx, cy, dist = swipe_points(cfg, a.scale)
    for g in range(a.games):
        deck = DeckTracker()
        moves = 0
        while True:
            board_idx, tileset = ocr.ocr(wda.screenshot())
            if board_idx is None:
                break
            board = to_values([list(r) for r in board_idx])
            nset = next_values(tileset) if tileset else None
            move = mc.ask(board, next_set=nset, deck=deck.remaining())
            if move < 0:
                break
            if nset and len(nset) == 1 and nset[0] in (1, 2, 3):
                deck.note(nset[0])
            dx, dy = SWIPE_DIR[move]
            wda.drag(cx, cy, cx + dx * dist, cy + dy * dist)
            moves += 1
            time.sleep(a.move_delay)
        print(f"game {g+1}: {moves} moves, over.", flush=True)
        if a.games > 1 and a.restart_tap:
            x, y = (float(v) for v in a.restart_tap.split(","))
            wda.tap(x, y)
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
    ap.add_argument("--wda", default="http://localhost:8100", help="WebDriverAgent base URL")
    ap.add_argument("--scale", type=float, default=3.0, help="device pixel scale (3 modern, 2 older/SE)")
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--move-delay", type=float, default=0.25)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--restart-tap", default="", help="'x,y' (points) of the new-game button")
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
