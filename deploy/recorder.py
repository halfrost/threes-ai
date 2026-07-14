"""Reusable game recorder + best-run keeper for the scoring drivers.

Records a live game (web / Android / iOS) as a replay in the SAME schema the web
viewer (web/replay.html) and the Go engine (engine/replay.go) use, so a saved
game plays back directly in the existing viewer with no conversion:

    {seed, agent, depth_cap, final_score, max_tile, moves, value_table[16],
     steps: [{board: 4x4 tile INDICES, next: index (-1 = none),
              move: 0-3 (-1 = terminal), score}]}

Board cells are tile INDICES (0 = empty); value_table maps index -> printed value.
The score is the Threes score computed from the board — sum of 3^(index-2) over
tiles with index >= 3 — which equals the value the game shows.

Only the single highest-scoring game is kept: BestKeeper overwrites best.json and
best.png only when a new game beats the best final_score seen so far (persisted
across runs by reading the existing best.json).
"""
import json
import os

from common import VALUE, INDEX


def score_from_board(board_idx):
    """Threes score from a board of tile indices (matches engine Score / the UI)."""
    return sum(3 ** (i - 2) for row in board_idx for i in row if i >= 3)


def _to_idx(v):
    if not v or v < 0:
        return 0
    return INDEX.get(v, 0)


class GameRecorder:
    """Accumulates one game's plies in replay-file form."""
    def __init__(self, agent="web", depth_cap=0, seed=0):
        self.agent, self.depth_cap, self.seed = agent, depth_cap, seed
        self.steps = []

    def record(self, board_values, next_value, move):
        """One ply: the board BEFORE the move (printed values), the previewed next
        tile value (0/None/bonus -> none), and the move actually applied (0-3)."""
        board_idx = [[_to_idx(v) for v in row] for row in board_values]
        nxt = INDEX[next_value] if (next_value in INDEX and next_value > 0) else -1
        self.steps.append({"board": board_idx, "next": nxt, "move": move,
                           "score": score_from_board(board_idx)})

    def finish(self, final_board_values):
        """The terminal board (no move)."""
        board_idx = [[_to_idx(v) for v in row] for row in final_board_values]
        self.steps.append({"board": board_idx, "next": -1, "move": -1,
                           "score": score_from_board(board_idx)})

    def final_score(self):
        return self.steps[-1]["score"] if self.steps else 0

    def replay_dict(self):
        max_idx = max((c for st in self.steps for row in st["board"] for c in row), default=0)
        return {
            "seed": self.seed, "agent": self.agent, "depth_cap": self.depth_cap,
            "final_score": self.final_score(), "max_tile": VALUE[max_idx],
            "moves": max(0, len(self.steps) - 1), "value_table": list(VALUE),
            "steps": self.steps,
        }


class BestKeeper:
    """Keeps only the highest-scoring game: best.json (replay) + best.png
    (game-over screenshot), overwritten only when beaten. Best score persists
    across runs by reading the existing best.json."""
    def __init__(self, out_dir):
        self.dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.best = 0
        try:
            with open(os.path.join(out_dir, "best.json")) as f:
                self.best = json.load(f).get("final_score", 0)
        except (OSError, ValueError):
            pass

    def consider(self, replay_dict, screenshot_bytes=None):
        """Save iff replay beats the best so far. Returns (saved, score, best)."""
        score = replay_dict.get("final_score", 0)
        if score <= self.best:
            return False, score, self.best
        self.best = score
        with open(os.path.join(self.dir, "best.json"), "w") as f:
            json.dump(replay_dict, f)
        if screenshot_bytes:
            with open(os.path.join(self.dir, "best.png"), "wb") as f:
                f.write(screenshot_bytes)
        return True, score, self.best
