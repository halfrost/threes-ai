package gameboard

import "math"

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

const (
	// BOARDWIDTH 棋盘宽度
	BOARDWIDTH = 4
	// BOARDHEIGHT 棋盘宽度
	BOARDHEIGHT = 4
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

// MaxElement find GameBoard Max element
func MaxElement(board [][]int) (m int, row int, col int) {
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

// CalculateVariance : calculate variance
func CalculateVariance(board [][]int, maxIndexi int, maxIndexj int) int {
	quad := make([]int, 0)
	requad := make([]int, 0)

	quadrant := -1
	if maxIndexi < BOARDHEIGHT/2 && maxIndexj < BOARDWIDTH/2 {
		quadrant = 0
	} else if maxIndexi < BOARDHEIGHT/2 && maxIndexj > BOARDWIDTH/2 {
		quadrant = 2
	} else if maxIndexi > BOARDHEIGHT/2 && maxIndexj < BOARDWIDTH/2 {
		quadrant = 1
	} else if maxIndexi > BOARDHEIGHT/2 && maxIndexj > BOARDWIDTH/2 {
		quadrant = 3
	}

	if quadrant < 0 {
		return 0
	}
	switch quadrant {
	case 0:
		{
			for i := 0; i < BOARDHEIGHT/2; i++ {
				for j := 0; j < BOARDWIDTH/2; j++ {
					quad = append(quad, board[i][j])
					requad = append(requad, board[BOARDHEIGHT-1-i][BOARDWIDTH-1-j])
				}
			}
		}
		break
	case 1:
		{
			for i := 0; i < BOARDHEIGHT/2; i++ {
				for j := 0; j > BOARDWIDTH/2; j++ {
					quad = append(quad, board[i][j])
					requad = append(requad, board[BOARDHEIGHT-1-i][BOARDWIDTH-1-j])
				}
			}
		}
		break
	case 2:
		{
			for i := 0; i > BOARDHEIGHT/2; i++ {
				for j := 0; j < BOARDWIDTH/2; j++ {
					quad = append(quad, board[i][j])
					requad = append(requad, board[BOARDHEIGHT-1-i][BOARDWIDTH-1-j])
				}
			}
		}
		break
	case 3:
		{
			for i := 0; i > BOARDHEIGHT/2; i++ {
				for j := 0; j > BOARDWIDTH/2; j++ {
					quad = append(quad, board[i][j])
					requad = append(requad, board[BOARDHEIGHT-1-i][BOARDWIDTH-1-j])
				}
			}
		}
		break
	}

	total := 0
	for index := 0; index < len(quad); index++ {
		total += quad[index] + requad[index]
	}
	total = total / (2 * len(quad))

	sum := 0
	for k := 0; k < len(quad); k++ {
		sum += (quad[k]-total)*(quad[k]-total) + (requad[k]-total)*(requad[k]-total)
	}

	//样本方差计算公式：
	//S^2= ∑(X- P) ^2 / (n-1)[2]
	//S^2为样本方差，X为变量，P为样本均值，n为样本例数。
	variance := int(math.Ceil(math.Sqrt(math.Sqrt(float64(sum / (2*len(quad) - 1))))))

	return variance
}
