// Command diag plays a single self-play game and reports how per-move search
// cost grows as the board fills, so we can choose a tractable depth cap for the
// baseline. It is a throwaway diagnostic, not part of the measurement pipeline.
//
// Usage: go run ./cmd/diag -seed 1 -depthcap 3 -maxmoves 4000
package main

import (
	"flag"
	"fmt"
	"sort"
	"time"

	"github.com/halfrost/threes-ai/ai"
	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

func main() {
	seed := flag.Int64("seed", 1, "seed")
	depthcap := flag.Int("depthcap", 0, "ai.MaxDepthCap (0=uncapped)")
	maxmoves := flag.Int("maxmoves", 4000, "move cap")
	bb := flag.Bool("bb", false, "use the bitboard search")
	flag.Parse()

	utils.InitGameScoreTable()
	ai.MaxDepthCap = *depthcap

	g := engine.NewGame(*seed)
	fmt.Printf("seed=%d depthcap=%d maxmoves=%d bb=%v\n", *seed, *depthcap, *maxmoves, *bb)
	var perMove []float64 // ms
	start := time.Now()
	for g.Moves < *maxmoves {
		t0 := time.Now()
		cand := gameboard.FindCandidates(g.Board)
		var move int
		if *bb {
			move = ai.ExpectSearchBB(engine.PackBoard(g.Board), cand, []int{g.Next})
		} else {
			move = ai.ExpectSearch(g.Board, cand, []int{g.Next})
		}
		ms := float64(time.Since(t0).Microseconds()) / 1000
		if move < 0 || !g.Step(move) {
			break
		}
		perMove = append(perMove, ms)
		if g.Moves%50 == 0 {
			fmt.Printf("  move %4d | maxtile %5d | this move %7.1f ms | cum %6.1fs\n",
				g.Moves, g.MaxTile(), ms, time.Since(start).Seconds())
		}
	}
	total := time.Since(start)

	sort.Float64s(perMove)
	var sum float64
	for _, v := range perMove {
		sum += v
	}
	n := len(perMove)
	fmt.Printf("\n=== RESULT ===\n")
	fmt.Printf("moves=%d  score=%d  maxtile=%d  wall=%.1fs\n", g.Moves, g.Score(), g.MaxTile(), total.Seconds())
	if n > 0 {
		fmt.Printf("per-move ms: avg=%.1f  median=%.1f  p90=%.1f  p99=%.1f  max=%.1f\n",
			sum/float64(n), perMove[n/2], perMove[n*90/100], perMove[min(n*99/100, n-1)], perMove[n-1])
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
