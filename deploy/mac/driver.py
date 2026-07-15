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
from common import VALUE  # noqa: E402

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


def _glyph(npim, cx, cy):
    """Normalised digit glyph of the tile centred at (cx,cy): the number region
    (above the monster face), colour-agnostic ink (any non-white pixel — some big
    tiles render the number in pink), resized to a fixed 48x40 for matching."""
    import numpy as np
    from PIL import Image
    crop = npim[cy - 70:cy + 40, cx - 72:cx + 72]
    ink = (~((crop[:, :, 0] > 228) & (crop[:, :, 1] > 228) & (crop[:, :, 2] > 228))).astype("uint8") * 255
    return np.asarray(Image.fromarray(ink).resize((48, 40))) / 255.0


_GLYPH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glyphs")


class TileTemplates:
    """Nearest-glyph matcher for white-tile values (INDEX 3=3 .. 15=12288). Keeps a
    FEW exemplars per value (per-cell alignment wobbles a little, so >1 exemplar
    keeps within-value distance below the between-value gap). Verified separation:
    same value ~0.10, different ~0.23+, so 0.15 is a safe threshold. A pre-built
    library on disk (deploy/mac/glyphs) is loaded at start so any board — even a
    resumed deep one — reads exactly; new values seen mid-game are learned from the
    engine's (deterministic merge) value and persisted, so the library keeps
    filling in across runs."""
    THRESH = 0.15
    MAX_PER = 6

    def __init__(self, load=True):
        self.t = {}                     # index -> list of glyphs
        if load:
            self.load()

    def learn(self, idx, g):
        import numpy as np
        if idx < 3:
            return
        lst = self.t.setdefault(idx, [])
        if len(lst) < self.MAX_PER and all(float(np.abs(g - e).mean()) > 0.04 for e in lst):
            lst.append(g)

    def match(self, g):
        import numpy as np
        best_i, best_d = None, 1e9
        for i, lst in self.t.items():
            for e in lst:
                d = float(np.abs(g - e).mean())
                if d < best_d:
                    best_d, best_i = d, i
        return (best_i, best_d) if best_i is not None else (None, 1.0)

    def load(self, d=_GLYPH_DIR):
        import numpy as np
        if not os.path.isdir(d):
            return
        for fn in os.listdir(d):
            if fn.endswith(".npy"):
                idx = int(fn[:-4])
                arr = np.load(os.path.join(d, fn))      # (N,40,48)
                self.t[idx] = [arr[k] for k in range(arr.shape[0])]

    def save(self, d=_GLYPH_DIR):
        import numpy as np
        os.makedirs(d, exist_ok=True)
        for idx, lst in self.t.items():
            if lst:
                np.save(os.path.join(d, f"{idx}.npy"), np.stack(lst))


