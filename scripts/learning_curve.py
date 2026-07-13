#!/usr/bin/env python3
"""Parse a cmd/train log into a learning curve (CSV + ASCII sparklines).

train prints one eval line per checkpoint, e.g.
    [ 1200000 games |  1525s] eval(N=1000): mean=  12269 median=  9525 max=  63105 | 3072= 0.0% 6144= 0.0%
This extracts (games, sec, mean, median, max, 3072%, 6144%) from every such
line, writes a CSV, and draws unicode sparklines for mean & median so a plateau
or a phase-transition (e.g. the big-tuple median jumping 10k->21k) is visible in
a terminal. Optionally renders a PNG if matplotlib is importable. Pure stdlib
core; runs on the cloud box with no extra deps.

Usage:
    python3 scripts/learning_curve.py train_big.log [--csv out.csv] [--png out.png]
"""
import argparse
import re
import sys

LINE = re.compile(
    r"\[\s*(\d+)\s+games\s*\|\s*(\d+)s\]\s*eval\(N=(\d+)\):\s*"
    r"mean=\s*(\d+)\s+median=\s*(\d+)\s+max=\s*(\d+)\s*\|\s*"
    r"3072=\s*([\d.]+)%\s+6144=\s*([\d.]+)%")
BLOCKS = "▁▂▃▄▅▆▇█"


def parse(path):
    rows, header = [], ""
    with open(path) as f:
        for line in f:
            if line.startswith("Training "):
                header = line.strip()
            m = LINE.search(line)
            if m:
                g, s, n, mean, med, mx, r3, r6 = m.groups()
                rows.append(dict(games=int(g), sec=int(s), n=int(n),
                                 mean=int(mean), median=int(med), max=int(mx),
                                 r3072=float(r3), r6144=float(r6)))
    return header, rows


def spark(vals):
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return BLOCKS[0] * len(vals)
    return "".join(BLOCKS[int((v - lo) / (hi - lo) * (len(BLOCKS) - 1))] for v in vals)


def ascii_report(header, rows):
    if header:
        print(header)
    means = [r["mean"] for r in rows]
    meds = [r["median"] for r in rows]
    print(f"checkpoints={len(rows)}  games={rows[0]['games']}..{rows[-1]['games']}  "
          f"wall={rows[-1]['sec']}s")
    print(f"mean   {spark(means)}  {means[0]}->{means[-1]} (peak {max(means)})")
    print(f"median {spark(meds)}  {meds[0]}->{meds[-1]} (peak {max(meds)})")
    # mean near-saturation hint
    final = means[-1]
    plateau = next((r["games"] for r in rows if r["mean"] >= 0.95 * final), None)
    if plateau is not None:
        print(f"mean reaches 95% of final ({final}) by ~{plateau} games")
    # median phase-transition: compare the post-warmup low cluster to the late
    # cluster (two-cluster test), so we flag the 10k->21k jump, not the initial
    # warmup climb. warmup = the early-learning rise (mean < 30% of final).
    start = next((i for i, m in enumerate(means) if m >= 0.30 * final), 0)
    pw = meds[start:]
    if len(pw) >= 4:
        half = len(pw) // 2
        low = sorted(pw[:half])[half // 2]
        high = sorted(pw[half:])[(len(pw) - half) // 2]
        if high >= 1.4 * low:
            mid = (low + high) / 2
            gi = next(i for i, m in enumerate(meds) if i >= start and m >= mid)
            print(f"median phase-transition ~{low}->{high} near ~{rows[gi]['games']} games")
    peak6144 = max(r["r6144"] for r in rows)
    peak3072 = max(r["r3072"] for r in rows)
    print(f"greedy tile rates: 3072 peak {peak3072:.1f}%  6144 peak {peak6144:.1f}%")


def write_csv(path, rows):
    import csv
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"csv -> {path}")


def write_png(path, header, rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available; skipping --png (CSV/ASCII still produced)")
        return
    g = [r["games"] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(g, [r["mean"] for r in rows], label="mean")
    ax.plot(g, [r["median"] for r in rows], label="median")
    ax.set_xlabel("training games")
    ax.set_ylabel("eval score")
    ax.set_title(header or "N-tuple TD learning curve")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print(f"png -> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--csv")
    ap.add_argument("--png")
    a = ap.parse_args()
    try:
        header, rows = parse(a.log)
    except FileNotFoundError:
        sys.exit(f"no such file: {a.log}")
    if not rows:
        sys.exit(f"no eval lines matched in {a.log}")
    ascii_report(header, rows)
    if a.csv:
        write_csv(a.csv, rows)
    if a.png:
        write_png(a.png, header, rows)


if __name__ == "__main__":
    main()
