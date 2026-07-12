#!/usr/bin/env bash
#
# Rerun the full experiment suite on a many-core box (e.g. the 240 vCPU cloud).
# Everything is deterministic (game i uses seed+i), so results are reproducible.
#
# Usage (run detached so it survives an ssh disconnect):
#   nohup bash scripts/rerun_cloud.sh > rerun.log 2>&1 &
#   tail -f rerun.log            # watch progress
#
# Optional first arg = worker count (default: all logical CPUs).
#   nohup bash scripts/rerun_cloud.sh 240 > rerun.log 2>&1 &
#
# Outputs:
#   results/<label>.jsonl            one line per game (seed, score, max_tile, moves)
#   results/summaries.jsonl          one JSON summary line per run (feeds EXPERIMENTS.md)
#   results/records/record_<N>.json  the single highest-score replay across ALL runs
#
set -euo pipefail
cd "$(dirname "$0")/.."

W="${1:-$(nproc)}"
echo "Building bench (workers=$W)..."
go build -o bin/bench ./cmd/bench
mkdir -p results/records

# -seqsearch: each game's search runs single-threaded and we parallelise across
# games — the right mode for a many-core box (no root-goroutine oversubscription).
C="-bb -seqsearch -workers $W -record results/records"

run() { echo; echo "=== bench $* ==="; ./bin/bench $C "$@"; }

# Full grid: both deck modes x depths 1-6, uniform N=1000 (no special depth).
# This gives the strength-vs-depth curve for BOTH deck-blind and deck-aware, and
# hence the deck-aware ablation at every depth (paired seeds 1..1000). The deep
# points d5/d6 dominate wall time (~2h and ~3.6h per run on 240 cores).
for mode in blind aware; do
  flag=""; [ "$mode" = aware ] && flag="-deckaware"
  for d in 1 2 3 4 5 6; do
    run -n 1000 -seed 1 -depthcap "$d" $flag -label "$mode-d$d" -out "results/${mode}_d$d.jsonl"
  done
done

# 3) OPTIONAL / EXPENSIVE — depth 7 is ~hours; depth 8+ is impractical (CprobMin
#    caps the effective depth and cost grows ~4-5x per level). Uncomment if wanted.
# run -n 100 -seed 1 -depthcap 7 -deckaware -label aware-d7 -out results/aware_d7.jsonl

echo; echo "All done. Per-run summaries: results/summaries.jsonl"
echo "Best replay across all runs: results/records/"
