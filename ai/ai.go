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

// ExpectSearch find MaxScoreMove
func ExpectSearch(board [][]int, candidate []int, nextBrick []int) float64 {

	var res float64
	fmt.Printf("【AI.Search】board = %v |candidate = %v | nextBrick = %v |\n", board, candidate, nextBrick)
	// 	eval_state state;
	//
	// 	state.depth_limit = std::max(3, count_distinct_tiles(board) - 2);
	//
	// 	/* Opposite-corners penalty */
	// 	int corner_disparity = 0;
	// 	int maxrank = get_max_rank(board);
	// 	for(int q=0; q<4; q++) {
	// 			if(get_row_max_rank(get_quadrant(board, q)) == maxrank) {
	// 					/* Get rank in the opposite corner */
	// 					corner_disparity = maxrank - get_row_max_rank(get_quadrant(board, 3-q));
	// 					break;
	// 			}
	// 	}
	// 	if(corner_disparity <= 4 && maxrank >= 9) {
	// 			state.depth_limit += 2;
	// 	}
	//
	// 	res = _score_toplevel_move(state, board, deck, tileset, move);
	//
	// //     printf("Move %d: result %f: eval'd %ld moves (%d cache hits, %d cache size) in %.2f seconds (maxdepth=%d)\n", move, res,
	// //         state.moves_evaled, state.cachehits, (int)state.trans_table.size(), elapsed, state.maxdepth);

	return res
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
