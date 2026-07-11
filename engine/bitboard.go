package engine

// Bitboard engine: the whole 4x4 board is a single uint64, each cell a 4-bit
// tile index. Cell (r,c) lives at bit (r*4+c)*4 — row-major, LSB is (0,0). This
// matches utils.GetBoard's packing, so it is interchangeable with the c-shared
// interface. Moves are done with precomputed per-line lookup tables instead of
// cloning slices, which is the key speedup for search and self-play.
//
// A "line" is 4 cells = 16 bits. Threes moves shift a line by at most one step
// and merge at most one pair, exactly as gameboard.MakeMove does. The tables are
// validated to be bit-for-bit identical to gameboard.MakeMove (see bitboard_test).

var (
	lineLow, lineHigh       [65536]uint16 // line after moving toward index 0 / index 3
	lineLowChg, lineHighChg [65536]bool   // whether that line changed
	tablesReady             bool
)

// InitBitboard builds the move lookup tables. Safe to call multiple times.
func InitBitboard() {
	if tablesReady {
		return
	}
	for line := 0; line < 65536; line++ {
		c := decodeLine(uint16(line))
		r, chg := moveLineLowCells(c)
		lineLow[line] = encodeLine(r)
		lineLowChg[line] = chg

		rc := [4]int{c[3], c[2], c[1], c[0]} // reverse -> low-move -> reverse == high-move
		rr, chg2 := moveLineLowCells(rc)
		lineHigh[line] = encodeLine([4]int{rr[3], rr[2], rr[1], rr[0]})
		lineHighChg[line] = chg2
	}
	tablesReady = true
}

func init() { InitBitboard() }

func decodeLine(line uint16) [4]int {
	return [4]int{int(line & 0xF), int((line >> 4) & 0xF), int((line >> 8) & 0xF), int((line >> 12) & 0xF)}
}

func encodeLine(c [4]int) uint16 {
	return uint16(c[0]) | uint16(c[1])<<4 | uint16(c[2])<<8 | uint16(c[3])<<12
}

// mergeVal reports the merged tile of two adjacent cells a (leading) and b, per
// Threes rules: 1+2 -> 3; equal tiles >= 3 combine one rank (capped at 15). It
// mirrors gameboard.MakeMove, including that two 15s still "merge" (compact)
// without increasing in value.
func mergeVal(a, b int) (int, bool) {
	if (a == 1 && b == 2) || (a == 2 && b == 1) {
		return 3, true
	}
	if a == b && a >= 3 {
		if a != 15 {
			return a + 1, true
		}
		return 15, true
	}
	return 0, false
}

// moveLineLowCells moves a line one step toward index 0, merging the first
// eligible pair, matching gameboard.MakeMove's per-lane scan. At the first event
// position p, cells 0..p-1 are untouched, cell p becomes the slid/merged tile,
// and cells p+1.. are pulled up one (tail compaction), with the last cell cleared.
func moveLineLowCells(c [4]int) ([4]int, bool) {
	for p := 0; p < 3; p++ {
		slide := c[p] == 0 && c[p+1] != 0
		m, merge := mergeVal(c[p], c[p+1])
		if !slide && !merge {
			continue
		}
		var res [4]int
		copy(res[:], c[:p]) // 0..p-1 unchanged
		if merge {
			res[p] = m
		} else {
			res[p] = c[p+1]
		}
		for q := p + 1; q < 3; q++ { // pull the tail (orig p+2..3) up into p+1..2
			res[q] = c[q+1]
		}
		res[3] = 0
		return res, true
	}
	return c, false
}

// PackBoard packs a 4x4 index board into a uint64 (cell (r,c) at bit (r*4+c)*4).
func PackBoard(b [][]int) uint64 {
	var x uint64
	for r := 0; r < 4; r++ {
		for c := 0; c < 4; c++ {
			x |= uint64(b[r][c]&0xF) << (uint(r*4+c) * 4)
		}
	}
	return x
}

// UnpackBoard is the inverse of PackBoard.
func UnpackBoard(x uint64) [][]int {
	b := newBoard()
	for r := 0; r < 4; r++ {
		for c := 0; c < 4; c++ {
			b[r][c] = int((x >> (uint(r*4+c) * 4)) & 0xF)
		}
	}
	return b
}

// transpose swaps rows and columns of the 4x4 nibble board (standard 2048 trick).
func transpose(x uint64) uint64 {
	a1 := x & 0xF0F00F0FF0F00F0F
	a2 := x & 0x0000F0F00000F0F0
	a3 := x & 0x0F0F00000F0F0000
	a := a1 | (a2 << 12) | (a3 >> 12)
	b1 := a & 0xFF00FF0000FF00FF
	b2 := a & 0x00FF00FF00000000
	b3 := a & 0x00000000FF00FF00
	return b1 | (b2 >> 24) | (b3 << 24)
}

// MoveBitboard applies a move (0=UP,1=DOWN,2=LEFT,3=RIGHT) to a packed board.
// It returns the new board, which lanes changed (index = column for UP/DOWN,
// row for LEFT/RIGHT, matching gameboard.MakeMove's change slice), and whether
// anything moved at all.
func MoveBitboard(b uint64, move int) (nb uint64, changed [4]bool, any bool) {
	switch move {
	case 2: // LEFT: each row toward index 0
		for i := 0; i < 4; i++ {
			row := uint16((b >> (uint(i) * 16)) & 0xFFFF)
			nb |= uint64(lineLow[row]) << (uint(i) * 16)
			if lineLowChg[row] {
				changed[i], any = true, true
			}
		}
	case 3: // RIGHT: each row toward index 3
		for i := 0; i < 4; i++ {
			row := uint16((b >> (uint(i) * 16)) & 0xFFFF)
			nb |= uint64(lineHigh[row]) << (uint(i) * 16)
			if lineHighChg[row] {
				changed[i], any = true, true
			}
		}
	case 0: // UP: transpose so columns become rows, move toward index 0
		t := transpose(b)
		var tb uint64
		for i := 0; i < 4; i++ {
			row := uint16((t >> (uint(i) * 16)) & 0xFFFF)
			tb |= uint64(lineLow[row]) << (uint(i) * 16)
			if lineLowChg[row] {
				changed[i], any = true, true
			}
		}
		nb = transpose(tb)
	case 1: // DOWN
		t := transpose(b)
		var tb uint64
		for i := 0; i < 4; i++ {
			row := uint16((t >> (uint(i) * 16)) & 0xFFFF)
			tb |= uint64(lineHigh[row]) << (uint(i) * 16)
			if lineHighChg[row] {
				changed[i], any = true, true
			}
		}
		nb = transpose(tb)
	}
	return nb, changed, any
}
