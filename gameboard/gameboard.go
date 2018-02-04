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
func Clone(board [][]int) [][]int {

	bClone := make([][]int, BOARDHEIGHT)
	for i := range board {
		subArray := make([]int, BOARDWIDTH)
		for j := range subArray {
			subArray[j] = board[i][j]
		}
		bClone[i] = subArray
	}

	return bClone
}

// MakeMove ...
func MakeMove(board [][]int, move int) (b [][]int, change []int, num int) {
	newBoard := Clone(board)
	changeNum := 0
	change = make([]int, 4)
	var isChange bool
	switch move {
	case 0: // UP
		{
			for y := 0; y < 4; y++ {
				isChange = false
				for x := 0; x < 3; x++ {
					if newBoard[x][y] <= 0 {
						newBoard[x][y] = newBoard[x+1][y]
						newBoard[x+1][y] = 0
						changeNum++
						change[y] = 1
						isChange = true
					} else if (newBoard[x][y] == newBoard[x+1][y] && newBoard[x][y] >= 3) || (newBoard[x][y] == 1 && newBoard[x+1][y] == 2) || (newBoard[x][y] == 2 && newBoard[x+1][y] == 1) {
						newBoard[x][y] += newBoard[x+1][y]
						newBoard[x+1][y] = 0
						changeNum++
						change[y] = 1
						isChange = true
					}
					if isChange {
						for j := x + 1; j < 3; j++ {
							newBoard[j][y] = newBoard[j+1][y]
						}
						newBoard[3][y] = 0
						break
					}
				}
			}
		}
		break
	case 1: // DOWN
		{
			for y := 0; y < 4; y++ {
				isChange = false
				for x := 3; x > 0; x-- {
					if newBoard[x][y] <= 0 {
						newBoard[x][y] = newBoard[x-1][y]
						newBoard[x-1][y] = 0
						changeNum++
						change[y] = 1
						isChange = true
					} else if (newBoard[x][y] == newBoard[x-1][y] && newBoard[x][y] >= 3) || (newBoard[x][y] == 1 && newBoard[x-1][y] == 2) || (newBoard[x][y] == 2 && newBoard[x-1][y] == 1) {
						newBoard[x][y] += newBoard[x-1][y]
						newBoard[x-1][y] = 0
						changeNum++
						change[y] = 1
						isChange = true
					}
					if isChange {
						for j := x - 1; j > 0; j-- {
							newBoard[j][y] = newBoard[j-1][y]
						}
						newBoard[0][y] = 0
						break
					}
				}
			}
		}
		break
	case 2: // LEFT
		{
			for x := 0; x < 4; x++ {
				isChange = false
				for y := 0; y < 3; y++ {
					if newBoard[x][y] <= 0 {
						newBoard[x][y] = newBoard[x][y+1]
						newBoard[x][y+1] = 0
						changeNum++
						change[x] = 1
						isChange = true
					} else if (newBoard[x][y] == newBoard[x][y+1] && newBoard[x][y] >= 3) || (newBoard[x][y] == 1 && newBoard[x][y+1] == 2) || (newBoard[x][y] == 2 && newBoard[x][y+1] == 1) {
						newBoard[x][y] += newBoard[x][y+1]
						newBoard[x][y+1] = 0
						changeNum++
						change[x] = 1
						isChange = true
					}
					if isChange {
						for j := y + 1; j < 3; j++ {
							newBoard[x][j] = newBoard[x][j+1]
						}
						newBoard[x][3] = 0
						break
					}
				}
			}
		}
		break
	case 3: // RIGHT
		{
			for x := 0; x < 4; x++ {
				isChange = false
				for y := 3; y > 0; y-- {
					if newBoard[x][y] <= 0 {
						newBoard[x][y] = newBoard[x][y-1]
						newBoard[x][y-1] = 0
						changeNum++
						change[x] = 1
						isChange = true
					} else if (newBoard[x][y] == newBoard[x][y-1] && newBoard[x][y] >= 3) || (newBoard[x][y] == 1 && newBoard[x][y-1] == 2) || (newBoard[x][y] == 2 && newBoard[x][y-1] == 1) {
						newBoard[x][y] += newBoard[x][y-1]
						newBoard[x][y-1] = 0
						changeNum++
						change[x] = 1
						isChange = true
					}

					if isChange {
						for j := y - 1; j > 0; j-- {
							newBoard[x][j] = newBoard[x][j-1]
						}
						newBoard[x][0] = 0
						break
					}
				}
			}
		}
		break
	}

	return newBoard, change, changeNum
}

// InsertBrick ...
func InsertBrick(board [][]int, nextBrick int, move int, changeLine int) [][]int {
	newBoard := Clone(board)
	switch move {
	case 0:
		{
			newBoard[3][changeLine] = nextBrick
		}
		break
	case 1:
		{
			newBoard[0][changeLine] = nextBrick
		}
		break
	case 2:
		{
			newBoard[changeLine][3] = nextBrick
		}
		break
	case 3:
		{
			newBoard[changeLine][0] = nextBrick
		}
		break
	}
	return newBoard
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
