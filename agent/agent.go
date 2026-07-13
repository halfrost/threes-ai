// Package agent provides move selection for the learned N-tuple value function,
// shared by evaluation (cmd/bench) and usable elsewhere. It is additive: it does
// not change any existing search behaviour.
package agent

import (
	"math"

	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/ntuple"
)

// GreedyMove picks the depth-0 N-tuple policy move: the legal move maximising
// reward + V(afterstate), where reward is the score gained by the move. Returns
// ok=false when no move is legal (terminal).
func GreedyMove(net *ntuple.Network, g *engine.Game) (move int, ok bool) {
	cur := g.Score()
	best := math.Inf(-1)
	move = -1
	for a := 0; a < 4; a++ {
		nb, _, changeNum := gameboard.MakeMove(g.Board, a)
		if changeNum == 0 {
			continue
		}
		ab := engine.PackBoard(nb)
		r := engine.ScoreBB(ab) - cur
		if eval := float64(r) + net.Value(ab); eval > best {
			best, move = eval, a
		}
	}
	return move, move >= 0
}
