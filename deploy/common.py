"""Shared core for every scoring driver (web / Android / iOS).

Only two things are platform-specific — capturing the board and injecting a move.
Everything else is here: talking to the Go `moveserver` (the brain), tracking the
deck so the search can play deck-aware, and the tile index<->value maps. Pure
stdlib so it runs anywhere.

Pipeline each platform implements:  read board -> MoveClient.ask -> inject move
                                    -> DeckTracker.note -> repeat; restart on over.
"""
from __future__ import annotations
import json
import urllib.request

# Printed tile value for each engine index (index 0 = empty). Matches the Go
# ValueTable / rl/threes_env VALUE and android/ocr.to_ind.
VALUE = [0, 1, 2, 3, 6, 12, 24, 48, 96, 192, 384, 768, 1536, 3072, 6144, 12288]
INDEX = {v: i for i, v in enumerate(VALUE)}

# move int -> human name; matches gameboard.MakeMove / rl/threes_env / moveserver.
MOVE_NAME = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}


def to_values(board_idx):
    """4x4 of engine indices -> 4x4 of printed values (what moveserver expects)."""
    return [[VALUE[c] for c in row] for row in board_idx]


class MoveClient:
    """Posts a board to the Go moveserver and returns the best move (0..3, -1 none).

    board: 4x4 printed VALUES. Pass exactly one of:
      next_val — the single previewed value (1/2/3), or <=0 for a bonus "+";
      next_set — the exact candidate next VALUES (from OCR's next preview, or the
                 remaining deck) — more precise, used verbatim by the search.
    deck: optional [ones, twos, threes] remaining, for deck-aware play.
    """
    def __init__(self, server="http://127.0.0.1:9010", timeout=30):
        self.server = server.rstrip("/")
        self.timeout = timeout

    def ask(self, board_values, next_val=0, next_set=None, deck=None):
        body = {"board": board_values, "next": next_val}
        if next_set:
            body["nextset"] = list(next_set)
        if deck:
            body["deck"] = list(deck)
        data = json.dumps(body).encode()
        req = urllib.request.Request(self.server + "/move", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)["move"]

    def ping(self):
        with urllib.request.urlopen(self.server + "/", timeout=5) as resp:
            return resp.read().decode().strip()


class DeckTracker:
    """Tracks the remaining 1/2/3 bag by counting base tiles as they appear, so we
    can play deck-aware on a real device where the bag isn't observable. Threes
    reshuffles a fresh bag of {4x1, 4x2, 4x3} whenever it empties; we reset the
    count every 12 base tiles. Start from a fresh game for accuracy. Bonus tiles
    (value >= 6) are not drawn from the bag and are ignored."""
    def __init__(self):
        self.drawn = [0, 0, 0]

    def note(self, value):
        if value in (1, 2, 3):
            self.drawn[value - 1] += 1
            if sum(self.drawn) >= 12:
                self.drawn = [0, 0, 0]

    def remaining(self):
        return [4 - self.drawn[i] for i in range(3)]


def board_str(board_values):
    """Compact 4x4 render for logging."""
    return "\n".join(" ".join(f"{v:>4}" for v in row) for row in board_values)
