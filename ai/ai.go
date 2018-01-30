package ai

import (
	"fmt"

	"github.com/halfrost/threes-ai/utils"
)

import "C"

// GameState define
// type GameState struct {
// 	GameBoard map[type]type
// }

// InitGameState 初始化游戏状态
func InitGameState() {
	// 设置权重
	//2.5603675951186942, 48.075499534692185, 0.70005740882109824, 127.87624414823753, 253.7959629528122, 945.27171328243628, 674.42839422651991
}

// Search find MaxScoreMove
func Search(board [][]int, candidate []int, nextBrick []int, move int) float64 {

	var res float64
	fmt.Printf("【AI.Search】board = %v |candidate = %v | nextBrick = %v |move = %v |\n", board, candidate, nextBrick, move)
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

// ExpectSearch : Expectimax Search 最大期望搜索
func ExpectSearch(board uint64, deck uint32, tileset uint16, move int) float32 {
	cand, _ := utils.GetCandidates(deck)
	fmt.Printf("【AI.ExpectSearch】board = %v | deck = %v | tileset = %v |move = %v |\n", utils.GetBoard(board), cand, utils.GetNextBrick(tileset), move)
	return 0
}

// HeurSearch : Heuristic search 启发式搜索
func HeurSearch(f *float32, flen int) {
	fmt.Printf("【AI.HeurSearch】f = %v | flen = %v\n", f, flen)
}

// deptSearch : 深搜
func deptSearch() {

}
