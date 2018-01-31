package board

// Direction define
type Direction int

const (
	// UP Direction Enum
	UP Direction = iota
	// RIGHT Direction Enum
	RIGHT
	// DOWN Direction Enum
	DOWN
	// LEFT Direction Enum
	LEFT
	// NONE Direction Enum
	NONE
)

// GameBoard define
type GameBoard struct {
	Board [4][4]int
}

var candidate [3]int

// Clone GameBoard Clone
func (b *GameBoard) Clone() *GameBoard {
	bClone := &GameBoard{}
	*bClone = *b
	return bClone
}

// Max find GameBoard Max element
func Max(board [][]int) (m int, row int, col int) {
	max := 0
	i := 0
	j := 0
	for indexi, row := range board {
		for indexj, value := range row {
			if value > max {
				max = value
				i = indexi
				j = indexj
			}
		}
	}
	return max, i, j
}

// FindDiffCount find distinct_tiles, except 0，1，2
func FindDiffCount(board [][]int) int {
	array := make([]int, 16)
	for _, row := range board {
		for _, value := range row {
			if value > 2 {
				array[value]++
			}
		}
	}
	count := 0
	for i := range array {
		if array[i] != 0 {
			count++
		}
	}
	return count
}
