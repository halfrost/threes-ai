package engine

import (
	"math/rand"
	"testing"
)

func TestScore(t *testing.T) {
	g := &Game{Board: newBoard()}
	g.Board[0][0] = 3 // value 3   -> 3^1 = 3
	g.Board[0][1] = 4 // value 6   -> 3^2 = 9
	g.Board[0][2] = 5 // value 12  -> 3^3 = 27
	g.Board[1][0] = 1 // value 1   -> 0
	g.Board[1][1] = 2 // value 2   -> 0
	if got, want := g.Score(), 3+9+27; got != want {
		t.Fatalf("Score=%d want %d", got, want)
	}
}

func TestBagComposition(t *testing.T) {
	g := &Game{rng: rand.New(rand.NewSource(1))}
	g.refillBag()
	counts := map[int]int{}
	for i := 0; i < 12; i++ {
		counts[g.drawBag()]++
	}
	for v := 1; v <= 3; v++ {
		if counts[v] != 4 {
			t.Fatalf("bag value %d appeared %d times, want 4", v, counts[v])
		}
	}
	if len(g.bag) != 0 {
		t.Fatalf("bag not empty after 12 draws: %d left", len(g.bag))
	}
}

func TestNoBonusBelow48(t *testing.T) {
	g := &Game{rng: rand.New(rand.NewSource(2)), Board: newBoard()}
	g.Board[0][0] = 6 // value 24 -> max < 48, bonus must never fire
	for i := 0; i < 5000; i++ {
		if _, bonus := g.genTile(); bonus {
			t.Fatal("bonus generated with max tile value 24 (< 48)")
		}
		g.refillBag()
	}
}

func TestBonusRange(t *testing.T) {
	g := &Game{rng: rand.New(rand.NewSource(3)), Board: newBoard()}
	g.Board[0][0] = 10 // value 384 -> bonus in {6..48} == indices 4..7
	saw := false
	for i := 0; i < 100000; i++ {
		idx, bonus := g.genTile()
		if bonus {
			saw = true
			if idx < 4 || idx > 7 {
				t.Fatalf("bonus index %d out of expected range [4,7]", idx)
			}
		}
		g.refillBag()
	}
	if !saw {
		t.Fatal("no bonus tile seen in 100000 tries with max value 384")
	}
}

func TestDeterminism(t *testing.T) {
	trace := func() []int {
		g := NewGame(42)
		var seq []int
		for k := 0; k < 300 && !g.Over(); k++ {
			moved := false
			for mm := 0; mm < 4; mm++ {
				if g.Step((k + mm) % 4) {
					moved = true
					break
				}
			}
			if !moved {
				break
			}
			seq = append(seq, g.Board[0][0], g.Next, g.Score())
		}
		return seq
	}
	a, b := trace(), trace()
	if len(a) != len(b) {
		t.Fatalf("trace length mismatch: %d vs %d", len(a), len(b))
	}
	for i := range a {
		if a[i] != b[i] {
			t.Fatalf("determinism broken at %d: %d vs %d", i, a[i], b[i])
		}
	}
	if len(a) == 0 {
		t.Fatal("empty trace")
	}
}
