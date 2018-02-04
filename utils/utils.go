package utils

import (
	"fmt"
	"math"

	"github.com/halfrost/threes-ai/gameboard"
)

const (
	lostPenaltyWeight       = 149565.91439596863
	monotonicityPowerWeight = 1.9147186027686733
	monotonicityWeight      = 35.952280239746
	sumPowerWeight          = 1.3372030706843374
	sumWeight               = 95.6296369277664
	mergesWeight            = 189.79612634521368
	oneTwoMergesWeight      = 706.9021407486573
	emptyWeight             = 504.35749738547133
)

var rowLeftTable [65536]uint16
var rowRightTable [65536]uint16
var colUpTable [65536]uint64
var colDownTable [65536]uint64
var rowMaxTable [65536]int64
var heurScoreTable [65536]float64
var scoreTable [65536]float64

var valueMap = map[int]int{
	0: 0, 1: 1, 2: 2, 3: 3, 4: 6, 5: 12, 6: 24, 7: 48, 8: 96, 9: 192, 10: 384, 11: 768, 12: 1536, 13: 3072, 14: 6144, 15: 12288,
}

const deBruijn32 = 0x077CB531

var deBruijn32tab = [32]byte{
	0, 1, 28, 2, 29, 14, 24, 3, 30, 22, 20, 15, 25, 17, 4, 8,
	31, 27, 13, 23, 21, 19, 16, 7, 26, 12, 18, 6, 11, 5, 10, 9,
}

// GetBoard 从64位数字中获取棋盘,获得的棋盘是 0 - 15 的映射以后的值
func GetBoard(stream uint64) [][]int {
	board := make([][]int, gameboard.BOARDHEIGHT)
	for i := range board {
		subArray := make([]int, gameboard.BOARDWIDTH)
		for j := range subArray {
			subArray[j] = int((stream << (64 - (uint(i)*gameboard.BOARDWIDTH+uint(j)+1)*4)) >> 60)
		}
		board[i] = subArray
	}
	return board
}

// PrintfBoard 打印棋盘
func PrintfBoard(board [][]int) {
	fmt.Println()
	fmt.Printf("******************************\n")
	fmt.Printf("******当***前***棋***盘*******\n")
	fmt.Printf("******************************\n")
	fmt.Printf("***------------------------***\n")
	for i := range board {
		fmt.Printf("**|")
		for _, v := range board[i] {
			fmt.Printf("%6d", valueMap[v])
		}
		fmt.Printf("|**\n")
	}
	fmt.Printf("***------------------------***\n")
	fmt.Printf("******************************\n")
	fmt.Printf("******************************\n")
}

// GetCandidates 从32位数字中获取候选人和最大砖块
func GetCandidates(stream uint32) ([]int, int) {
	maxC := int(stream >> 24)
	cand := make([]int, 3)
	for i := range cand {
		cand[i] = int((stream << (32 - (uint32(i)+1)*8)) >> 24)
	}
	return cand, maxC
}

// GetNextBrick 从16位数字中获取下一个砖块
func GetNextBrick(stream uint16) []int {
	nextBrick := make([]int, 0)
	for x := stream; x != 0; x &= x - 1 {
		nextBrick = append(nextBrick, valueMap[trailingZeros16(x)])
	}
	return nextBrick
}

func trailingZeros16(x uint16) (n int) {
	return int(deBruijn32tab[uint32(x&-x)*deBruijn32>>(32-5)])
}

// PrintfGame 打印游戏状态
func PrintfGame(board [][]int, candidate []int, nextBrick []int) {
	fmt.Println()
	PrintfBoard(board)
	fmt.Printf("******当前分数:%8d*******\n", gameScore(board))
	fmt.Printf("******************************\n")
	fmt.Printf("****候选砖块:%4d,%4d,%4d***\n", valueMap[candidate[0]], valueMap[candidate[1]], valueMap[candidate[2]])
	fmt.Printf("****砖块统计:1:%2d,2:%2d,3:%2d***\n", valueMap[candidate[0]], valueMap[candidate[1]], valueMap[candidate[2]])
	fmt.Printf("******************************\n\n\n")
}

func gameScore(board [][]int) int {
	sum := 0
	for i := range board {
		for _, v := range board[i] {
			if v >= 3 {
				sum += int(math.Pow(3, float64(v-2)))
			}
		}
	}
	return sum
}

// Min return min
func Min(x, y int) int {
	if x < y {
		return x
	}
	return y
}

