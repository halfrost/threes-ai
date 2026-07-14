"""Shared core for the Android (ADB) and iOS (WebDriverAgent) scoring drivers.

Same standard as the web drivers (see deploy/web): drive the real Threes app with
the Go moveserver, record the best game as an `engine/replay.go` replay that plays
in `web/replay.html`, keep only the highest-scoring game (best.json + a game-over
screenshot), and — where the app exposes it — enter the leaderboard name. The
Android and iOS drivers differ only in the transport (adb vs WDA); everything
below is shared.

A `Device` is duck-typed:
    read()            -> (board_idx 4x4 | None if game over, next_tileset | None)
    swipe(move:int)                       # 0=UP 1=DOWN 2=LEFT 3=RIGHT
    screenshot_png()  -> bytes | None     # for the settlement shot (optional)
    submit_name(name)                     # optional (most builds use the OS account)
    restart()                             # optional (start the next game)

`EngineDevice` implements that interface on top of the Python Threes engine, so the
whole flow can be exercised offline (`--self-test`) with no phone attached — the
engine stands in for the device, and the same moveserver/recorder/best-keeper path
runs end to end.
"""
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))          # deploy/
from common import MoveClient, DeckTracker, to_values, MOVE_NAME, VALUE  # noqa: E402
from recorder import GameRecorder, BestKeeper  # noqa: E402


def play_one_game(dev, mc, deck, rec, move_delay=0.25, max_moves=4000, dbg=False):
    """One game: read board -> ask moveserver -> swipe -> record, until game over.
    The board read each step is the board BEFORE the move, exactly what the replay
    recorder wants. Game over = the device reports no board, or moveserver returns
    -1 (no legal move). Returns (score, best_tile, moves)."""
    last_board = [[0] * 4 for _ in range(4)]
    best_tile = 0
    for step in range(max_moves):
        board_idx, tileset = dev.read()
        if board_idx is None:
            break
        board = to_values([list(r) for r in board_idx])
        last_board = board
        best_tile = max(best_tile, max(v for row in board for v in row))
        nset = [VALUE[i] for i in tileset] if tileset else None
        nv = nset[0] if (nset and len(nset) == 1 and nset[0] in (1, 2, 3)) else 0
        move = mc.ask(board, next_set=nset, deck=deck.remaining())
        if move < 0:
            break
        rec.record(board, nv, move)          # board BEFORE + previewed next + move
        if nv in (1, 2, 3):
            deck.note(nv)
        if dbg and step % 20 == 0:
            print(f"    move {step}: max {best_tile} score {rec.final_score()} "
                  f"next {nv} {MOVE_NAME[move]}", flush=True)
        dev.swipe(move)
        if move_delay:
            time.sleep(move_delay)
    rec.finish(last_board)
    return rec.final_score(), best_tile, max(0, len(rec.steps) - 1)


def run_scoring(dev, a):
    """Multi-game scoring loop with best-keeping + settlement screenshot, shared by
    both mobile drivers. `a` supplies server, games, depth_cap, move_delay,
    max_moves, record_dir, player_name, platform."""
    mc = MoveClient(a.server)
    print("moveserver:", mc.ping(), flush=True)
    if getattr(a, "player_name", "") and hasattr(dev, "submit_name"):
        try:
            dev.submit_name(a.player_name)      # enter the leaderboard name if the build has a field
        except Exception as e:                  # noqa: BLE001
            print(f"submit_name skipped: {e}", flush=True)
    keeper = BestKeeper(a.record_dir) if a.record_dir else None
    for g in range(a.games):
        deck = DeckTracker()
        rec = GameRecorder(agent=f"{a.platform}-threes-expectimax", depth_cap=a.depth_cap)
        score, best_tile, moves = play_one_game(dev, mc, deck, rec,
                                                 a.move_delay, a.max_moves, getattr(a, "dbg", False))
        shot = None
        if hasattr(dev, "screenshot_png"):
            try:
                shot = dev.screenshot_png()     # the real game-over screen (settlement)
            except Exception:                   # noqa: BLE001
                shot = None
        msg = f"game {g+1}/{a.games}: {moves} moves, max {best_tile}, score {score}"
        if keeper:
            saved, _, best = keeper.consider(rec.replay_dict(), shot)
            msg += f" | best {best}" + (" -> NEW BEST saved" if saved else "")
        print(msg, flush=True)
        if g + 1 < a.games and hasattr(dev, "restart"):
            dev.restart()


