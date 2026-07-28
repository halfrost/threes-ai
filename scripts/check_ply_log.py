"""Audit a threesgame ply log for moves that did not land as intended.

The web driver records, per ply, the board BEFORE the move and the move it pressed:
    {"b": <4x4 printed values>, "n": <next tile>, "m": <move>}
so consecutive records must satisfy: apply_move(b_i, m_i) + exactly ONE spawned tile == b_{i+1}.

Anything else means the browser and the AI disagreed about what happened:
  * DOUBLE  — b_{i+1} is two moves ahead: the key was pressed twice (e.g. a re-press fired
              while the game had already processed the move but not yet persisted it), so a
              move the AI never chose got injected.
  * LOST    — b_{i+1} == b_i: nothing happened.
  * DESYNC  — anything else (a stale read, a resume seam, a mis-decoded board).

Why it matters: the search picks the best move for the board it was GIVEN. An injected or
dropped move silently turns depth-6 play into something much weaker while every component
still looks healthy in isolation.

Usage (on the box running the grind):
    python3 scripts/check_ply_log.py /tmp/tg_cloud/work_*/plies_*.jsonl
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rl"))
from threes_env import apply_move  # noqa: E402  (parity-verified against the Go engine)

VALUE = [0, 1, 2, 3, 6, 12, 24, 48, 96, 192, 384, 768, 1536, 3072, 6144, 12288]
INDEX = {v: i for i, v in enumerate(VALUE)}
MOVE_NAME = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}


def to_idx(vboard):
    return [[INDEX.get(v, 0) if v else 0 for v in row] for row in vboard]


def diff_cells(a, b):
    return [(r, c) for r in range(4) for c in range(4) if a[r][c] != b[r][c]]


def classify(prev_idx, move, next_idx):
    """Return (verdict, detail) for one ply transition."""
    slid, _, _ = apply_move(prev_idx, move)
    if slid == next_idx:
        return "NOSPAWN", "move landed but no tile spawned"
    d = diff_cells(slid, next_idx)
    if len(d) == 1:
        r, c = d[0]
        if slid[r][c] == 0 and next_idx[r][c] > 0:
            return "OK", ""
        return "DESYNC", f"single cell changed but not a spawn at ({r},{c})"
    if prev_idx == next_idx:
        return "LOST", "board unchanged — the press did nothing"
    # is the next board reachable by applying ANOTHER move on top? => double press
    for m2 in range(4):
        slid2, _, _ = apply_move(slid, m2)
        d2 = diff_cells(slid2, next_idx)
        if slid2 == next_idx or (len(d2) == 1 and slid2[d2[0][0]][d2[0][1]] == 0):
            return "DOUBLE", f"two moves applied ({MOVE_NAME[move]} then {MOVE_NAME[m2]})"
        # a double press of the SAME key, each followed by a spawn, is the common case:
        for r in range(4):
            for c in range(4):
                if slid[r][c] != 0:
                    continue
                probe = [row[:] for row in slid]
                for spawn in (1, 2, 3):
                    probe[r][c] = spawn
                    s3, _, _ = apply_move(probe, m2)
                    d3 = diff_cells(s3, next_idx)
                    if s3 == next_idx or (len(d3) == 1 and s3[d3[0][0]][d3[0][1]] == 0):
                        return "DOUBLE", f"two moves+spawns ({MOVE_NAME[move]} then {MOVE_NAME[m2]})"
    return "DESYNC", f"{len(d)} cells differ from the expected afterstate"


def audit(path):
    plies = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or '"terminal"' in line:
                continue
            try:
                plies.append(json.loads(line))
            except ValueError:
                pass
    if len(plies) < 2:
        return None
    counts = {"OK": 0, "DOUBLE": 0, "LOST": 0, "NOSPAWN": 0, "DESYNC": 0}
    examples = []
    for i in range(len(plies) - 1):
        prev_idx = to_idx(plies[i]["b"])
        next_idx = to_idx(plies[i + 1]["b"])
        verdict, detail = classify(prev_idx, plies[i]["m"], next_idx)
        counts[verdict] += 1
        if verdict != "OK" and len(examples) < 3:
            examples.append(f"    ply {i}: {verdict} — {detail}")
    return os.path.basename(os.path.dirname(path)), len(plies), counts, examples


def main():
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        sys.exit(1)
    total = {"OK": 0, "DOUBLE": 0, "LOST": 0, "NOSPAWN": 0, "DESYNC": 0}
    nplies = 0
    for p in sorted(paths):
        res = audit(p)
        if not res:
            continue
        name, n, counts, examples = res
        nplies += n
        for k in total:
            total[k] += counts[k]
        bad = n - 1 - counts["OK"]
        flag = "  <-- BAD" if bad else ""
        print(f"{name:12s} {n:5d} plies  OK={counts['OK']:5d} "
              f"DOUBLE={counts['DOUBLE']:4d} LOST={counts['LOST']:4d} "
              f"NOSPAWN={counts['NOSPAWN']:4d} DESYNC={counts['DESYNC']:4d}{flag}")
        for e in examples:
            print(e)
    checked = sum(total.values())
    print("\n===== TOTAL =====")
    print(f"  plies read     {nplies}")
    if checked:
        for k in ("OK", "DOUBLE", "LOST", "NOSPAWN", "DESYNC"):
            print(f"  {k:8s} {total[k]:6d}  ({100*total[k]/checked:5.1f}%)")
        bad = checked - total["OK"]
        print(f"\n  => {100*bad/checked:.1f}% of moves did NOT land as the search intended.")
        if total["DOUBLE"]:
            print("     DOUBLE > 0 confirms extra key presses are injecting moves the AI never chose.")


if __name__ == "__main__":
    main()
