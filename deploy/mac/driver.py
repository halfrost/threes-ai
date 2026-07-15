"""macOS scoring driver: drive the Threes iOS app running on Apple Silicon.

Apple-Silicon Macs run iPhone/iPad apps natively (the app lives in a `.../Wrapper/
Threes.app`). This driver treats that window like any other Device (see
deploy/mobile_core): capture the window -> read the board -> ask the Go moveserver
-> swipe -> record the best game (replay + settlement shot), same standard as the
web/Android/iOS drivers.

Board reading is ENGINE-IN-THE-LOOP (Threes' handwritten font defeats tesseract):
the board is read by tile COLOUR (1=blue, 2=red, >=3=white, empty=teal) — exact for
the low tiles — and the true board is tracked with the Threes engine
(rl/threes_env.apply_move). High tiles are never OCR'd; after each swipe the only
thing read off the screen is WHERE the new tile spawned (its value is the tile that
was previewed as "next"). Colours of the low tiles are re-checked every move to
catch desync.

Capture uses `screencapture -l<windowID>` (needs **Screen Recording**). Input is a
`cliclick` mouse-drag swipe (needs **Accessibility**). Grant both to the app running
this script (Terminal / iTerm / the IDE) in System Settings -> Privacy & Security.

Setup:
  pip install pyobjc-framework-Quartz    # window lookup (SSL_CERT_FILE=~/.threes-ca.pem)
  brew install cliclick
Run:
  ./bin/moveserver -addr :9010 -deckaware &
  python3 driver.py --calibrate /tmp/shot.png            # one frame to eyeball
  python3 driver.py --player-name 'Github halfrost' --record-dir ../../results/replays/mac
"""
from __future__ import annotations
import argparse
import io
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))          # deploy/*
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))    # repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "rl"))
from mobile_core import run_scoring, dry_run, EngineDevice  # noqa: E402
from threes_env import apply_move  # noqa: E402

# Board tile-centre geometry in the 2x window capture (px). Calibrated from a
# 1024x796-pt window; SCALE converts capture px -> screen points for the swipe.
X0, DX, Y0, DY = 732.0, 194.7, 538.0, 252.3
NEXT_XY = (1020, 220)
SCALE = 2
KEY_CODE = {0: 126, 1: 125, 2: 123, 3: 124}                    # UP DOWN LEFT RIGHT arrow keys
EDGE = {0: [(3, c) for c in range(4)], 1: [(0, c) for c in range(4)],
        2: [(r, 3) for r in range(4)], 3: [(r, 0) for r in range(4)]}


def find_window(owner="Threes"):
    """(window_id, x, y, w, h) of the app's largest on-screen window, in POINTS,
    via CoreGraphics — reliable, permission-free geometry (System Events reports a
    bogus size for iOS-app-on-Mac windows)."""
    import Quartz
    wl = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    hits = [w for w in wl
            if owner.lower() in (w.get("kCGWindowOwnerName", "") or "").lower()
            and w.get("kCGWindowLayer", 0) == 0]
    if not hits:
        raise RuntimeError(f"no on-screen window for '{owner}' — is the app open and un-minimized?")
    w = max(hits, key=lambda w: w["kCGWindowBounds"]["Height"])
    b = w["kCGWindowBounds"]
    return (w["kCGWindowNumber"], int(b["X"]), int(b["Y"]), int(b["Width"]), int(b["Height"]))


def _classify(rgb):
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    mx, mn = max(r, g, b), min(r, g, b)
    if r > 232 and g > 232 and b > 228:
        return 3                      # white tile (>=3)
    if b > 150 and b - r > 25 and r < 175:
        return 1                      # blue = 1
    if r > 190 and r - g > 55 and r - b > 35:
        return 2                      # red = 2
    if mx - mn < 40 and 170 < g < 228:
        return 0                      # empty teal cell
    return -1                         # unknown (page / gap)


def _median(npim, cx, cy, rw=55, rh=80):
    import numpy as np
    return np.median(npim[cy - rh:cy + rh, cx - rw:cx + rw].reshape(-1, 3), axis=0)


def read_shape(npim):
    """4x4 of colour classes: 0 empty, 1 blue, 2 red, 3 white(>=3), -1 unknown."""
    out = []
    for r in range(4):
        row = []
        for c in range(4):
            cx, cy = int(X0 + c * DX), int(Y0 + r * DY)
            row.append(_classify(_median(npim, cx, cy)))
        out.append(row)
    return out


def read_next(npim):
    """The previewed next tile value 1/2/3 by colour (0 if unreadable/bonus)."""
    cls = _classify(_median(npim, NEXT_XY[0], NEXT_XY[1], 35, 45))
    return cls if cls in (1, 2, 3) else 0


