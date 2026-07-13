"""Faithful Threes! environment for the RL baselines (Phase 3).

Mirrors the Go engine's rules exactly (bag of 4x{1,2,3}; bonus tiles at 1/21 when
the max tile >= 48, uniform over {6..maxTile/8}; one-step slide+merge; spawn on
the edge opposite the move; score = sum 3^(index-2)). Board cells are tile
INDICES (0..15); use VALUE[idx] for printed values.

The core env is pure Python (no numpy) so it runs anywhere; `encode()` (numpy) is
only needed to feed the neural agents. Action: 0=UP, 1=DOWN, 2=LEFT, 3=RIGHT.
reset(seed) -> board; step(action) -> (board, reward, done, info). Reward is the
score gained by the move (merges).

NOTE: this is a Python port. Before any paper numbers, validate it against the Go
engine (same seed -> same trajectory) or evaluate trained policies through the Go
bench harness. It exists so the RL comparison baselines (DQN/PPO/AlphaZero) are
runnable now; they are the comparison, not the main method.
"""
from __future__ import annotations
import random

VALUE = [0, 1, 2, 3, 6, 12, 24, 48, 96, 192, 384, 768, 1536, 3072, 6144, 12288]
BONUS_FREQ = 21
INITIAL_TILES = 9


def merge_val(a: int, b: int) -> int:
    """Merged tile index of adjacent a (leading) and b, or -1 if they can't merge."""
    if (a == 1 and b == 2) or (a == 2 and b == 1):
        return 3
    if a == b and a >= 3:
        return a if a == 15 else a + 1
    return -1


def _move_line_low(c):
    """Move a 4-cell lane one step toward index 0 (matches gameboard.MakeMove).
    Returns (result_list, changed)."""
    for p in range(3):
        slide = c[p] == 0 and c[p + 1] != 0
        m = merge_val(c[p], c[p + 1])
        if not slide and m < 0:
            continue
        res = list(c[:p])
        res.append(m if m >= 0 else c[p + 1])
        for q in range(p + 1, 3):
            res.append(c[q + 1])
        res.append(0)
        return res, True
    return list(c), False


def _lane_cells(action, li):
    if action == 0:    # UP: column li, top -> bottom
        return [(r, li) for r in range(4)]
    if action == 1:    # DOWN: column li, bottom -> top
        return [(3 - r, li) for r in range(4)]
    if action == 2:    # LEFT: row li, left -> right
        return [(li, c) for c in range(4)]
    return [(li, 3 - c) for c in range(4)]  # RIGHT: row li, right -> left


def apply_move(board, action):
    """Apply a move to a 4x4 index board. Returns (new_board, changed_lanes, moved)."""
    nb = [row[:] for row in board]
    changed = [False] * 4
    for li in range(4):
        cells = _lane_cells(action, li)
        res, ch = _move_line_low([board[r][c] for (r, c) in cells])
        if ch:
            changed[li] = True
            for (r, c), v in zip(cells, res):
                nb[r][c] = v
    return nb, changed, any(changed)


def score(board) -> int:
    s = 0
    for row in board:
        for v in row:
            if v >= 3:
                s += 3 ** (v - 2)
    return s


def encode(board, nxt):
    """(17, 4, 4) float32 observation: 16 one-hot board channels + a next-tile
    channel. numpy is imported lazily so the core env has no hard dependency."""
    import numpy as np
    obs = np.zeros((17, 4, 4), dtype=np.float32)
    for r in range(4):
        for c in range(4):
            obs[board[r][c], r, c] = 1.0
    obs[16, :, :] = nxt / 15.0
    return obs


class ThreesEnv:
    def __init__(self):
        self.rng = random.Random()
        self.board = [[0] * 4 for _ in range(4)]
        self.bag = []
        self.next = 0
        self.next_bonus = False
        self.moves = 0

    def _refill_bag(self):
        self.bag = [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]

    def _draw_bag(self) -> int:
        if not self.bag:
            self._refill_bag()
        return self.bag.pop(self.rng.randrange(len(self.bag)))

    def _max_index(self) -> int:
        return max(max(row) for row in self.board)

    def _gen_tile(self):
        mx = self._max_index()
        if mx >= 7 and self.rng.randrange(BONUS_FREQ) == 0:
            return self.rng.randint(4, mx - 3), True   # value 6 .. maxValue/8
        return self._draw_bag(), False

    def reset(self, seed=None):
        if seed is not None:
            self.rng.seed(seed)
        self.board = [[0] * 4 for _ in range(4)]
        self._refill_bag()
        pos = list(range(16))
        self.rng.shuffle(pos)
        for p in pos[:INITIAL_TILES]:
            self.board[p // 4][p % 4] = self._draw_bag()
        self.next, self.next_bonus = self._gen_tile()
        self.moves = 0
        return self.board

    def legal_actions(self):
        return [a for a in range(4) if apply_move(self.board, a)[2]]

    def step(self, action):
        nb, changed, moved = apply_move(self.board, action)
        if not moved:
            # illegal move: no-op. Agents should mask with legal_actions().
            return self.board, 0.0, len(self.legal_actions()) == 0, {"illegal": True}
        reward = float(score(nb) - score(self.board))
        li = self.rng.choice([i for i in range(4) if changed[i]])
        r, c = {0: (3, li), 1: (0, li), 2: (li, 3), 3: (li, 0)}[action]
        nb[r][c] = self.next
        self.board = nb
        self.next, self.next_bonus = self._gen_tile()
        self.moves += 1
        return self.board, reward, len(self.legal_actions()) == 0, {}

    def obs(self):
        return encode(self.board, self.next)

    def max_tile(self):
        return VALUE[self._max_index()]

    def score(self):
        return score(self.board)

    def render(self):
        print(f"score={self.score()} next={VALUE[self.next]}{'+' if self.next_bonus else ''} moves={self.moves}")
        for row in self.board:
            print(" ".join(f"{VALUE[v]:5d}" for v in row))
        print()


if __name__ == "__main__":
    env = ThreesEnv()
    scores, maxtiles = [], []
    for g in range(200):
        env.reset(seed=g + 1)
        while True:
            legal = env.legal_actions()
            if not legal:
                break
            env.step(env.rng.choice(legal))
        scores.append(env.score())
        maxtiles.append(env.max_tile())
    scores.sort()
    print(f"random policy, 200 games: mean={sum(scores)/len(scores):.0f} "
          f"median={scores[len(scores)//2]} max={max(scores)} best_tile={max(maxtiles)}")
