#!/usr/bin/env bash
#
# Prove the Python RL environment (rl/threes_env.py) is the SAME environment as
# the Go engine, so Phase 3 RL scores are comparable to the Go search/N-tuple
# agents in the paper. The Go engine dumps random-legal-move games as event
# streams; the Python env replays each move and force-places the recorded spawn,
# asserting board + score match cell-for-cell (RNG-independent — see
# cmd/paritydump and rl/parity_check.py).
#
# Run it after ANY change to the move/merge/score logic on either side.
#
# Usage:  bash scripts/rl_parity.sh [games] [seed]
#   games  number of games to cross-check (default 500 — more = wider coverage)
#   seed   base seed (default 1)
#
set -euo pipefail
cd "$(dirname "$0")/.."

GAMES="${1:-500}"
SEED="${2:-1}"

echo "Building paritydump..."
go build -o bin/paritydump ./cmd/paritydump

echo "Dumping $GAMES Go games (seed $SEED) and replaying through rl/threes_env.py..."
./bin/paritydump -seed "$SEED" -games "$GAMES" | python3 rl/parity_check.py
