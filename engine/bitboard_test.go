package engine

import (
	"math/rand"
	"testing"

	"github.com/halfrost/threes-ai/gameboard"
)

func randomBoard(rng *rand.Rand) [][]int {
	b := newBoard()
	for r := 0; r < 4; r++ {
		for c := 0; c < 4; c++ {
			b[r][c] = rng.Intn(16)
		}
	}
	return b
}

func boardsEqual(a, b [][]int) bool {
	for r := 0; r < 4; r++ {
		for c := 0; c < 4; c++ {
			if a[r][c] != b[r][c] {
				return false
			}
		}
	}
	return true
}

func TestPackRoundtrip(t *testing.T) {
	rng := rand.New(rand.NewSource(7))
	for i := 0; i < 200000; i++ {
		b := randomBoard(rng)
		if !boardsEqual(UnpackBoard(PackBoard(b)), b) {
			t.Fatalf("pack/unpack roundtrip mismatch on %v", b)
		}
	}
}

// TestBitboardMatchesGameboard is the correctness anchor: the fast bitboard move
// must be bit-for-bit identical to gameboard.MakeMove (board, changed lanes, and
// whether anything moved) across millions of random boards and all directions.
func TestBitboardMatchesGameboard(t *testing.T) {
	rng := rand.New(rand.NewSource(12345))
	const N = 2_000_000
	for i := 0; i < N; i++ {
		b := randomBoard(rng)
		move := rng.Intn(4)

		wantBoard, wantChange, wantNum := gameboard.MakeMove(b, move)
		nb, changed, any := MoveBitboard(PackBoard(b), move)
		gotBoard := UnpackBoard(nb)

		if !boardsEqual(gotBoard, wantBoard) {
			t.Fatalf("board mismatch move=%d\n in  =%v\n want=%v\n got =%v", move, b, wantBoard, gotBoard)
		}
		for k := 0; k < 4; k++ {
			if changed[k] != (wantChange[k] == 1) {
				t.Fatalf("changed[%d] mismatch move=%d in=%v want=%v got=%v", k, move, b, wantChange, changed)
			}
		}
		if any != (wantNum != 0) {
			t.Fatalf("any mismatch move=%d in=%v wantNum=%d any=%v", move, b, wantNum, any)
		}
	}
}

func BenchmarkMakeMove(b *testing.B) {
	rng := rand.New(rand.NewSource(1))
	board := randomBoard(rng)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		gameboard.MakeMove(board, i&3)
	}
}

func BenchmarkMoveBitboard(b *testing.B) {
	rng := rand.New(rand.NewSource(1))
	bb := PackBoard(randomBoard(rng))
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		MoveBitboard(bb, i&3)
	}
}
