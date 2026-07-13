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

// BigTuples2 is the highest-capacity set: eight 6-cell shapes spread over the
// top/middle/bottom bands and the left/right columns, so with the 8 symmetries
// they cover the board more densely than BigTuples. ~536 MB of weights as
// float32 (8 x 16^6 x 4B), roughly double BigTuples — the option for pushing
// past the 4x6 greedy plateau (T2). With temporal-coherence accumulators on
// (train -tc) it needs ~3x that (~1.6 GB), which the cloud box can hold.
var BigTuples2 = [][]int{
	{0, 1, 2, 4, 5, 6},    // 2x3 top-left
	{1, 2, 3, 5, 6, 7},    // 2x3 top-right
	{4, 5, 6, 8, 9, 10},   // 2x3 middle band
	{5, 6, 7, 9, 10, 11},  // 2x3 middle-right
	{0, 1, 4, 5, 8, 9},    // 3x2 left column
	{1, 2, 5, 6, 9, 10},   // 3x2 centre column
	{2, 3, 6, 7, 10, 11},  // 3x2 right column
	{4, 5, 8, 9, 12, 13},  // 3x2 lower-left
}

// TuplesByName selects a named tuple set ("small", "big", or "big2").
func TuplesByName(name string) [][]int {
	switch name {
	case "big":
		return BigTuples
	case "big2":
		return BigTuples2
	default:
		return DefaultTuples
	}
}

// Network is an N-tuple value function.
type Network struct {
	Tuples  [][]int     `json:"tuples"`
	Weights [][]float32 `json:"weights"`

	// Temporal-coherence accumulators (training-only, NOT serialised — they are
	// unexported so gob skips them). Per weight: tcN is the signed sum of its
	// updates, tcA the absolute sum; their ratio is the weight's coherence.
	// Allocated by EnableTC; a resumed model restarts its TC state fresh.
	tcN [][]float32
	tcA [][]float32
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

// EnableTC allocates the temporal-coherence accumulators so training can use a
// per-weight adaptive step size (UpdateTC). Call once before training. The
// accumulators are not serialised, so a resumed model starts its TC state fresh.
func (n *Network) EnableTC() {
	n.tcN = make([][]float32, len(n.Weights))
	n.tcA = make([][]float32, len(n.Weights))
	for t := range n.Weights {
		n.tcN[t] = make([]float32, len(n.Weights[t]))
		n.tcA[t] = make([]float32, len(n.Weights[t]))
	}
}

// TCEnabled reports whether EnableTC has been called.
func (n *Network) TCEnabled() bool { return n.tcN != nil }

func abs32(x float32) float32 {
	if x < 0 {
		return -x
	}
	return x
}

// UpdateTC is the temporal-coherence variant of Update: it splits tdError across
// the active weights and scales each weight's step by its own coherence
// |N_i|/A_i in [0,1] — weights whose updates agree in sign keep the full rate,
// oscillating ones are damped (a self-tuning per-weight learning rate on top of
// the global, possibly-annealed, alpha). Requires EnableTC.
func (n *Network) UpdateTC(board uint64, tdError, alpha float64) {
	e := float32(tdError / float64(len(n.Tuples)*8))
	a := float32(alpha)
	for t := range n.Tuples {
		w, N, A := n.Weights[t], n.tcN[t], n.tcA[t]
		for s := 0; s < 8; s++ {
			i := n.feature(board, t, s)
			beta := float32(1)
			if A[i] > 0 {
				beta = abs32(N[i]) / A[i]
			}
			w[i] += a * beta * e
			N[i] += e
			A[i] += abs32(e)
		}
	}
}
