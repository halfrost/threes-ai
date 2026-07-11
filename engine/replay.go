package engine

import "github.com/halfrost/threes-ai/gameboard"

// Step is one recorded ply: the board BEFORE the move (tile indices), the
// previewed next tile, the move applied (0=UP,1=DOWN,2=LEFT,3=RIGHT; -1 marks
// the terminal board), and the running score.
type Step struct {
	Board [][]int `json:"board"`
	Next  int     `json:"next"`
	Move  int     `json:"move"`
	Score int     `json:"score"`
}

// Replay is a full recorded game, sufficient for a frontend to step through it.
// Board cells are tile INDICES; use ValueTable to render printed values.
type Replay struct {
	Seed       int64   `json:"seed"`
	Agent      string  `json:"agent"`
	DepthCap   int     `json:"depth_cap"`
	FinalScore int     `json:"final_score"`
	MaxTile    int     `json:"max_tile"`
	Moves      int     `json:"moves"`
	ValueTable [16]int `json:"value_table"`
	Steps      []Step  `json:"steps"`
}

// Play runs a full game to completion (or maxMoves). choose returns the move for
// the current state; a return < 0 means "no legal move" (game over). When
// rec != nil, every ply (board before the move) and the terminal board are
// appended to rec, and rec's summary fields are filled in at the end.
func Play(g *Game, choose func(*Game) int, rec *Replay, maxMoves int) {
	for g.Moves < maxMoves {
		move := choose(g)
		if move < 0 {
			break
		}
		if rec != nil {
			rec.Steps = append(rec.Steps, Step{
				Board: gameboard.Clone(g.Board),
				Next:  g.Next,
				Move:  move,
				Score: g.Score(),
			})
		}
		if !g.Step(move) {
			// Illegal move returned (should not happen with a correct agent);
			// drop the speculative record to keep the replay faithful.
			if rec != nil && len(rec.Steps) > 0 {
				rec.Steps = rec.Steps[:len(rec.Steps)-1]
			}
			break
		}
	}
	if rec != nil {
		rec.Steps = append(rec.Steps, Step{
			Board: gameboard.Clone(g.Board),
			Next:  -1,
			Move:  -1,
			Score: g.Score(),
		})
		rec.FinalScore = g.Score()
		rec.MaxTile = g.MaxTile()
		rec.Moves = g.Moves
		rec.ValueTable = ValueTable
	}
}
