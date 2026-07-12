// Command train learns an N-tuple value function for Threes by afterstate
// temporal-difference self-play (TD(0)), the standard strong approach for
// 2048-like games (Szubert & Jaskowski 2014). It periodically evaluates the
// current network by greedy (depth-0) play and prints a learning curve, then
// saves the trained network.
//
// The value function estimates the value of an *afterstate* — the board right
// after a move but before the random tile appears. Move selection is greedy on
// reward + V(afterstate); the reward is the score gained by the move. Training
// seeds are kept disjoint from the fixed evaluation seed set (1..eval-n).
//
// Usage: go run ./cmd/train -games 200000 -alpha 0.1 -eval-every 20000
package main

import (
	"flag"
	"fmt"
	"math"
	"os"
	"sort"
	"time"

	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/ntuple"
)

// bestMove picks the greedy move for g: the legal move maximising
// reward + V(afterstate). Returns the move, its afterstate (packed), the reward,
// and ok=false if no move is legal (terminal).
func bestMove(net *ntuple.Network, g *engine.Game) (mv int, after uint64, reward int, ok bool) {
	cur := g.Score()
	best := math.Inf(-1)
	mv = -1
	for a := 0; a < 4; a++ {
		nb, _, changeNum := gameboard.MakeMove(g.Board, a)
		if changeNum == 0 {
			continue
		}
		ab := engine.PackBoard(nb)
		r := engine.ScoreBB(ab) - cur
		if eval := float64(r) + net.Value(ab); eval > best {
			best, mv, after, reward = eval, a, ab, r
		}
	}
	return mv, after, reward, mv >= 0
}

// trainGame plays one self-play game, updating net by afterstate TD(0):
// V(s'_t) <- V(s'_t) + alpha * ( r_{t+1} + V(s'_{t+1}) - V(s'_t) ), with a target
// of 0 for the last afterstate (no future reward after the game ends).
func trainGame(net *ntuple.Network, seed int64, alpha float64, maxMoves int) {
	g := engine.NewGame(seed)
	var prev uint64
	havePrev := false
	for g.Moves < maxMoves {
		mv, after, reward, ok := bestMove(net, g)
		if !ok {
			break
		}
		if havePrev {
			target := float64(reward) + net.Value(after)
			net.Update(prev, alpha*(target-net.Value(prev)))
		}
		prev, havePrev = after, true
		g.Step(mv)
	}
	if havePrev {
		net.Update(prev, alpha*(0-net.Value(prev)))
	}
}

// evalGame plays one greedy game with no learning.
func evalGame(net *ntuple.Network, seed int64, maxMoves int) (score, maxTile int) {
	g := engine.NewGame(seed)
	for g.Moves < maxMoves {
		mv, _, _, ok := bestMove(net, g)
		if !ok {
			break
		}
		g.Step(mv)
	}
	return g.Score(), g.MaxTile()
}

func evalAndReport(net *ntuple.Network, trained, n, maxMoves int, elapsed time.Duration) {
	scores := make([]int, n)
	var total, maxScore, r3072, r6144 int
	for s := 1; s <= n; s++ {
		score, maxTile := evalGame(net, int64(s), maxMoves)
		scores[s-1] = score
		total += score
		if score > maxScore {
			maxScore = score
		}
		if maxTile >= 3072 {
			r3072++
		}
		if maxTile >= 6144 {
			r6144++
		}
	}
	sort.Ints(scores)
	fmt.Printf("[%8d games | %5.0fs] eval(N=%d): mean=%8.0f median=%7d max=%8d | 3072=%4.1f%% 6144=%4.1f%%\n",
		trained, elapsed.Seconds(), n, float64(total)/float64(n), scores[n/2], maxScore,
		100*float64(r3072)/float64(n), 100*float64(r6144)/float64(n))
}

func main() {
	games := flag.Int("games", 200000, "self-play training games")
	alpha := flag.Float64("alpha", 0.1, "TD learning rate")
	maxMoves := flag.Int("maxmoves", 30000, "safety move cap per game")
	evalEvery := flag.Int("eval-every", 20000, "evaluate every N training games")
	evalN := flag.Int("eval-n", 200, "eval games (fixed held-out seeds 1..eval-n)")
	trainSeed := flag.Int64("train-seed", 10_000_000, "base seed for training games (disjoint from eval)")
	out := flag.String("out", "models/ntuple.gob", "save the trained network here")
	resume := flag.String("resume", "", "resume from an existing network file")
	flag.Parse()

	var net *ntuple.Network
	if *resume != "" {
		var err error
		if net, err = ntuple.Load(*resume); err != nil {
			fmt.Fprintf(os.Stderr, "resume: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("Resumed network from %s (%d tuples)\n", *resume, len(net.Tuples))
	} else {
		net = ntuple.New(ntuple.DefaultTuples)
	}

	fmt.Printf("Training %d games, alpha=%.3f, %d tuples, eval seeds 1..%d (train seeds from %d)\n",
		*games, *alpha, len(net.Tuples), *evalN, *trainSeed)
	start := time.Now()
	evalAndReport(net, 0, *evalN, *maxMoves, 0) // baseline (untrained)
	for i := 0; i < *games; i++ {
		trainGame(net, *trainSeed+int64(i), *alpha, *maxMoves)
		if (i+1)%*evalEvery == 0 || i+1 == *games {
			evalAndReport(net, i+1, *evalN, *maxMoves, time.Since(start))
			if err := net.Save(*out); err != nil { // checkpoint each eval
				fmt.Fprintf(os.Stderr, "save: %v\n", err)
			}
		}
	}
	fmt.Printf("Done in %.0fs. Network saved to %s\n", time.Since(start).Seconds(), *out)
}
