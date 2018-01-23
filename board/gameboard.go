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
	GameBoard [4][4]int
}

var candidate [3]int

// Clone GameBoard Clone
func (b *GameBoard) Clone() *GameBoard {
	bClone := &GameBoard{}
	*bClone = *b
	return bClone
}

// Max find GameBoard Max element
func (b *GameBoard) Max() int {
	max := 0
	for _, row := range b.GameBoard {
		for _, value := range row {
			if value > max {
				max = value
			}
		}
	}
	return max
}
