#!/usr/bin/env bash
#
# Train the strongest N-tuple config to try to break the T2 greedy plateau
# (big tuples saturated around mean ~21k): 8x 6-cell tuples (big2, ~540MB) with
# temporal-coherence per-weight learning rates (-tc) and a linearly annealed
# global alpha. TC damps oscillating weights and anneal lets it settle, both of
# which should push the asymptote above the constant-alpha 4x6 run.
#
# Memory: big2 weights ~540MB; with TC accumulators ~1.6GB resident. Fine on the
# cloud box. Slower per step than big (8 vs 4 tuples) — budget ~2x the T2 wall.
#
# Usage (detached, survives ssh disconnect):
#   nohup bash scripts/train_big2_tc.sh > train_big2_tc.log 2>&1 &
#   tail -f train_big2_tc.log
#   # then plot:  python3 scripts/learning_curve.py train_big2_tc.log
#
# Args (optional, positional):
#   $1 = games        (default 15000000)
#   $2 = alpha0       (default 0.1)
#   $3 = alpha_final  (default 0.01)
#
set -euo pipefail
cd "$(dirname "$0")/.."

GAMES="${1:-15000000}"
A0="${2:-0.1}"
AF="${3:-0.01}"
OUT="models/ntuple_big2_tc.gob"

echo "Building train..."
go build -o bin/train ./cmd/train
mkdir -p models

echo "Training big2 + TC, alpha ${A0}->${AF}, ${GAMES} games -> ${OUT}"
./bin/train -games "$GAMES" -alpha "$A0" -alpha-final "$AF" -tc -tuples big2 \
  -eval-every 500000 -eval-n 1000 -out "$OUT"

echo "Done. Compare against T2 (big, mean ~21k):"
echo "  python3 scripts/learning_curve.py train_big2_tc.log"
echo "  ./bin/bench -agent ntuple-search -model ${OUT} -deckaware -depthcap 4 -n 1000 -seqsearch -workers \$(nproc) -label ntsearch-big2-d4"
