#!/usr/bin/env bash
#
# T6 — the fourth cell of the T2/T4/T5/T6 design: `big2` tuples with CONSTANT alpha
# (T2's recipe, but on big2's 2x capacity). No temporal-coherence, no anneal.
# Purpose: T4 (big2 + TC + anneal) regressed to ~9.6k greedy vs T2's ~21k, and we
# can't tell if TC+anneal HURT or big2 is just under-trained at 15M. This isolates
# it: T2 (big,const) vs T6 (big2,const) -> capacity effect alone; T4 (big2,TC+anneal)
# vs T6 (big2,const) -> the TC+anneal levers on big2. If T6 clears ~21k, TC+anneal
# is the culprit; if T6 also stalls low, big2 just needs far more games.
#
# Single-threaded (only the periodic eval fans out); ~540MB weights, no TC
# accumulators. Resumable via -resume; checkpoints every 500k games.
#
# Usage (detached):
#   nohup bash scripts/train_big2.sh > train_big2.log 2>&1 &
#   tail -f train_big2.log
#   python3 scripts/learning_curve.py train_big2.log      # compare vs T2/T4/T5
#
# Args (optional, positional): $1=games (15M)  $2=alpha (0.1)
set -euo pipefail
cd "$(dirname "$0")/.."

GAMES="${1:-15000000}"
ALPHA="${2:-0.1}"
OUT="models/ntuple_big2.gob"

echo "Building train..."
go build -o bin/train ./cmd/train
mkdir -p models

echo "Training big2, CONSTANT alpha=${ALPHA}, ${GAMES} games -> ${OUT}"
./bin/train -games "$GAMES" -alpha "$ALPHA" -tuples big2 \
  -eval-every 500000 -eval-n 1000 -out "$OUT"

echo "Done. Compare greedy asymptote to T2 (big,const ~21k) and T4 (big2,TC+anneal ~9.6k):"
echo "  python3 scripts/learning_curve.py train_big2.log"
