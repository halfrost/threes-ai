package ai

import (
	"fmt"

	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

import "C"

// GameState define
type GameState struct {
	Dept int
}

var gameStateMaster GameState

// InitGameState ...
func InitGameState() {
	gameStateMaster = GameState{Dept: 5}
}

// ExpectSearch find MaxScoreMove
func ExpectSearch(board [][]int, candidate []int, nextBrick []int) int {

	//var res float64
	fmt.Printf("【AI.Search】board = %v |candidate = %v | nextBrick = %v |\n", board, candidate, nextBrick)
	gameStateMaster.Dept = deptSearch(board)
	var moveScoreMap map[int]float64
	for move := 0; move < 4; move++ {

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

// HeurSearch : Heuristic search 启发式搜索
func HeurSearch(f *float32, flen int) {
	fmt.Printf("【AI.HeurSearch】f = %v | flen = %v\n", f, flen)
}

// deptSearch : ordering variance to search
func deptSearch(board [][]int) int {
	dept := utils.Max(5, gameboard.FindDiffCount(board))
	_, maxIndexi, maxIndexj := gameboard.MaxElement(board)
	qua := gameboard.CalculateVariance(board, maxIndexi, maxIndexj)
	dept += qua
	return dept
}