class MacThreesDevice:
    """Engine-in-the-loop Device driving the Threes app window on macOS."""
    def __init__(self, owner="Threes", region=None, move_delay=0.45, dbg=False):
        self.owner, self.region, self.move_delay, self.dbg = owner, region, move_delay, dbg
        self.desyncs = 0
        self.over = False
        self._activate()
        npim = self._capture_np()
        shape = read_shape(npim)
        # Seed the tracked board. White cells are 3 at this point (a game that has
        # only ever seen 1/2/3 so far); higher tiles are then tracked by the engine.
        self.board = [[shape[r][c] if shape[r][c] >= 0 else 0 for c in range(4)] for r in range(4)]
        self.next = read_next(npim) or 1

    # --- capture -----------------------------------------------------------
    def _win(self):
        if self.region:
            return (None, *self.region)
        return find_window(self.owner)

    def _capture_png_bytes(self):
        wid, x, y, w, h = self._win()
        fd, path = __import__("tempfile").mkstemp(suffix=".png")
        os.close(fd)
        if wid is not None:
            subprocess.run(["screencapture", "-x", "-o", "-l", str(wid), path], check=True)
        else:
            subprocess.run(["screencapture", "-x", "-o", "-R", f"{x},{y},{w},{h}", path], check=True)
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
        return data

    def _capture_np(self):
        import numpy as np
        from PIL import Image
        return np.asarray(Image.open(io.BytesIO(self._capture_png_bytes())).convert("RGB")).astype(int)

    def screenshot_png(self):
        return self._capture_png_bytes()

    # --- Device interface --------------------------------------------------
    def _legal(self):
        return [a for a in range(4) if apply_move(self.board, a)[2]]

    def read(self):
        if self.over or not self._legal():
            return None, None
        return [row[:] for row in self.board], [self.next]

    def _activate(self):
        subprocess.run(["osascript", "-e",
                        f'tell application "System Events" to set frontmost of process "{self.owner}" to true'],
                       capture_output=True)

    def swipe(self, move):
        # Threes-on-Mac takes arrow keys (a mouse-drag swipe does NOT register).
        # Keys go to the frontmost app, so keep the game focused. A legal move
        # always changes the visible board (it slides a tile AND spawns one), so we
        # confirm the key landed by the shape changing — and re-send if it didn't
        # (a dropped keystroke is the main failure mode, and it silently desyncs
        # the engine-tracked board). The generous delay makes "unchanged" mean
        # "dropped", not "captured mid-animation" (which would double-move).
        pre = read_shape(self._capture_np())
        npim, shape, registered = None, pre, False
        for _ in range(4):
            self._activate()
            time.sleep(0.12)
            subprocess.run(["osascript", "-e",
                            f'tell application "System Events" to key code {KEY_CODE[move]}'], check=True)
            time.sleep(self.move_delay)
            npim = self._capture_np()
            shape = read_shape(npim)
            if shape != pre:
                registered = True
                break
        if not registered:
            # a legal move always changes the board; 4 tries with no change means the
            # real game is over (its game-over screen ignores keys). Stop cleanly.
            self.over = True
            return
        # Update the tracked board = engine slide/merge, then RE-SYNC every cell's
        # shape from the screen so nothing can drift: empties, blue(1), red(2) and
        # the spawned tile all come from the screen (exact); only a white tile's
        # VALUE (3 vs 6 vs 12...) comes from the engine, since colour can't tell
        # them apart. Starting from a fresh game (all 1/2/3) the engine's merges are
        # correct, and re-syncing the shape each move keeps them correct.
        nb, changed, moved = apply_move(self.board, move)
        if not moved:
            nb = [row[:] for row in self.board]
        mis = 0
        for r in range(4):
            for c in range(4):
                s = shape[r][c]
                # real desync = the engine HAD a tile here whose colour disagrees
                # with the screen (spawns, where the engine cell was empty, don't
                # count — they are expected and simply filled in from the screen).
                exp = 0 if nb[r][c] == 0 else (nb[r][c] if nb[r][c] in (1, 2) else 3)
                if s >= 0 and nb[r][c] != 0 and s != exp:
                    mis += 1
                if s == 0:
                    nb[r][c] = 0
                elif s in (1, 2):
                    nb[r][c] = s
                elif s == 3 and nb[r][c] < 3:
                    nb[r][c] = 3
        self.board = nb
        self.next = read_next(npim) or self.next
        self.desyncs += 1 if mis else 0
        if self.dbg:
            print(f"    [dbg] move={move} next={self.next} desync={mis}",
                  file=sys.stderr, flush=True)

    def submit_name(self, name):
        print(f"submit_name: Threes submits to Game Center under the signed-in Apple ID "
              f"(set the nickname to '{name}')", flush=True)

    def _seed(self):
        npim = self._capture_np()
        shape = read_shape(npim)
        self.board = [[shape[r][c] if shape[r][c] >= 0 else 0 for c in range(4)] for r in range(4)]
        self.next = read_next(npim) or 1

    def restart(self):
        """Start a fresh game with NO mouse. The app ignores synthetic mouse
        clicks (so the game-over "retry" button is untappable), but it DOES take
        synthetic keys — and relaunching shows the start menu whose "PLAY THREES"
        fires on the RETURN key. So: kill -> relaunch -> Return -> a brand-new game."""
        subprocess.run(["pkill", "-9", "-f", "Wrapper/Threes.app/Threes"], check=False)
        time.sleep(2.5)
        subprocess.run(["open", "-b", "vo.threes.exclaim"], check=False)
        time.sleep(9)                       # launch + menu render (needs a beat)
        for _ in range(6):                  # Return -> PLAY THREES (retry until it takes)
            self._activate()
            time.sleep(0.6)
            subprocess.run(["osascript", "-e",
                            'tell application "System Events" to key code 36'], check=False)
            time.sleep(2.0)
            shape = read_shape(self._capture_np())
            filled = sum(1 for r in range(4) for c in range(4) if shape[r][c] > 0)
            empties = sum(1 for r in range(4) for c in range(4) if shape[r][c] == 0)
            lows = sum(1 for r in range(4) for c in range(4) if shape[r][c] in (1, 2))
            # A real fresh game has blue(1)/red(2) tiles; the start MENU's decorative
            # board is all white (3..768), so require some low tiles to tell them apart.
            if 6 <= filled <= 11 and empties >= 3 and lows >= 2:
                break
        self._seed()


