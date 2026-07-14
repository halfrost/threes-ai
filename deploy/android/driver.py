"""Android scoring driver (Phase 4): drive the real Threes app via ADB.

Loop (shared with iOS/web via deploy/mobile_core): `adb screencap` -> OCR the
board+next with the repo's exemplar matcher (android/ocr) -> ask the Go moveserver
-> `adb input swipe` -> record the ply -> repeat; keep the best game's replay
(plays in web/replay.html) + its game-over screenshot.

Reuses:
  - android/ocr        exemplar OCR (screenshot -> 4x4 indices + next-tile set).
                       Needs a CONFIGS['<model>'] entry in android/ocr/devices.py
                       and a one-time exemplar bootstrap (prompts for unknowns).
  - deploy/common.py   moveserver client + DeckTracker + tile maps.
  - deploy/recorder.py replay + best-keeper (same schema as web/iOS).
  - deploy/mobile_core the shared play loop, best-keeping, and the --self-test.

Swipe geometry is derived from the SAME OCR config (x0,y0,dx,dy).

Setup:
  adb devices                     # confirm the emulator/phone is attached
  pip install pillow numpy
  # add a CONFIGS['<model>'] entry (screen + tile geometry) in android/ocr/devices.py
Run:
  go run ../../cmd/moveserver -addr :9010 -deckaware &
  python driver.py --dry-run                       # brain only, no device
  python driver.py --self-test --record-dir /tmp/at   # full flow, engine stands in
  python driver.py --model 'Pixel_7_API_34' --serial emulator-5554 \
      --player-name 'Github halfrost' --record-dir ../../results/replays/android
"""
from __future__ import annotations
import argparse
import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))          # deploy/*
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))    # repo root -> android.ocr
from mobile_core import run_scoring, dry_run, EngineDevice  # noqa: E402

SWIPE_DIR = {0: (0, -1), 1: (0, 1), 2: (-1, 0), 3: (1, 0)}  # UP DOWN LEFT RIGHT


class AdbDevice:
    """A mobile_core Device backed by adb: screencap+OCR to read, input swipe to move."""
    def __init__(self, model, serial, restart_tap="", name_tap=""):
        from android.ocr import OCR
        from android.ocr.devices import CONFIGS
        if model not in CONFIGS:
            sys.exit(f"no CONFIGS['{model}'] in android/ocr/devices.py — add screen+tile geometry first")
        self.cfg = CONFIGS[model]
        self.ocr = OCR(model)
        self.serial = serial
        self.restart_tap = restart_tap
        self.name_tap = name_tap
        cx = self.cfg.x0 + 1.5 * self.cfg.dx + self.cfg.w / 2
        cy = self.cfg.y0 + 1.5 * self.cfg.dy + self.cfg.h / 2
        self.centre = (cx, cy)
        self.dist = 1.2 * min(self.cfg.dx, self.cfg.dy)

    def _adb(self, *args, capture=False):
        base = ["adb"] + (["-s", self.serial] if self.serial else [])
        return subprocess.run(base + list(args), capture_output=capture, check=True)

    def _screencap(self):
        from PIL import Image
        png = self._adb("exec-out", "screencap", "-p", capture=True).stdout
        return Image.open(io.BytesIO(png))

    def read(self):
        return self.ocr.ocr(self._screencap())        # (board_idx|None, tileset|None)

    def screenshot_png(self):
        return self._adb("exec-out", "screencap", "-p", capture=True).stdout

    def swipe(self, move, duration_ms=60):
        dx, dy = SWIPE_DIR[move]
        cx, cy = self.centre
        self._adb("shell", "input", "swipe", str(int(cx)), str(int(cy)),
                  str(int(cx + dx * self.dist)), str(int(cy + dy * self.dist)), str(duration_ms))

    def tap(self, x, y):
        self._adb("shell", "input", "tap", str(int(x)), str(int(y)))

    def submit_name(self, name):
        # Most Threes builds submit under the Google Play Games account, not an
        # in-game field. Only type a name if a --name-tap field location was given.
        if not self.name_tap:
            print("submit_name: no --name-tap; leaderboard uses the Play Games account "
                  f"(set it to '{name}' on the device)", flush=True)
            return
        x, y = (float(v) for v in self.name_tap.split(","))
        self.tap(x, y)
        self._adb("shell", "input", "text", name.replace(" ", "%s"))

    def restart(self):
        if self.restart_tap:
            x, y = (float(v) for v in self.restart_tap.split(","))
            self.tap(x, y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="key into android/ocr/devices.py CONFIGS")
    ap.add_argument("--serial", default="", help="adb device serial (e.g. emulator-5554)")
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--move-delay", type=float, default=0.25)
    ap.add_argument("--max-moves", type=int, default=4000)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--depth-cap", type=int, default=5)
    ap.add_argument("--record-dir", default="", help="keep the best game's replay+screenshot here")
    ap.add_argument("--player-name", default="", help="leaderboard name (Github halfrost)")
    ap.add_argument("--restart-tap", default="", help="'x,y' of the new-game button for multi-game runs")
    ap.add_argument("--name-tap", default="", help="'x,y' of an in-game name field, if the build has one")
    ap.add_argument("--self-test", action="store_true", help="run the full flow offline (engine device)")
    ap.add_argument("--dry-run", action="store_true", help="just check the moveserver")
    ap.add_argument("--dbg", action="store_true")
    a = ap.parse_args()
    a.platform = "android"
    if a.dry_run:
        dry_run(a.server)
    elif a.self_test:
        run_scoring(EngineDevice(seed=1, player=a.player_name or "self-test"), a)
    elif not a.model:
        ap.error("--model is required (or use --dry-run / --self-test)")
    else:
        run_scoring(AdbDevice(a.model, a.serial, a.restart_tap, a.name_tap), a)


if __name__ == "__main__":
    main()