def dry_run(server):
    """No device: just confirm the moveserver answers a canned position."""
    mc = MoveClient(server)
    print("moveserver:", mc.ping())
    board = [[1, 2, 0, 0], [3, 6, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    m = mc.ask(board, next_val=1, deck=[3, 3, 4])
    print(f"dry-run: move={m} ({MOVE_NAME.get(m, 'none')})")


# --------------------------------------------------------------------------- #
# Offline simulated device — the Threes engine stands in for the phone.
# --------------------------------------------------------------------------- #
def _render_board_png(board_idx, score, game_over=True, player=""):
    """A simple settlement-style card for the self-test's screenshot_png()."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 460, 620
    im = Image.new("RGB", (W, H), (0xf7, 0xf3, 0xe9))
    d = ImageDraw.Draw(im)

    def font(sz, bold=True):
        for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
                  else "/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/System/Library/Fonts/Helvetica.ttc"):
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
        return ImageFont.load_default()

    def ctext(x, y, s, f, fill):
        w = d.textlength(s, font=f)
        d.text((x - w / 2, y), s, font=f, fill=fill)

    ctext(W / 2, 26, "GAME OVER" if game_over else "THREES", font(30), (0x33, 0x33, 0x33))
    ctext(W / 2, 66, f"self-test (engine){'  ·  ' + player if player else ''}",
          font(15, False), (0x88, 0x88, 0x88))
    ctext(W / 2, 96, f"{score:,}", font(52), (0x22, 0x22, 0x22))
    cs, gap, y0 = 96, 8, 200
    x0 = (W - 4 * cs - 3 * gap) // 2

    def tilecol(v):
        if v == 0:
            return (0xEA, 0xE4, 0xD6), (0xEA, 0xE4, 0xD6)
        if v == 1:
            return (0x37, 0x9F, 0xE0), (255, 255, 255)
        if v == 2:
            return (0xF2, 0x53, 0x5B), (255, 255, 255)
        return (255, 255, 255), (0x33, 0x33, 0x33)

    for r in range(4):
        for c in range(4):
            v = VALUE[board_idx[r][c]]
            bg, fg = tilecol(v)
            x, y = x0 + c * (cs + gap), y0 + r * (cs + gap)
            d.rounded_rectangle([x, y, x + cs, y + cs], radius=10, fill=bg)
            if v:
                ctext(x + cs / 2, y + cs / 2 - 18, str(v), font(30 if v < 100 else 24), fg)
    buf = io.BytesIO()
    im.save(buf, "png")
    return buf.getvalue()


class EngineDevice:
    """A `Device` backed by the Python Threes engine (rl/threes_env.ThreesEnv), so
    the full scoring flow runs offline with no phone. read()/swipe() go straight to
    the engine; screenshot_png() renders a settlement card."""
    def __init__(self, seed=1, player=""):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rl"))
        from threes_env import ThreesEnv
        self.env = ThreesEnv()
        self.env.reset(seed)
        self.seed = seed
        self.player = player

    def read(self):
        if not self.env.legal_actions():
            return None, None
        return [list(r) for r in self.env.board], [self.env.next]

    def swipe(self, move):
        self.env.step(move)

    def screenshot_png(self):
        return _render_board_png(self.env.board, self.env.score(),
                                 game_over=not self.env.legal_actions(), player=self.player)

    def submit_name(self, name):
        pass

    def restart(self):
        self.seed += 1
        self.env.reset(self.seed)
