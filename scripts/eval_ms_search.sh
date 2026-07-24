#!/usr/bin/env bash
#
# T11 — MULTI-STAGE N-tuple as the expectimax LEAF (T3 done right).
#
# T3 plugged a single greedy-trained net into the expectimax leaves and it LOST to the
# hand heuristic, the gap widening with depth (d5: 3072 56% vs 70%, 6144 6.4% vs 15.2%) —
# because one leaf is phase-miscalibrated. T10 then showed a per-phase split lifts greedy
# play +19% (23.5k -> 28k). T11 combines them: use the T10 stage nets as the leaf, each
# dispatched to the phase it was trained for. The bet: a phase-calibrated leaf is what T3
# lacked, and the search already reaches 6144 ~21% of the time — a good leaf could convert
# that into a real endgame rate.
#
# Runs, for each depth, three agents on IDENTICAL deck-aware seeds:
#   ntuple-ms-search  (the T10 stage nets, dispatched by max tile)   <- the candidate
#   ntuple-search     (T7's single 30M net as the leaf)               <- T3's leaf
#   expectimax        (hand heuristic leaf)                           <- the bar to beat
#
# Usage (detached):
#   nohup bash scripts/eval_ms_search.sh models/ntuple_ms 10,13 > ms_search.log 2>&1 &
#   tail -f ms_search.log
# Args (positional):
#   $1 = stage-net PREFIX (loads <prefix>.stage0.gob ..stageK.gob)   default models/ntuple_ms
#   $2 = -stages boundaries (MUST match how the nets were trained)    default 10,13
#   $3 = single-net leaf for the T3 comparison                        default models/ntuple_big.gob
#   $4 = worker count                                                 default all CPUs
#   $5 = depths (space-sep)                                           default "3 4 5"
#   $6 = games per run                                                default 1000
set -euo pipefail
cd "$(dirname "$0")/.."

PREFIX="${1:-models/ntuple_ms}"
STAGES="${2:-10,13}"
SINGLE="${3:-models/ntuple_big.gob}"
W="${4:-$(nproc 2>/dev/null || sysctl -n hw.ncpu)}"
DEPTHS="${5:-3 4 5}"
N="${6:-1000}"

# Build the comma-sep stage-net list from the prefix: one file per boundary + 1.
NB=$(awk -F, '{print NF}' <<<"$STAGES")     # number of boundaries
NSTAGES=$((NB + 1))
MODELS=""
for i in $(seq 0 $((NSTAGES - 1))); do
  f="${PREFIX}.stage${i}.gob"
  [ -f "$f" ] || { echo "missing stage net: $f" >&2; exit 1; }
  SZ=$(wc -c < "$f" | tr -d ' ')
  [ "$SZ" -gt 1000000 ] || { echo "$f is only $SZ bytes — an LFS pointer, not a model" >&2; exit 1; }
  MODELS="${MODELS:+$MODELS,}$f"
done
echo "T11: ${NSTAGES} stage nets [$MODELS], bounds ${STAGES}, single-net baseline ${SINGLE}"

go build -o bin/bench ./cmd/bench
mkdir -p results/records

C="-bb -seqsearch -workers $W -deckaware -n $N -seed 1 -record results/records -log results/ms_search_summaries.jsonl"
run() { echo; echo "=== bench $* ==="; ./bin/bench $C "$@"; }

for d in $DEPTHS; do
  # candidate: multi-stage leaf
  run -agent ntuple-ms-search -models "$MODELS" -stages "$STAGES" -depthcap "$d" \
      -label "ms-search-d$d" -out "results/ms_search_d$d.jsonl"
  # T3's single-net leaf, identical seeds
  [ -f "$SINGLE" ] && run -agent ntuple-search -model "$SINGLE" -depthcap "$d" \
      -label "single-leaf-d$d" -out "results/single_leaf_d$d.jsonl"
  # hand heuristic leaf, identical seeds — the bar
  run -agent expectimax -depthcap "$d" \
      -label "expectimax-d$d" -out "results/expectimax_ms_d$d.jsonl"
done

echo; echo "All done. Summaries: results/ms_search_summaries.jsonl"
echo "T11 wins if ms-search closes T3's d4/d5 gap to the hand heuristic (3072/6144 rates)."
