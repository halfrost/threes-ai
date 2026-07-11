package ai

import (
	"math/rand"
	"testing"

	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

func cloneInts(s []int) []int {
	c := make([]int, len(s))
	copy(c, s)
	return c
}

// TestBBSearchMatchesSlice is the correctness anchor for the bitboard port: over
// many real gameplay positions, ExpectSearchBB must choose the same move as the
// original ExpectSearch. Depth is capped low so the slow [][]int search stays
// affordable across hundreds of comparisons.
func TestBBSearchMatchesSlice(t *testing.T) {
	utils.InitGameScoreTable()
	MaxDepthCap = 2
	defer func() { MaxDepthCap = 0 }()

	rng := rand.New(rand.NewSource(99))
	compared, mismatches := 0, 0
	for game := 0; game < 6; game++ {
		g := engine.NewGame(int64(game + 1))
		for steps := 0; steps < 120 && !g.Over(); steps++ {
			b2d := gameboard.Clone(g.Board)
			cand := gameboard.FindCandidates(g.Board)
			next := []int{g.Next}

			m1 := ExpectSearch(gameboard.Clone(b2d), cloneInts(cand), cloneInts(next))
			m2 := ExpectSearchBB(engine.PackBoard(b2d), cloneInts(cand), cloneInts(next))
			compared++
			if m1 != m2 {
				mismatches++
				if mismatches <= 5 {
					t.Logf("mismatch game=%d step=%d board=%v cand=%v next=%v: slice=%d bb=%d",
						game, steps, b2d, cand, next, m1, m2)
				}
			}

			mv := m1
			if mv < 0 || !g.Step(mv) {
				moved := false
				for _, mm := range rng.Perm(4) {
					if g.Step(mm) {
						moved = true
						break
					}
				}
				if !moved {
					break
				}
			}
		}
	}
	t.Logf("compared=%d mismatches=%d", compared, mismatches)
	if mismatches > 0 {
		t.Fatalf("bitboard search decisions differ from slice search in %d/%d positions", mismatches, compared)
	}
}
