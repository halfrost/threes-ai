package engine

// ScoreBB is the Threes score of a packed board: the sum of 3^(index-2) over
// tiles with index >= 3 (identical to Game.Score, but on a uint64). Used as the
// per-move reward for TD learning: reward = ScoreBB(afterstate) - ScoreBB(state).
func ScoreBB(b uint64) int {
	sum := 0
	for p := 0; p < 16; p++ {
		if v := int((b >> (uint(p) * 4)) & 0xF); v >= 3 {
			s := 1
			for k := 0; k < v-2; k++ {
				s *= 3
			}
			sum += s
		}
	}
	return sum
}
