"""iOS scoring driver (Phase 4): drive the real Threes iOS app via WebDriverAgent.

iOS has no `adb input`, so we talk to WebDriverAgent (WDA) — the on-device
automation server Appium uses — directly over HTTP (just urllib + the shared OCR;
no Appium/Selenium stack). Everything else is shared with the Android/web drivers
via deploy/mobile_core: read the board, ask the moveserver, swipe, record the best
game's replay (plays in web/replay.html) + its game-over screenshot.

Coordinates: the screenshot is in PIXELS, WDA touch is in POINTS, so divide by the
device scale (--scale, 3 for most modern iPhones, 2 for older/SE).

One-time setup (needs a Mac + Xcode + a REAL device — App Store apps don't run on
the Simulator):
  1. Build & launch WebDriverAgentRunner on the device (Xcode, or
     `xcodebuild ... -scheme WebDriverAgentRunner test`).
  2. Forward its port:  iproxy 8100 8100   (from libimobiledevice)
  3. Verify:  curl http://localhost:8100/status
  4. Add a CONFIGS['<model>'] entry (pixel geometry) to android/ocr/devices.py and
     bootstrap exemplars (see ../android).
Run:
  go run ../../cmd/moveserver -addr :9010 -deckaware &
  python driver.py --dry-run                          # brain only
  python driver.py --self-test --record-dir /tmp/it   # full flow, engine stands in
  python driver.py --model 'iPhone_14' --scale 3 \
      --player-name 'Github halfrost' --record-dir ../../results/replays/ios
"""
from __future__ import annotations
import argparse
import base64
import io
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))          # deploy/*
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))    # repo root -> android.ocr
from mobile_core import run_scoring, dry_run, EngineDevice  # noqa: E402

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

    def screenshot_b64(self):
        return self._req("GET", "/screenshot")["value"]

    def drag(self, x1, y1, x2, y2, duration=0.1):
        self._req("POST", f"/session/{self.sid}/wda/dragfromtoforduration",
                  {"fromX": x1, "fromY": y1, "toX": x2, "toY": y2, "duration": duration})

    def tap(self, x, y):
        self._req("POST", f"/session/{self.sid}/wda/tap/0", {"x": x, "y": y})

    def type_text(self, text):
        self._req("POST", f"/session/{self.sid}/wda/keys", {"value": list(text)})


class WdaDevice:
    """A mobile_core Device backed by WebDriverAgent."""
    def __init__(self, model, wda_url, scale, restart_tap="", name_tap=""):
        from android.ocr import OCR
        from android.ocr.devices import CONFIGS
        if model not in CONFIGS:
            sys.exit(f"no CONFIGS['{model}'] in android/ocr/devices.py — add pixel geometry first")
        self.cfg = CONFIGS[model]
        self.ocr = OCR(model)
        self.scale = scale
        self.restart_tap = restart_tap
        self.name_tap = name_tap
        self.wda = WDA(wda_url)
        self.wda.session()
        cx = (self.cfg.x0 + 1.5 * self.cfg.dx + self.cfg.w / 2) / scale
        cy = (self.cfg.y0 + 1.5 * self.cfg.dy + self.cfg.h / 2) / scale
        self.centre = (cx, cy)
        self.dist = 1.2 * min(self.cfg.dx, self.cfg.dy) / scale

    def _shot(self):
        from PIL import Image
        return Image.open(io.BytesIO(base64.b64decode(self.wda.screenshot_b64())))

    def read(self):
        return self.ocr.ocr(self._shot())

    def screenshot_png(self):
        return base64.b64decode(self.wda.screenshot_b64())

    def swipe(self, move):
        dx, dy = SWIPE_DIR[move]
        cx, cy = self.centre
        self.wda.drag(cx, cy, cx + dx * self.dist, cy + dy * self.dist)

    def submit_name(self, name):
        # Threes on iOS submits to Game Center under the signed-in Apple ID, not an
        # in-game field. Only type a name if a --name-tap field location was given.
        if not self.name_tap:
            print("submit_name: no --name-tap; Game Center uses the signed-in Apple ID "
                  f"(set the nickname to '{name}')", flush=True)
            return
        x, y = (float(v) for v in self.name_tap.split(","))
        self.wda.tap(x, y)
        self.wda.type_text(name)

    def restart(self):
        if self.restart_tap:
            x, y = (float(v) for v in self.restart_tap.split(","))
            self.wda.tap(x, y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="key into android/ocr/devices.py CONFIGS")
    ap.add_argument("--wda", default="http://localhost:8100", help="WebDriverAgent base URL")
    ap.add_argument("--scale", type=float, default=3.0, help="device pixel scale (3 modern, 2 older/SE)")
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--move-delay", type=float, default=0.25)
    ap.add_argument("--max-moves", type=int, default=4000)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--depth-cap", type=int, default=5)
    ap.add_argument("--record-dir", default="", help="keep the best game's replay+screenshot here")
    ap.add_argument("--player-name", default="", help="leaderboard name (Github halfrost)")
    ap.add_argument("--restart-tap", default="", help="'x,y' (points) of the new-game button")
    ap.add_argument("--name-tap", default="", help="'x,y' (points) of an in-game name field, if any")
    ap.add_argument("--self-test", action="store_true", help="run the full flow offline (engine device)")
    ap.add_argument("--dry-run", action="store_true", help="just check the moveserver")
    ap.add_argument("--dbg", action="store_true")
    a = ap.parse_args()
    a.platform = "ios"
    if a.dry_run:
        dry_run(a.server)
    elif a.self_test:
        run_scoring(EngineDevice(seed=1, player=a.player_name or "self-test"), a)
    elif not a.model:
        ap.error("--model is required (or use --dry-run / --self-test)")
    else:
        run_scoring(WdaDevice(a.model, a.wda, a.scale, a.restart_tap, a.name_tap), a)


if __name__ == "__main__":
    main()
