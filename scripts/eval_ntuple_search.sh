#!/usr/bin/env bash
#
# N-tuple-as-search-leaf vs hand-heuristic, head-to-head, on a many-core box.
# For each depth we run the SAME seeds twice: once with the learned N-tuple value
# function plugged into the expectimax leaves (-agent ntuple-search), once with
# the hand heuristic (-agent expectimax). Deterministic (game i uses seed+i), so
# the two agents are judged on identical games.
#
# The question: can a LEARNED leaf let a SHALLOWER search match/beat a DEEPER
# hand-heuristic search (a compute win), and/or lift the 3072/6144 tile rates?
#
# Usage (detached so it survives an ssh disconnect):
#   nohup bash scripts/eval_ntuple_search.sh > ntsearch.log 2>&1 &
#   tail -f ntsearch.log            # watch progress
#
# Args (all optional, positional):
#   $1 = N-tuple model file   (default: models/ntuple_big.gob)
#   $2 = worker count         (default: all logical CPUs)
#   $3 = depths, space-sep    (default: "3 4 5")
#   $4 = games per run         (default: 1000)
#
# Outputs:
#   results/<label>.jsonl                one line per game (seed, score, max_tile, moves)
#   results/ntsearch_summaries.jsonl     one JSON summary per run (send this to compare)
#   results/records/record_<N>.json      the single highest-score replay across ALL runs
#
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${1:-models/ntuple_big.gob}"
W="${2:-$(nproc)}"
DEPTHS="${3:-3 4 5}"
N="${4:-1000}"

[ -f "$MODEL" ] || { echo "model not found: $MODEL (train it first, or pass the path as \$1)" >&2; exit 1; }
echo "Building bench (model=$MODEL workers=$W depths='$DEPTHS' N=$N)..."
go build -o bin/bench ./cmd/bench
mkdir -p results/records

# -seqsearch: each game's search runs single-threaded and we parallelise across
# games — the right mode for a many-core box. -deckaware feeds the true bag to
# BOTH agents so the only variable is the leaf (learned vs hand heuristic).
C="-bb -seqsearch -workers $W -deckaware -n $N -seed 1 -record results/records -log results/ntsearch_summaries.jsonl"

run() { echo; echo "=== bench $* ==="; ./bin/bench $C "$@"; }

for d in $DEPTHS; do
  # learned N-tuple value function as the expectimax leaf
  run -agent ntuple-search -model "$MODEL" -depthcap "$d" \
      -label "ntsearch-big-d$d" -out "results/ntsearch_big_d$d.jsonl"
  # hand heuristic as the leaf (baseline), identical seeds
  run -agent expectimax -depthcap "$d" \
      -label "expectimax-d$d" -out "results/expectimax_d$d.jsonl"
done

echo; echo "All done. Head-to-head summaries: results/ntsearch_summaries.jsonl"
echo "Best replay across all runs: results/records/"
