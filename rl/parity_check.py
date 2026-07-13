#!/usr/bin/env python3
"""Prove rl/threes_env.py reproduces the Go engine's rules, via event replay.

Reads the JSONL that `cmd/paritydump` emits (one game per line: initial board +
a stream of {move, spawn, board, score}). For each step we re-apply the move
with the Python env's own slide/merge, force-place the SAME spawn the Go engine
placed, then assert the resulting board and score match Go cell-for-cell. Because
the spawn is replayed (not re-sampled), this isolates the deterministic rules
(slide / merge / placement / scoring) from each side's RNG.

A green run means the Go and Python environments are the same environment — the
precondition for reporting Phase 3 RL numbers next to the Go search/N-tuple
agents in the paper.

Usage:
    go run ./cmd/paritydump -seed 1 -games 200 > parity.jsonl
    python3 rl/parity_check.py parity.jsonl
    # or pipe:  go run ./cmd/paritydump -games 200 | python3 rl/parity_check.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import threes_env as te  # noqa: E402


def reshape(flat):
    return [list(flat[r * 4:r * 4 + 4]) for r in range(4)]


def check_game(g):
    """Return (steps_checked, error_or_None)."""
    board = reshape(g["init"])
    for i, st in enumerate(g["steps"]):
        idx, r, c = st["spawn"]
        if idx < 0:
            return i, f"step {i}: dumper flagged a bad spawn diff (idx={idx})"
        nb, _changed, moved = te.apply_move(board, st["move"])
        if not moved:
            return i, f"step {i}: Python treats move {st['move']} as illegal, Go did not"
        if nb[r][c] != 0:
            return i, f"step {i}: spawn cell ({r},{c}) not empty after move (={nb[r][c]})"
        nb[r][c] = idx
        want = reshape(st["board"])
        if nb != want:
            return i, (f"step {i}: board mismatch after move {st['move']}\n"
                       f"  python: {nb}\n  go:     {want}")
        sc = te.score(nb)
        if sc != st["score"]:
            return i, f"step {i}: score {sc} (python) != {st['score']} (go)"
        board = want
    # whole-game endpoints
    if g["steps"]:
        if te.score(board) != g["final_score"]:
            return len(g["steps"]), "final score mismatch"
        maxv = te.VALUE[max(max(row) for row in board)]
        if maxv != g["final_max"]:
            return len(g["steps"]), f"final max tile {maxv} != {g['final_max']}"
    return len(g["steps"]), None


def main():
    src = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
    games = ok = total_steps = 0
    failures = []
    for line in src:
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        games += 1
        checked, err = check_game(g)
        total_steps += checked
        if err is None:
            ok += 1
        else:
            failures.append((g["seed"], err))
            if len(failures) <= 5:  # show the first few divergences
                print(f"FAIL seed={g['seed']}: {err}", file=sys.stderr)
    print(f"parity: {ok}/{games} games OK, {total_steps} steps checked")
    if failures:
        print(f"{len(failures)} game(s) diverged — Python env != Go engine", file=sys.stderr)
        sys.exit(1)
    print("Python env reproduces the Go engine exactly.")


if __name__ == "__main__":
    main()
