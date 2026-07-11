package utils

// HeurScoreBitboard is the bitboard form of GetHeurWeightScore: it sums the
// per-row and per-column heuristic table over a packed uint64 board. Rows are
// the four contiguous 16-bit chunks; each column's nibbles are gathered into a
// 16-bit key. Requires InitGameScoreTable() to have been called.
func HeurScoreBitboard(b uint64) float64 {
	var res float64
	for i := 0; i < 4; i++ {
		res += heurScoreTable[(b>>(uint(i)*16))&0xFFFF]
	}
	for j := 0; j < 4; j++ {
		var col uint64
		for i := 0; i < 4; i++ {
			col |= ((b >> (uint(i*4+j) * 4)) & 0xF) << (uint(i) * 4)
		}
		res += heurScoreTable[col]
	}
	return res
}