def calibrate(path, owner, region):
    if region:
        x, y, w, h = region
        subprocess.run(["screencapture", "-x", "-o", "-R", f"{x},{y},{w},{h}", path], check=True)
    else:
        wid, x, y, w, h = find_window(owner)
        subprocess.run(["screencapture", "-x", "-o", "-l", str(wid), path], check=True)
    print(f"saved {path}  (window {w}x{h} pt at {x},{y})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="Threes", help="app process name for window lookup")
    ap.add_argument("--region", default="", help="'x,y,w,h' points, overrides window auto-detect")
    ap.add_argument("--server", default="http://127.0.0.1:9010")
    ap.add_argument("--move-delay", type=float, default=0.45)
    ap.add_argument("--max-moves", type=int, default=4000)
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--depth-cap", type=int, default=5)
    ap.add_argument("--record-dir", default="")
    ap.add_argument("--player-name", default="")
    ap.add_argument("--calibrate", default="", help="save one window screenshot and exit")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-restart", action="store_true",
                    help="play the game already on screen (don't kill+relaunch to start fresh)")
    ap.add_argument("--dbg", action="store_true")
    a = ap.parse_args()
    a.platform = "mac"
    region = tuple(int(v) for v in a.region.split(",")) if a.region else None
    if a.dry_run:
        dry_run(a.server)
    elif a.calibrate:
        calibrate(a.calibrate, a.owner, region)
    elif a.self_test:
        run_scoring(EngineDevice(seed=1, player=a.player_name or "self-test"), a)
    else:
        from common import MoveClient, DeckTracker  # noqa: E402
        from recorder import GameRecorder, BestKeeper  # noqa: E402
        from mobile_core import play_one_game  # noqa: E402
        mc = MoveClient(a.server)
        print("moveserver:", mc.ping(), flush=True)
        dev = MacThreesDevice(a.owner, region, a.move_delay, a.dbg)
        keeper = BestKeeper(a.record_dir) if a.record_dir else None
        for g in range(a.games):
            # (Re)start until we actually get a live game: a run that ends in < 10
            # moves means the menu->game start didn't take (the app briefly ignores
            # the Return that fires PLAY THREES), so restart and try again.
            for attempt in range(1 if a.no_restart else 8):
                if a.no_restart:
                    dev.over = False
                    dev._seed()                 # play whatever game is on screen now
                else:
                    dev.restart()
                deck = DeckTracker()
                rec = GameRecorder(agent="mac-threes-expectimax", depth_cap=a.depth_cap)
                score, best_tile, moves = play_one_game(dev, mc, deck, rec, a.move_delay,
                                                        a.max_moves, a.dbg)
                if a.no_restart or moves >= 10:
                    break
                print(f"  start didn't take ({moves} moves) — retry {attempt+1}", flush=True)
            from common import VALUE  # noqa: E402
            print("final tracked board:", [[VALUE[i] for i in row] for row in dev.board],
                  flush=True)
            time.sleep(1.5)                      # let the game-over screen render
            shot = None
            try:
                shot = dev.screenshot_png()      # the real settlement screen
            except Exception:                    # noqa: BLE001
                shot = None
            msg = (f"game {g+1}/{a.games}: {moves} moves, max {best_tile}, "
                   f"score {score}, desync {dev.desyncs}")
            if keeper:
                saved, _, best = keeper.consider(rec.replay_dict(), shot)
                msg += f" | best {best}" + (" -> NEW BEST saved" if saved else "")
            print(msg, flush=True)


if __name__ == "__main__":
    main()
