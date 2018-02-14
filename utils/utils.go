package utils

import (
	"fmt"
	"math"

	"github.com/halfrost/threes-ai/gameboard"
)
import "C"

const (
	lostPenaltyWeight       = 10000.0
	monotonicityPowerWeight = 2.0
	monotonicityWeight      = 40.0
	sumPowerWeight          = 1.0
	sumWeight               = 100.0
	mergesWeight            = 200.0
	oneTwoMergesWeight      = 700.0
	emptyWeight             = 500.0

	// CprobMin ...
	CprobMin = 0.0001
	// CacheDeptLevel ...
	CacheDeptLevel = 6
	// HightBrickFreq ...
	HightBrickFreq = 21
)

var heurScoreTable [65536]float64

var valueMap = map[int]int{
	0: 0, 1: 1, 2: 2, 3: 3, 4: 6, 5: 12, 6: 24, 7: 48, 8: 96, 9: 192, 10: 384, 11: 768, 12: 1536, 13: 3072, 14: 6144, 15: 12288,
}

// ReValueMap ...
var ReValueMap = map[int]int{
	0: 0, 1: 1, 2: 2, 3: 3, 6: 4, 12: 5, 24: 6, 48: 7, 96: 8, 192: 9, 384: 10, 768: 11, 1536: 12, 3072: 13, 6144: 14, 12288: 15,
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
	if len(nextBrick) == 1 {
		fmt.Printf("********候选砖块:%4d*********\n", nextBrick[0])
	} else if len(nextBrick) == 2 {
		fmt.Printf("******候选砖块:%4d,%4d******\n", nextBrick[0], nextBrick[1])
	} else if len(nextBrick) == 3 {
		fmt.Printf("****候选砖块:%4d,%4d,%4d***\n", nextBrick[0], nextBrick[1], nextBrick[2])
	}
	fmt.Printf("****砖块统计:1:%2d,2:%2d,3:%2d***\n", candidate[0], candidate[1], candidate[2])
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

// GetHeurWeightScore ...
func GetHeurWeightScore(board [][]int) float64 {
	var res float64
	res = 0
	var stream uint16
	for i := 0; i < len(board); i++ {
		stream = 0
		for j := len(board[i]) - 1; j >= 0; j-- {
			stream += uint16(board[i][j] << uint(j*4))
		}
		res += heurScoreTable[stream]
	}

	for j := 0; j < len(board); j++ {
		stream = 0
		for i := len(board[j]) - 1; i >= 0; i-- {
			stream += uint16(board[i][j] << uint(i*4))
		}
		res += heurScoreTable[stream]
	}
	return res
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

// InitGameScoreTable 初始化游戏状态,打表
func InitGameScoreTable() {

	line := make([]uint, 4)
	var row uint
	for row = 0; row < 65536; row++ {
		line[0] = uint((row >> 0) & 0xf)
		line[1] = uint((row >> 4) & 0xf)
		line[2] = uint((row >> 8) & 0xf)
		line[3] = uint((row >> 12) & 0xf)

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
	}
}
