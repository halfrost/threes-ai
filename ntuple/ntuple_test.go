package ntuple

import (
	"math"
	"math/rand"
	"testing"
)

func randBoard(rng *rand.Rand) uint64 {
	var b uint64
	for i := 0; i < 16; i++ {
		b |= uint64(rng.Intn(16)) << (uint(i) * 4)
	}
	return b
}

// applySym remaps a board by symmetry s (new cell i takes old cell sym[s][i]).
func applySym(board uint64, s int) uint64 {
	var nb uint64
	for i := 0; i < 16; i++ {
		v := (board >> (uint(symmetries[s][i]) * 4)) & 0xF
		nb |= v << (uint(i) * 4)
	}
	return nb
}

func TestSizesAndZero(t *testing.T) {
	n := New(DefaultTuples)
	for i, w := range n.Weights {
		want := 1
		for range n.Tuples[i] {
			want *= 16
		}
		if len(w) != want {
			t.Fatalf("tuple %d weight size %d, want %d", i, len(w), want)
		}
	}
	if v := n.Value(randBoard(rand.New(rand.NewSource(1)))); v != 0 {
		t.Fatalf("fresh network value = %v, want 0", v)
	}
}

func TestUpdateRaisesValue(t *testing.T) {
	n := New(DefaultTuples)
	b := randBoard(rand.New(rand.NewSource(2)))
	before := n.Value(b)
	n.Update(b, 100)
	after := n.Value(b)
	if after <= before {
		t.Fatalf("Update did not raise value: before=%v after=%v", before, after)
	}
	// With no symmetric collisions the value moves by ~delta; collisions only add.
	if after < 99 {
		t.Fatalf("Update moved value too little: %v (want >= ~100)", after)
	}
}

// TestSymmetryInvariance is the correctness anchor: because the network sums over
// all 8 symmetries, its value must be identical for a board and any symmetry of it.
func TestSymmetryInvariance(t *testing.T) {
	rng := rand.New(rand.NewSource(3))
	n := New(DefaultTuples)
	// Train a few random boards so weights are non-trivial.
	for i := 0; i < 200; i++ {
		n.Update(randBoard(rng), rng.Float64()*10-5)
	}
	for i := 0; i < 500; i++ {
		b := randBoard(rng)
		base := n.Value(b)
		for s := 0; s < 8; s++ {
			if got := n.Value(applySym(b, s)); math.Abs(got-base) > 1e-4 {
				t.Fatalf("symmetry %d changed value: base=%v got=%v (board=%016x)", s, base, got, b)
			}
		}
	}
}
