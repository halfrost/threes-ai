package engine

import (
	"math/rand"
	"testing"
)

func TestScoreBBMatchesGameScore(t *testing.T) {
	rng := rand.New(rand.NewSource(5))
	for i := 0; i < 100000; i++ {
		b := randomBoard(rng)
		g := &Game{Board: b}
		if got, want := ScoreBB(PackBoard(b)), g.Score(); got != want {
			t.Fatalf("ScoreBB=%d Game.Score=%d on %v", got, want, b)
		}
	}
}
