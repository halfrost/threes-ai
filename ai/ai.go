package ai

import (
	"fmt"

	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

// GameState define
type GameState struct {
	MaxElement  int
	CurrentDept int
	DeptMax     int
	MoveCount   int
	CacheScore  map[uint64]float64
	CacheHint   int
}

const (
	debug = false
)

// ExpectSearch find MaxScoreMove
func ExpectSearch(board [][]int, candidate []int, nextBrick []int) int {

	if debug {
		fmt.Printf("【AI.Search】board = %v |candidate = %v | nextBrick = %v |\n", board, candidate, nextBrick)
	}
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
	bestMove = -1
	for key, value := range moveScoreMap {
		if value > bestScore {
			bestScore = value
			bestMove = key
		}
	}
	if debug {
		fmt.Printf("最佳的 move = %v ,score = %f\n\n\n\n\n", bestMove, bestScore)
	}
	return bestMove
}

// deptSearch : ordering variance to search
func deptSearch(board [][]int, candidate []int, nextBrick []int, move int) float64 {
	if debug {
		fmt.Printf("【AI.deptSearch】board = %v |candidate = %v | nextBrick = %v | move = %v\n", board, candidate, nextBrick, move)
	}
	maxEle, _, _ := gameboard.MaxElement(board)

	cs := make(map[uint64]float64, 0)
	gameStateMaster := GameState{MaxElement: 0, CurrentDept: 0, DeptMax: 8, MoveCount: 0, CacheScore: cs, CacheHint: 0}
	gameStateMaster.DeptMax = deptLevel(board)
	gameStateMaster.MaxElement = maxEle
	gameStateMaster.MoveCount = 0

	newboard, changes, changeNum := gameboard.MakeMove(board, move)

	if debug {
		fmt.Printf("变更以后board = %v |candidate = %v | nextBrick = %v | move = %v | changes = %v | changeNum = %v\n", newboard, candidate, nextBrick, move, changes, changeNum)
	}

	if changeNum == 0 {
		return 0
	}
	var result float64
	result = 0
	chance := 0
	for _, brick := range nextBrick {
		switch brick {
		case 1:
			{
				c := make([]int, 3)
				for i := 0; i < 3; i++ {
					if i == 0 {
						c[i] = candidate[0] - 1
					} else {
						c[i] = candidate[i]
					}
				}
				result += heurSearch(&gameStateMaster, newboard, c, brick, move, changes, changeNum, 1.0)
				if debug {
					fmt.Printf("brick = 1, result = %f, move = %d\n", result, move)
				}
			}
			break
		case 2:
			{
				c := make([]int, 3)
				for i := 0; i < 3; i++ {
					if i == 1 {
						c[i] = candidate[1] - 1
					} else {
						c[i] = candidate[i]
					}
				}
				result += heurSearch(&gameStateMaster, newboard, c, brick, move, changes, changeNum, 1.0)
				if debug {
					fmt.Printf("brick = 2, result = %f, move = %d\n", result, move)
				}
			}
			break
		case 3:
			{
				c := make([]int, 3)
				for i := 0; i < 3; i++ {
					if i == 2 {
						c[i] = candidate[2] - 1
					} else {
						c[i] = candidate[i]
					}
				}
				result += heurSearch(&gameStateMaster, newboard, c, brick, move, changes, changeNum, 1.0)
				if debug {
					fmt.Printf("brick = 3, result = %f, move = %d\n", result, move)
				}
			}
			break
		default:
			{
				result += heurSearch(&gameStateMaster, newboard, candidate, brick, move, changes, changeNum, 1.0)
				if debug {
					fmt.Printf("brick = else, result = %f, move = %d\n", result, move)
				}
			}
			break
		}
		chance++
	}

	if debug {
		fmt.Printf("本地 move 移动了 move = %d , movecount = %d deptMax = %d , currentDept = %d cachehint = %d cachesize = %d\n", move, gameStateMaster.MoveCount, gameStateMaster.DeptMax, gameStateMaster.CurrentDept, gameStateMaster.CacheHint, len(gameStateMaster.CacheScore))
	}
	return result/float64(chance) + 1e-6
}

// heurSearch : Heuristic search 启发式搜索
func heurSearch(gameStateMaster *GameState, board [][]int, candidate []int, nextBrick int, move int, changes []int, changeNum int, prob float64) float64 {
	var res float64
	res = 0
	factor := 1.0 / float64(changeNum)
	cprob := prob * factor

	for changeIndex := 0; changeIndex < 4; changeIndex++ {
		if changes[changeIndex] == 1 {
			newboard := gameboard.InsertBrick(board, nextBrick, move, changeIndex)
			res += insertHeurSearch(gameStateMaster, newboard, candidate, cprob)
		}
	}
	return res * factor
}

// insertHeurSearch : Heuristic search 插入候选可能的砖块，再进行启发式搜索
func insertHeurSearch(gameStateMaster *GameState, board [][]int, candidate []int, prob float64) float64 {

	if prob < utils.CprobMin || gameStateMaster.CurrentDept >= gameStateMaster.DeptMax {
		return utils.GetHeurWeightScore(board)
	}

	var stream uint64
	stream = 0
	for i := len(board) - 1; i >= 0; i-- {
		for j := len(board[i]) - 1; j >= 0; j-- {
			stream += uint64(utils.ReValueMap[board[i][j]] << uint((uint(i)*gameboard.BOARDWIDTH+uint(j))*4))
		}
	}

	var best float64
	best = 0
	gameStateMaster.CurrentDept++

	for move := 0; move < 4; move++ {
		newboard, changes, changeNum := gameboard.MakeMove(board, move)
		gameStateMaster.MoveCount++
		if changeNum != 0 {
			sc := recursionDeptSearch(gameStateMaster, newboard, candidate, move, changes, changeNum, prob)
			if sc > best {
				best = sc
			}
		}
	}
	gameStateMaster.CurrentDept--
	gameStateMaster.CacheScore[stream] = best

	return best
}

func recursionDeptSearch(gameStateMaster *GameState, board [][]int, candidate []int, move int, changes []int, changeNum int, prob float64) float64 {

	var res float64
	res = 0
	maxEle, _, _ := gameboard.MaxElement(board)
	gameStateMaster.MaxElement = maxEle

	if candidate[0] == 0 && candidate[1] == 0 && candidate[2] == 0 {
		candidate[0] = 4
		candidate[1] = 4
		candidate[2] = 4
	}

	oneNum := candidate[0]
	twoNum := candidate[1]
	threeNum := candidate[2]

	var total float64
	total = float64(oneNum + twoNum + threeNum)
	var hres float64
	hres = 0

	if maxEle >= 7 {
		chance := maxEle - 6
		for i := 0; i < chance; i++ {
			hres += heurSearch(gameStateMaster, board, candidate, i+4, move, changes, changeNum, prob/float64(chance)/float64(utils.HightBrickFreq))
		}
		hres /= float64(chance * utils.HightBrickFreq)
		total *= float64(utils.HightBrickFreq) / (utils.HightBrickFreq - 1)
	}

	if oneNum != 0 {
		c := make([]int, 3)
		for i := 0; i < 3; i++ {
			if i == 0 {
				c[i] = candidate[0] - 1
			} else {
				c[i] = candidate[i]
			}
		}
		res += heurSearch(gameStateMaster, board, c, 1, move, changes, changeNum, prob/total*float64(oneNum)) * float64(oneNum)
	}

	if twoNum != 0 {
		c := make([]int, 3)
		for i := 0; i < 3; i++ {
			if i == 1 {
				c[i] = candidate[1] - 1
			} else {
				c[i] = candidate[i]
			}
		}
		res += heurSearch(gameStateMaster, board, c, 2, move, changes, changeNum, prob/total*float64(twoNum)) * float64(twoNum)
	}

	if threeNum != 0 {
		c := make([]int, 3)
		for i := 0; i < 3; i++ {
			if i == 2 {
				c[i] = candidate[2] - 1
			} else {
				c[i] = candidate[i]
			}
		}
		res += heurSearch(gameStateMaster, board, c, 3, move, changes, changeNum, prob/total*float64(threeNum)) * float64(threeNum)
	}

	res /= total
	res += hres

	return res
}

func deptLevel(board [][]int) int {
	dept := utils.Max(3, gameboard.FindDiffCount(board)-2)
	if debug {
		fmt.Printf("初始的dept = %v\n", dept)
	}
	maxE, maxIndexi, maxIndexj := gameboard.MaxElement(board)
	qua := gameboard.CalculateVariance(board, maxIndexi, maxIndexj)
	if debug {
		fmt.Printf("qua = %d", qua)
	}
	if maxE-qua <= 4 && maxE >= 9 {
		dept += 2
	}
	if debug {
		fmt.Printf("更新以后的的dept = %v\n", dept)
	}
	return dept
}
