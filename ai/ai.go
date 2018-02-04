package ai

import (
	"fmt"

	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

import "C"

// GameState define
type GameState struct {
	Dept       int
	MaxElement int
}

var gameStateMaster GameState

// InitGameState ...
func InitGameState() {
	gameStateMaster = GameState{Dept: 5, MaxElement: 0}
}

// ExpectSearch find MaxScoreMove
func ExpectSearch(board [][]int, candidate []int, nextBrick []int) int {

	fmt.Printf("【AI.Search】board = %v |candidate = %v | nextBrick = %v |\n", board, candidate, nextBrick)
	gameStateMaster.Dept = deptLevel(board)
	moveScoreMap := make(map[int]float64, 0)

	ExpectScoreSearch := func(scoreChan chan float64, board [][]int, candidate []int, nextBrick []int, move int) {
		scoreChan <- deptSearch(board, candidate, nextBrick, move)
	}

	scores := make([]chan float64, 4)
	for move := 0; move < 4; move++ {
		scores[move] = make(chan float64, 1)
		go ExpectScoreSearch(scores[move], board, candidate, nextBrick, move)
	}

	var sc float64
	for i := 0; i < 4; i++ {
		select {
		case sc = <-scores[i]:
			{
				moveScoreMap[i] = sc
			}
		}
	}

	var bestScore float64
	var bestMove int
	for key, value := range moveScoreMap {
		if value > bestScore {
			bestScore = value
			bestMove = key
		}
	}
	return bestMove
}

// heurSearch : Heuristic search 启发式搜索
func heurSearch(board [][]int, candidate []int, nextBrick int, move int, changes []int, changeNum int, prob float64) float64 {
	fmt.Printf("【AI.HeurSearch】\n")
	return 0.0
}

// deptSearch : ordering variance to search
func deptSearch(board [][]int, candidate []int, nextBrick []int, move int) float64 {

	maxEle, _, _ := gameboard.MaxElement(board)
	gameStateMaster.MaxElement = maxEle
	newboard, changes, changeNum := gameboard.MakeMove(board, move)

	if changeNum == 0 {
		return 0
	}
	var result float64
	chance := 0
	for _, brick := range nextBrick {
		switch brick {
		case 1:
			{
				candidate[0] = candidate[0] - 1
				result += heurSearch(newboard, candidate, brick, move, changes, changeNum, 1.0)
				chance++
			}
			break
		case 2:
			{
				candidate[1] = candidate[1] - 1
				result += heurSearch(newboard, candidate, brick, move, changes, changeNum, 1.0)
				chance++
			}
			break
		case 3:
			{
				candidate[2] = candidate[2] - 1
				result += heurSearch(newboard, candidate, brick, move, changes, changeNum, 1.0)
				chance++
			}
			break
		default:
			{
				result += heurSearch(newboard, candidate, brick, move, changes, changeNum, 1.0)
				chance++
			}
			break
		}
	}

	return result/float64(chance) + 1e-6
}

func deptLevel(board [][]int) int {
	dept := utils.Max(5, gameboard.FindDiffCount(board))
	_, maxIndexi, maxIndexj := gameboard.MaxElement(board)
	qua := gameboard.CalculateVariance(board, maxIndexi, maxIndexj)
	dept += qua
	return dept
}