class MacThreesDevice:
    """Engine-in-the-loop Device driving the Threes app window on macOS."""
    def __init__(self, owner="Threes", region=None, move_delay=0.45, dbg=False):
        self.owner, self.region, self.move_delay, self.dbg = owner, region, move_delay, dbg
        self.desyncs = 0
        self.noops = 0          # consecutive non-registering moves (desync/wedge guard)
        self.over = False
        self.tmpl = TileTemplates()
        self._activate()
        npim, _ = self._stable_np()
        # Seed the tracked board via colour + glyph templates (white cells are 3 at a
        # fresh start; higher tiles get learned as they are first created).
        self.board, _ = self._exact_board(npim)
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

    def _stable_np(self, tries=12, gap=0.07):
        """Capture until the colour grid is identical on two consecutive frames —
        i.e. the slide/merge animation has SETTLED. This is what keeps late-game
        reads honest: a full board triggers long merge cascades whose mid-animation
        frames otherwise look like phantom tiles (the bug that cascaded a clean
        180-move game into garbage). Returns (npim, shape) of the settled frame."""
        img = self._capture_np()
        prev = read_shape(img)
        for _ in range(tries):
            time.sleep(gap)
            img2 = self._capture_np()
            cur = read_shape(img2)
            if cur == prev and -1 not in (v for row in cur for v in row):
                return img2, cur
            img, prev = img2, cur
        return img, prev

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

    def _screen_xy(self, cap_x, cap_y):
        """Capture-pixel (x,y) -> absolute screen point, using the live window origin."""
        _, wx, wy, _, _ = self._win()
        return wx + cap_x / SCALE, wy + cap_y / SCALE

    def _mouse(self, kind, x, y):
        import Quartz
        ev = Quartz.CGEventCreateMouseEvent(None, kind, (x, y), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    def _drag_swipe(self, move):
        """Play a move as a real mouse SWIPE (a CGEvent drag with intermediate
        MouseDragged points). This is what actually drives Threes-on-Mac: the app
        ignores synthetic ARROW KEYS unless the window holds genuine keyboard
        first-responder (which a synthetic app-launch/menu-click never grants), but it
        honours a synthetic mouse drag regardless of focus. 0=UP 1=DOWN 2=LEFT 3=RIGHT."""
        import Quartz
        cx, cy = self._screen_xy(X0 + 1.5 * DX, Y0 + 1.5 * DY)     # board centre
        d = 150
        vx, vy = {0: (0, -d), 1: (0, d), 2: (-d, 0), 3: (d, 0)}[move]
        self._mouse(Quartz.kCGEventMouseMoved, cx, cy); time.sleep(0.03)
        self._mouse(Quartz.kCGEventLeftMouseDown, cx, cy); time.sleep(0.03)
        steps = 14
        for i in range(1, steps + 1):
            self._mouse(Quartz.kCGEventLeftMouseDragged, cx + vx * i / steps, cy + vy * i / steps)
            time.sleep(0.012)
        self._mouse(Quartz.kCGEventLeftMouseUp, cx + vx, cy + vy); time.sleep(0.03)

    def _click(self, cap_x, cap_y):
        """A real synthetic left click at a capture-pixel location (menu / retry
        buttons DO honour synthetic clicks, unlike arrow keys)."""
        import Quartz
        x, y = self._screen_xy(cap_x, cap_y)
        self._mouse(Quartz.kCGEventMouseMoved, x, y); time.sleep(0.05)
        self._mouse(Quartz.kCGEventLeftMouseDown, x, y); time.sleep(0.05)
        self._mouse(Quartz.kCGEventLeftMouseUp, x, y); time.sleep(0.05)

    def _exact_board(self, npim, engine_board=None):
        """Read the EXACT board (indices) from the screen: colour for empty/1/2, and
        for white tiles a fixed-font glyph TEMPLATE MATCH -> exact value (3..12288),
        so nothing drifts. A white tile whose glyph isn't in the library yet is
        labelled from the engine's (deterministic merge) value and its glyph learned,
        so the library fills itself in as new tiles are first created. Returns
        (board_indices, colour_shape)."""
        shape = read_shape(npim)
        board = [[0] * 4 for _ in range(4)]
        for r in range(4):
            for c in range(4):
                s = shape[r][c]
                if s in (1, 2):
                    board[r][c] = s
                elif s == 3:                                   # white, value >= 3
                    g = _glyph(npim, int(X0 + c * DX), int(Y0 + r * DY))
                    idx, d = self.tmpl.match(g)
                    if idx is not None and d < TileTemplates.THRESH:
                        board[r][c] = idx                      # exact, screen-anchored
                    else:
                        ev = engine_board[r][c] if engine_board else 0
                        idx2 = ev if ev >= 3 else 3            # engine value, or a 3 at game start
                        board[r][c] = idx2
                        self.tmpl.learn(idx2, g)
                elif s == -1 and engine_board:
                    board[r][c] = engine_board[r][c]           # unreadable frame -> trust engine
        return board, shape

    def swipe(self, move):
        # Threes-on-Mac takes arrow keys (a mouse-drag swipe does NOT register).
        # Keys go to the frontmost app, so keep the game focused. A legal move always
        # changes the visible board (it slides a tile AND spawns one), so we confirm
        # the key landed by the colour grid changing — and re-send if it didn't (a
        # dropped keystroke is the main failure mode). The generous delay makes
        # "unchanged" mean "dropped", not "captured mid-animation" (a double-move).
        #
        # BOARD TRACKING — engine-trusted, spawn-anchored (the key to accuracy):
        # `apply_move` gives the EXACT slide/merge of the existing tiles
        # (deterministic — a merge's value is fixed), so we never glyph-read high
        # tiles (that was the old drift source: 12/24/48/96 confuse the matcher). The
        # only new information on screen after a move is the single SPAWNED tile;
        # its value is exactly the `next` we previewed BEFORE the move (always a
        # 1/2/3, colour-coded — or a bonus, handled below). So: engine board + read
        # the screen only to place that one spawn and confirm the move.
        _, pre = self._stable_np()           # settled colour grid BEFORE the move
        nv = self.next                       # previewed next = the tile that spawns now
        npim, shape, registered = None, pre, False
        for _ in range(4):
            self._drag_swipe(move)           # mouse SWIPE (arrow keys need genuine focus)
            time.sleep(self.move_delay)
            npim, shape = self._stable_np()  # wait for the slide/merge to SETTLE
            if shape != pre:
                registered = True
                break
        if not registered:
            # The swipe didn't change the screen. Re-read the true board off the
            # settled frame, then decide game-over by the REAL rule: in Threes a game
            # is over ONLY when the board is completely FULL (16 tiles) with no
            # mergeable pair. With ANY empty cell a slide is always legal, so a no-op
            # there is a read/move glitch to recover from (re-sync + let the next loop
            # re-ask), NOT a dead game — the endgame false-over that used to stop us a
            # few moves short of the real settlement screen. noops>=30 is a wedge
            # backstop only (mouse swipes are reliable, so this rarely bites).
            fresh, _ = self._stable_np()
            self.board, _ = self._exact_board(fresh)
            self.next = read_next(fresh) or self.next
            filled = sum(1 for r in range(4) for c in range(4) if self.board[r][c] > 0)
            self.noops += 1
            if (filled == 16 and not self._legal()) or self.noops >= 30:
                self.over = True
            return
        # Engine slide/merge of the existing tiles (exact), then place the one spawn.
        nb, changed, moved = apply_move(self.board, move)
        if not moved:
            nb = [row[:] for row in self.board]
        # The spawn = the cell that is EMPTY in the engine's post-slide board but
        # filled on screen. (Merges free cells; the set difference isolates the spawn.)
        spawns = [(r, c) for r in range(4) for c in range(4)
                  if nb[r][c] == 0 and shape[r][c] in (1, 2, 3)]
        if len(spawns) == 1:
            r, c = spawns[0]
            col = shape[r][c]
            if col in (1, 2):
                nb[r][c] = col               # low spawn: the colour IS the value
            elif nv >= 3:
                nb[r][c] = nv                # white/bonus spawn: use the preview value
            else:
                g = _glyph(npim, int(X0 + c * DX), int(Y0 + r * DY))
                idx, d = self.tmpl.match(g)  # bonus spawn w/ no readable preview: read it
                nb[r][c] = idx if (idx is not None and d < TileTemplates.THRESH) else 3
        # Occupancy check: do the engine's filled cells match the screen's? (colour-
        # based, robust). If the spawn count was wrong OR occupancy drifted, the
        # engine board diverged — RESYNC from the settled screen via a full glyph
        # read so a single miss can't cascade (the failure mode that ate game 3).
        occ = sum(1 for r in range(4) for c in range(4)
                  if (nb[r][c] > 0) != (shape[r][c] in (1, 2, 3)))
        if len(spawns) != 1 or occ:
            nb, _ = self._exact_board(npim, nb)
            occ = sum(1 for r in range(4) for c in range(4)
                      if (nb[r][c] > 0) != (shape[r][c] in (1, 2, 3)))
        self.board = nb
        self.next = read_next(npim) or nv
        self.noops = 0                       # a move landed -> clear the wedge counter
        self.desyncs += 1 if occ else 0
        if self.dbg:
            mx = max(max(row) for row in nb)
            print(f"    [dbg] move={move} nv={nv} spawn={len(spawns)} resync={'Y' if (len(spawns)!=1 or occ) else 'n'} "
                  f"occ_mis={occ} maxtile={VALUE[mx] if mx in VALUE else mx}", file=sys.stderr, flush=True)

    def submit_name(self, name):
        print(f"submit_name: Threes submits to Game Center under the signed-in Apple ID "
              f"(set the nickname to '{name}')", flush=True)

    def _seed(self):
        npim, _ = self._stable_np()                 # settled frame, so the seed is exact
        self.board, _ = self._exact_board(npim)     # colour + glyph templates; learns fresh 3s
        self.next = read_next(npim) or 1

    def restart(self):
        """Start a fresh game with the MOUSE. The app honours synthetic CLICKS on the
        menu / game-over buttons but ignores synthetic ARROW KEYS unless the window
        holds genuine keyboard focus (a synthetic launch never grants it) — so we both
        play AND restart via mouse. Click 'retry' on a game-over screen (starts a new
        game directly, no relaunch) or 'PLAY THREES' on the start menu, and verify a
        fresh low-tile board appeared. Hard reset (kill+relaunch) only as a fallback."""
        RETRY_XY = (685, 200)              # game-over 'retry' button (capture px)
        PLAY_XY = (1000, 1340)             # start-menu 'PLAY THREES' button (capture px)

        def is_fresh():
            shape = self._stable_np()[1]
            filled = sum(1 for r in range(4) for c in range(4) if shape[r][c] > 0)
            empties = sum(1 for r in range(4) for c in range(4) if shape[r][c] == 0)
            lows = sum(1 for r in range(4) for c in range(4) if shape[r][c] in (1, 2))
            # a live game has blue(1)/red(2) tiles; the menu/game-over polaroid boards
            # are all-white decoration, so require some low tiles to tell them apart.
            return 6 <= filled <= 11 and empties >= 3 and lows >= 2

        for attempt in range(6):
            if is_fresh():
                break
            self._click(*RETRY_XY); time.sleep(2.0)   # game-over -> retry
            if is_fresh():
                break
            self._click(*PLAY_XY); time.sleep(2.0)    # start menu -> PLAY THREES
            if is_fresh():
                break
            if attempt == 3:                            # last resort: hard reset
                subprocess.run(["pkill", "-9", "-f", "Wrapper/Threes.app/Threes"], check=False)
                time.sleep(2.5)
                subprocess.run(["open", "-b", "vo.threes.exclaim"], check=False)
                time.sleep(9)
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
            dev.tmpl.save()             # persist glyphs learned this game (grows across runs)
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
