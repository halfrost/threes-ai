// Package ntuple implements an N-tuple network value function over the bitboard,
// the learned replacement for the hand-tuned heuristic. A network is a set of
// tuples (small patterns of board cells); each tuple maps the tile indices of
// its cells to a weight via a lookup table. The board value is the sum of those
// weights over every tuple and all 8 board symmetries (rotations + reflections),
// which share weights for sample efficiency. Weights are learned by temporal-
// difference self-play (see cmd/train). This is the standard, strong approach for
// 2048-like games (Szubert & Jaskowski 2014; Yeh et al. 2016 for Threes).
package ntuple

// symmetries[s][i] is the cell index that cell i maps to under the s-th symmetry
// of the 4x4 board (cell (r,c) = r*4+c). The 8 symmetries are the dihedral group.
var symmetries [8][16]int

func init() {
	tf := []func(r, c int) (int, int){
		func(r, c int) (int, int) { return r, c },         // identity
		func(r, c int) (int, int) { return c, 3 - r },     // rotate 90
		func(r, c int) (int, int) { return 3 - r, 3 - c }, // rotate 180
		func(r, c int) (int, int) { return 3 - c, r },     // rotate 270
		func(r, c int) (int, int) { return r, 3 - c },     // flip columns
		func(r, c int) (int, int) { return 3 - r, c },     // flip rows
		func(r, c int) (int, int) { return c, r },         // transpose
		func(r, c int) (int, int) { return 3 - c, 3 - r }, // anti-transpose
	}
	for s := 0; s < 8; s++ {
		for i := 0; i < 16; i++ {
			nr, nc := tf[s](i/4, i%4)
			symmetries[s][i] = nr*4 + nc
		}
	}
}

// DefaultTuples is a compact starter set: two 4-in-a-line shapes and two 2x2
// squares. With the 8 symmetries these already cover all rows, columns and
// quadrants. Each 4-cell tuple is a 16^4 = 65536-entry table (256 KB as
// float32), so the whole network is ~1 MB — small, fast, and downloadable for a
// WASM demo, but too low-capacity for strong play (it plateaus quickly).
var DefaultTuples = [][]int{
	{0, 1, 2, 3},  // top edge line
	{4, 5, 6, 7},  // second row line
	{0, 1, 4, 5},  // top-left 2x2 square
	{1, 2, 5, 6},  // top-middle 2x2 square
}

// BigTuples is the higher-capacity set for strong play: 6-cell shapes (2x3 / 3x2
// rectangles and an L). Each is a 16^6 = 16.7M-entry table (~67 MB as float32),
// ~270 MB total — the standard size range for strong 2048/Threes N-tuple nets
// (Szubert & Jaskowski, Matsuzaki). Too large to ship to a browser, but the
// right choice for the research model trained on the cloud box.
var BigTuples = [][]int{
	{0, 1, 2, 4, 5, 6},  // 2x3 rectangle
	{0, 1, 2, 3, 4, 5},  // top row + two below
	{0, 1, 4, 5, 8, 9},  // 3x2 rectangle
	{1, 2, 5, 6, 9, 10}, // 3x2 rectangle, centre
}

// TuplesByName selects a named tuple set ("small" or "big").
func TuplesByName(name string) [][]int {
	if name == "big" {
		return BigTuples
	}
	return DefaultTuples
}

// Network is an N-tuple value function.
type Network struct {
	Tuples  [][]int     `json:"tuples"`
	Weights [][]float32 `json:"weights"`
}

// New creates a zero-initialised network for the given tuple shapes.
func New(tuples [][]int) *Network {
	n := &Network{Tuples: tuples, Weights: make([][]float32, len(tuples))}
	for t, cells := range tuples {
		size := 1
		for range cells {
			size *= 16
		}
		n.Weights[t] = make([]float32, size)
	}
	return n
}

func nibble(board uint64, cell int) int { return int((board >> (uint(cell) * 4)) & 0xF) }

// feature returns the weight-table index for tuple t under symmetry s.
func (n *Network) feature(board uint64, t, s int) int {
	idx := 0
	for _, c := range n.Tuples[t] {
		idx = idx*16 + nibble(board, symmetries[s][c])
	}
	return idx
}

// Value returns the network's estimate for a board: the summed weight of every
// tuple over all 8 symmetries.
func (n *Network) Value(board uint64) float64 {
	var v float64
	for t := range n.Tuples {
		w := n.Weights[t]
		for s := 0; s < 8; s++ {
			v += float64(w[n.feature(board, t, s)])
		}
	}
	return v
}

// Update nudges the value of board by delta, spreading it evenly across all
// active weights (tuples x symmetries), so a subsequent Value(board) moves by
// ~delta. Used by the TD learner with delta = alpha * tdError.
func (n *Network) Update(board uint64, delta float64) {
	per := float32(delta / float64(len(n.Tuples)*8))
	for t := range n.Tuples {
		w := n.Weights[t]
		for s := 0; s < 8; s++ {
			w[n.feature(board, t, s)] += per
		}
	}
}
