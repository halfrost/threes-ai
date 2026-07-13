#!/usr/bin/env python3
"""Turn a bench summaries.jsonl into a comparison table.

bench appends one JSON summary per run to its -log file (default
results/summaries.jsonl). This reads that file and prints a compact table
sorted by (depth, agent), so an ntuple-search vs expectimax head-to-head — or
any depth sweep — is readable at a glance. Pure stdlib; runs anywhere.

Usage:
    python3 scripts/report_runs.py [summaries.jsonl] [--md] [--grep SUBSTR]
        summaries.jsonl   path to the bench -log file (default results/summaries.jsonl)
        --md              emit a GitHub-Markdown table (paste into docs/EXPERIMENTS.md)
        --grep SUBSTR     only rows whose label/agent contains SUBSTR
        --sort KEY        sort key: depth (default) | mean | median | 6144

Columns: label, agent, deck(a/b), depth, N, mean, median, p90, max,
         reach 768/1536/3072/6144 (%), ms/move, wall(s).
The last row-block is what you send back for analysis / the paper table.
"""
import argparse
import json
import sys

COLS = ["label", "agent", "deck", "d", "N", "mean", "median", "p90",
        "max", "768%", "1536%", "3072%", "6144%", "ms/mv", "wall_s"]


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def pct(reach, tile):
    return 100.0 * reach.get(str(tile), 0.0)


def row_cells(s):
    r = s.get("reach", {})
    return {
        "label": s.get("label", "") or "-",
        "agent": s.get("agent", ""),
        "deck": "a" if s.get("deck_aware") else "b",
        "d": s.get("depth_cap", 0),
        "N": s.get("games", 0),
        "mean": f"{s.get('score_mean', 0):.0f}",
        "median": s.get("score_median", 0),
        "p90": s.get("score_p90", 0),
        "max": s.get("score_max", 0),
        "768%": f"{pct(r, 768):.1f}",
        "1536%": f"{pct(r, 1536):.1f}",
        "3072%": f"{pct(r, 3072):.1f}",
        "6144%": f"{pct(r, 6144):.1f}",
        "ms/mv": f"{s.get('ms_per_move', 0):.2f}",
        "wall_s": f"{s.get('wall_sec', 0):.0f}",
    }


def sort_key(name):
    def key(s):
        r = s.get("reach", {})
        if name == "mean":
            return -s.get("score_mean", 0)
        if name == "median":
            return -s.get("score_median", 0)
        if name == "6144":
            return -r.get("6144", 0)
        return (s.get("depth_cap", 0), s.get("agent", ""), not s.get("deck_aware"))
    return key


def render(rows, md):
    cells = [row_cells(s) for s in rows]
    if md:
        print("| " + " | ".join(COLS) + " |")
        print("|" + "|".join("---" for _ in COLS) + "|")
        for c in cells:
            print("| " + " | ".join(str(c[k]) for k in COLS) + " |")
        return
    widths = {k: max(len(k), *(len(str(c[k])) for c in cells)) for k in COLS}
    line = "  ".join(k.rjust(widths[k]) for k in COLS)
    print(line)
    print("-" * len(line))
    for c in cells:
        print("  ".join(str(c[k]).rjust(widths[k]) for k in COLS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="results/summaries.jsonl")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--grep", default="")
    ap.add_argument("--sort", default="depth")
    a = ap.parse_args()
    try:
        rows = load(a.path)
    except FileNotFoundError:
        sys.exit(f"no such file: {a.path} (run bench with -log {a.path} first)")
    if a.grep:
        rows = [s for s in rows
                if a.grep in (s.get("label", "") + " " + s.get("agent", ""))]
    if not rows:
        sys.exit("no matching runs")
    rows.sort(key=sort_key(a.sort))
    render(rows, a.md)


if __name__ == "__main__":
    main()
