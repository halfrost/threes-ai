package engine

// InsertBrickBB places tile index t at the spawn cell for a given move/lane,
// mirroring gameboard.InsertBrick: a swipe spawns the new tile on the edge
// opposite the move, in the given lane. UP -> row 3, DOWN -> row 0 (lane=col);
// LEFT -> col 3, RIGHT -> col 0 (lane=row).
func InsertBrickBB(b uint64, t, move, lane int) uint64 {
	var r, c int
	switch move {
	case 0: // UP
		r, c = 3, lane
	case 1: // DOWN
		r, c = 0, lane
	case 2: // LEFT
		r, c = lane, 3
	case 3: // RIGHT
		r, c = lane, 0
	}
	pos := uint(r*4+c) * 4
	b &^= 0xF << pos
	b |= uint64(t&0xF) << pos
	return b
}

// MaxIndexBB returns the highest tile index present on the packed board.
func MaxIndexBB(b uint64) int {
	m := 0
	for p := 0; p < 16; p++ {
		if v := int((b >> (uint(p) * 4)) & 0xF); v > m {
			m = v
		}
	}
	return m
}

// CountChanged converts a changed-lane mask to the lane count and a 0/1 slice
// matching gameboard.MakeMove's change slice, for reuse by the search.
func CountChanged(changed [4]bool) (changes [4]int, num int) {
	for k := 0; k < 4; k++ {
		if changed[k] {
			changes[k] = 1
			num++
		}
	}
	return changes, num
}
