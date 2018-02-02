package utils

import (
	"fmt"
	"math"
)

const (
	// BOARDWIDTH 棋盘宽度
	BOARDWIDTH = 4
	// BOARDHEIGHT 棋盘宽度
	BOARDHEIGHT = 4
)

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
	board := make([][]int, BOARDHEIGHT)
	for i := range board {
		subArray := make([]int, BOARDWIDTH)
		for j := range subArray {
			subArray[j] = int((stream << (64 - (uint(i)*BOARDWIDTH+uint(j)+1)*4)) >> 60)
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