// Max return max
func Max(x, y int) int {
	if x > y {
		return x
	}
	return y
}

// MaxUint return max
func MaxUint(x, y uint) int64 {
	if x > y {
		return int64(x)
	}
	return int64(y)
}

// MaxInt64 return max
func MaxInt64(x, y int64) int64 {
	if x > y {
		return x
	}
	return y
}

// MinFloat64 return min
func MinFloat64(x, y float64) float64 {
	if x < y {
		return x
	}
	return y
}

//ReverseRow ...
func ReverseRow(row uint16) uint {
	return uint((row >> 12) | ((row >> 4) & 0x00F0) | ((row << 4) & 0x0F00) | (row << 12))
}

// UnpackCol ...
func UnpackCol(row uint16) uint64 {
	tmp := uint64(row)
	return (tmp | (tmp << 12) | (tmp << 24) | (tmp << 36)) & 0x000F000F000F000F
}

// InitGameState 初始化游戏状态,打表
func InitGameState() {

	line := make([]uint, 4)
	var row uint
	for row = 0; row < 65536; row++ {
		line[0] = uint((row >> 0) & 0xf)
		line[1] = uint((row >> 4) & 0xf)
		line[2] = uint((row >> 8) & 0xf)
		line[3] = uint((row >> 12) & 0xf)

		score := 0.0
		for i := 0; i < 4; i++ {
			rank := line[i]
			if rank >= 3 {
				score += math.Pow(3, float64(rank-2))
			}
		}
		scoreTable[row] = score
		rowMaxTable[row] = MaxInt64(MaxUint(line[0], line[1]), MaxUint(line[2], line[3]))

		var sum float64
		empty := 0
		merges := 0
		oneTwoMerges := 0

		prev := 0
		counter := 0
		for i := 0; i < 4; i++ {
			rank := line[i]
			sum += math.Pow(float64(rank), float64(sumPowerWeight))
			if rank == 0 {
				empty++
			} else {
				if prev == int(rank) {
					counter++
				} else if counter > 0 {
					merges += 1 + counter
					counter = 0
				}
				prev = int(rank)
			}
		}
		if counter > 0 {
			merges += 1 + counter
		}
		for i := 1; i < 4; i++ {
			if (line[i-1] == 1 && line[i] == 2) || (line[i-1] == 2 && line[i] == 1) {
				oneTwoMerges++
			}
		}

		var monotonicityLeft float64
		var monotonicityRight float64
		for i := 1; i < 4; i++ {
			if line[i-1] > line[i] {
				monotonicityLeft += math.Pow(float64(line[i-1]), monotonicityPowerWeight) - math.Pow(float64(line[i]), monotonicityPowerWeight)
			} else {
				monotonicityRight += math.Pow(float64(line[i]), monotonicityPowerWeight) - math.Pow(float64(line[i-1]), monotonicityPowerWeight)
			}
		}

		heurScoreTable[row] = lostPenaltyWeight + emptyWeight*float64(empty) + mergesWeight*float64(merges) + oneTwoMergesWeight*float64(oneTwoMerges) - monotonicityWeight*MinFloat64(monotonicityLeft, monotonicityRight) - sumWeight*float64(sum)

		// execute a move to the left
		var i int
		for i = 0; i < 3; i++ {
			if line[i] == 0 {
				line[i] = line[i+1]
				break
			} else if line[i] == 1 && line[i+1] == 2 {
				line[i] = 3
				break
			} else if line[i] == 2 && line[i+1] == 1 {
				line[i] = 3
				break
			} else if line[i] == line[i+1] && line[i] >= 3 {
				if line[i] != 15 {
					line[i]++
				}
				break
			}
		}

		if i == 3 {
			continue
		}

		for j := i + 1; j < 3; j++ {
			line[j] = line[j+1]
		}
		line[3] = 0

		result := (line[0] << 0) | (line[1] << 4) | (line[2] << 8) | (line[3] << 12)
		revResult := ReverseRow(uint16(result))
		revRow := ReverseRow(uint16(row))

		rowLeftTable[row] = uint16(row ^ result)
		rowRightTable[revRow] = uint16(revRow ^ revResult)
		colUpTable[row] = UnpackCol(uint16(row)) ^ UnpackCol(uint16(result))
		colDownTable[revRow] = UnpackCol(uint16(revRow)) ^ UnpackCol(uint16(revResult))
	}
}
