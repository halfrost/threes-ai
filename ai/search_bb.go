package ai

// Bitboard expectimax: a faithful, faster port of ExpectSearch that operates on
// packed uint64 boards. It mirrors the [][]int search function-for-function so
// it returns the same move decisions, but replaces slice-cloning moves with
// bitboard table lookups and drops the original write-only cache map (which was
// never read, so removing it changes no result). Verified against ExpectSearch
// in search_bb_test.go.

import (
	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/utils"
)

// ParallelRoot controls whether ExpectSearchBB evaluates the 4 root moves in
// parallel goroutines. Keep it true for low single-game latency. Set it false
// for batch self-play on many cores, where running each game's search
// sequentially and parallelising across games avoids 4x goroutine
// oversubscription and gives higher total throughput.
var ParallelRoot = true

// ExpectSearchBB returns the best move (0=UP,1=DOWN,2=LEFT,3=RIGHT) for a packed
// board, or -1 if no move is legal. candidate/nextBrick match ExpectSearch. The
// result is identical whether or not ParallelRoot is set.
func ExpectSearchBB(board uint64, candidate []int, nextBrick []int) int {
	var moveScore [4]float64
	if ParallelRoot {
		var scores [4]chan float64
		for move := 0; move < 4; move++ {
			scores[move] = make(chan float64, 1)
			go func(m int) { scores[m] <- deptSearchBB(board, candidate, nextBrick, m) }(move)
		}
		for m := 0; m < 4; m++ {
			moveScore[m] = <-scores[m]
		}
	} else {
		for m := 0; m < 4; m++ {
			moveScore[m] = deptSearchBB(board, candidate, nextBrick, m)
		}
	}
	var bestScore float64
	bestMove := -1
	for m := 0; m < 4; m++ {
		if moveScore[m] > bestScore {
			bestScore, bestMove = moveScore[m], m
		}
	}
	return bestMove
}

func deptSearchBB(board uint64, candidate []int, nextBrick []int, move int) float64 {
	gsm := GameState{
		DeptMax:    deptLevel(engine.UnpackBoard(board)),
		MaxElement: engine.MaxIndexBB(board),
	}
	nb, changed, any := engine.MoveBitboard(board, move)
	if !any {
		return 0
	}
	changes, changeNum := engine.CountChanged(changed)

	var result float64
	chance := 0
	for _, brick := range nextBrick {
		c := adjustTopCandidate(candidate, brick)
		result += heurSearchBB(&gsm, nb, c, brick, move, changes, changeNum, 1.0)
		chance++
	}
	return result/float64(chance) + 1e-6
}

// adjustTopCandidate mirrors deptSearch's per-brick candidate adjustment: a base
// tile decrements its count (fresh slice); any other value (bonus) reuses the
// same slice, exactly as the original default branch did.
func adjustTopCandidate(candidate []int, brick int) []int {
	switch brick {
	case 1:
		return []int{candidate[0] - 1, candidate[1], candidate[2]}
	case 2:
		return []int{candidate[0], candidate[1] - 1, candidate[2]}
	case 3:
		return []int{candidate[0], candidate[1], candidate[2] - 1}
	default:
		return candidate
	}
}

func heurSearchBB(gsm *GameState, board uint64, candidate []int, nextBrick, move int, changes [4]int, changeNum int, prob float64) float64 {
	var res float64
	factor := 1.0 / float64(changeNum)
	cprob := prob * factor
	for ci := 0; ci < 4; ci++ {
		if changes[ci] == 1 {
			nb := engine.InsertBrickBB(board, nextBrick, move, ci)
			res += insertHeurSearchBB(gsm, nb, candidate, cprob)
		}
	}
	return res * factor
}

// LeafEval, when set, replaces the hand-tuned heuristic at the search leaves —
// e.g. with a learned N-tuple value function. nil (the default) preserves the
// original behaviour exactly, so existing runs are unaffected.
var LeafEval func(uint64) float64

func insertHeurSearchBB(gsm *GameState, board uint64, candidate []int, prob float64) float64 {
	if prob < utils.CprobMin || gsm.CurrentDept >= gsm.DeptMax {
		if LeafEval != nil {
			return LeafEval(board)
		}
		return utils.HeurScoreBitboard(board)
	}
	var best float64
	gsm.CurrentDept++
	for move := 0; move < 4; move++ {
		nb, changed, any := engine.MoveBitboard(board, move)
		gsm.MoveCount++
		if any {
			changes, changeNum := engine.CountChanged(changed)
			if sc := recursionDeptSearchBB(gsm, nb, candidate, move, changes, changeNum, prob); sc > best {
				best = sc
			}
		}
	}
	gsm.CurrentDept--
	return best
}

func recursionDeptSearchBB(gsm *GameState, board uint64, candidate []int, move int, changes [4]int, changeNum int, prob float64) float64 {
	var res float64
	maxEle := engine.MaxIndexBB(board)
	gsm.MaxElement = maxEle

	if candidate[0] == 0 && candidate[1] == 0 && candidate[2] == 0 {
		candidate[0], candidate[1], candidate[2] = 4, 4, 4 // in-place, mirrors original aliasing
	}
	oneNum, twoNum, threeNum := candidate[0], candidate[1], candidate[2]
	total := float64(oneNum + twoNum + threeNum)

	var hres float64
	if maxEle >= 7 {
		chance := maxEle - 6
		for i := 0; i < chance; i++ {
			hres += heurSearchBB(gsm, board, candidate, i+4, move, changes, changeNum, prob/float64(chance)/float64(utils.HightBrickFreq))
		}
		hres /= float64(chance * utils.HightBrickFreq)
		total *= float64(utils.HightBrickFreq) / (utils.HightBrickFreq - 1)
	}

	if oneNum != 0 {
		c := []int{candidate[0] - 1, candidate[1], candidate[2]}
		res += heurSearchBB(gsm, board, c, 1, move, changes, changeNum, prob/total*float64(oneNum)) * float64(oneNum)
	}
	if twoNum != 0 {
		c := []int{candidate[0], candidate[1] - 1, candidate[2]}
		res += heurSearchBB(gsm, board, c, 2, move, changes, changeNum, prob/total*float64(twoNum)) * float64(twoNum)
	}
	if threeNum != 0 {
		c := []int{candidate[0], candidate[1], candidate[2] - 1}
		res += heurSearchBB(gsm, board, c, 3, move, changes, changeNum, prob/total*float64(threeNum)) * float64(threeNum)
	}
	res /= total
	res += hres
	return res
}
