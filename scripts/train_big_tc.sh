#!/usr/bin/env bash
#
# T5 — ABLATION for T4: the SAME recipe (temporal-coherence + linearly annealed
# alpha) on the 4x6 `big` tuple set instead of the 8x6 `big2` set. Run alongside
# T4 (train_big2_tc.sh) on a second box. Two things it isolates:
#   * T2 (big, constant alpha, plateaued ~21k greedy) vs THIS (big, TC + anneal)
#     -> how much of any gain is the TC+anneal levers, holding the tuple set fixed.
#   * THIS (big, TC+anneal) vs T4 (big2, TC+anneal)
#     -> how much is big2's extra capacity, holding the levers fixed.
# It also yields a CHEAPER leaf: T3 showed leaf-eval speed dominates, and `big`
# (~270MB) evaluates ~2x faster than `big2` (~540MB), so a strong-but-smaller
# model may be the better practical expectimax leaf.
#
# Training is single-threaded (only the periodic eval fans out), so this coexists
# with anything else on the box. Memory: big weights ~270MB, +TC accumulators
# ~800MB resident. Resumable via -resume; checkpoints every 500k games.
#
# Usage (detached, survives ssh disconnect):
#   nohup bash scripts/train_big_tc.sh > train_big_tc.log 2>&1 &
#   tail -f train_big_tc.log
#   python3 scripts/learning_curve.py train_big_tc.log
#   # then eval it as a leaf, head-to-head vs the hand heuristic (like T3):
#   bash scripts/eval_ntuple_search.sh models/ntuple_big_tc.gob "$(nproc)" "2 3 4"
#
# Args (optional, positional): $1=games (15M)  $2=alpha0 (0.1)  $3=alpha_final (0.01)
set -euo pipefail
cd "$(dirname "$0")/.."

GAMES="${1:-15000000}"
A0="${2:-0.1}"
AF="${3:-0.01}"
OUT="models/ntuple_big_tc.gob"

echo "Building train..."
go build -o bin/train ./cmd/train
mkdir -p models

echo "Training big + TC, alpha ${A0}->${AF}, ${GAMES} games -> ${OUT}"
./bin/train -games "$GAMES" -alpha "$A0" -alpha-final "$AF" -tc -tuples big \
  -eval-every 500000 -eval-n 1000 -out "$OUT"

echo "Done. Compare greedy asymptote to T2 (big, const-alpha, ~21k) and T4 (big2+TC):"
echo "  python3 scripts/learning_curve.py train_big_tc.log"
echo "  bash scripts/eval_ntuple_search.sh ${OUT} \$(nproc) \"2 3 4\""
