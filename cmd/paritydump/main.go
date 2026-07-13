// Command paritydump plays random-legal-move games with the Go engine and dumps
// each one as a replayable event stream, so rl/parity_check.py can prove the
// Python environment (rl/threes_env.py) reproduces the Go rules exactly.
//
// Per step we emit the move plus the SPAWN that actually happened (its index and
// cell) and the resulting board+score. The Python side re-applies the same move
// with its own slide/merge, force-places the recorded spawn, and asserts the
// board and score match — validating slide/merge/placement/scoring independent
// of each language's RNG (the spawn is replayed, not re-sampled).
//
// Move convention matches gameboard.MakeMove and rl/threes_env: 0=UP 1=DOWN
// 2=LEFT 3=RIGHT. Board is 4x4 tile INDICES, row-major when flattened to 16.
//
// Usage: go run ./cmd/paritydump -seed 1 -games 200 > parity.jsonl
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"math/rand"
	"os"

	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
)

type step struct {
	Move  int   `json:"move"`
	Spawn [3]int `json:"spawn"` // [index, row, col]
	Board []int `json:"board"` // 16 indices, row-major, AFTER move+spawn
	Score int   `json:"score"`
}

type gameDump struct {
	Seed       int64  `json:"seed"`
	Init       []int  `json:"init"` // 16 indices before any move
	Steps      []step `json:"steps"`
	FinalScore int    `json:"final_score"`
	FinalMax   int    `json:"final_max"`
	Moves      int    `json:"moves"`
}

func flat(b [][]int) []int {
	out := make([]int, 16)
	for i := 0; i < 4; i++ {
		for j := 0; j < 4; j++ {
			out[i*4+j] = b[i][j]
		}
	}
	return out
}

func legalMoves(b [][]int) []int {
	var ms []int
	for m := 0; m < 4; m++ {
		if _, _, n := gameboard.MakeMove(b, m); n != 0 {
			ms = append(ms, m)
		}
	}
	return ms
}

// spawnCell returns the single cell where post differs from the pre-spawn board.
func spawnCell(preSpawn, post [][]int) (idx, r, c int) {
	for i := 0; i < 4; i++ {
		for j := 0; j < 4; j++ {
			if preSpawn[i][j] != post[i][j] {
				return post[i][j], i, j
			}
		}
	}
	return -1, -1, -1
}

func main() {
	seed := flag.Int64("seed", 1, "base seed (game i uses seed+i)")
	games := flag.Int("games", 200, "number of games to dump")
	maxMoves := flag.Int("maxmoves", 20000, "safety cap on moves per game")
	flag.Parse()

	w := bufio.NewWriter(os.Stdout)
	defer w.Flush()
	enc := json.NewEncoder(w)

	for gi := 0; gi < *games; gi++ {
		s := *seed + int64(gi)
		g := engine.NewGame(s)
		// A separate RNG picks the moves — the trajectory just needs to be some
		// legal sequence; Python replays these exact moves, so the policy is
		// irrelevant to parity. Random legal moves exercise all 4 directions.
		pick := rand.New(rand.NewSource(s ^ 0x5deece66d))
		d := gameDump{Seed: s, Init: flat(g.Board)}
		for !g.Over() && g.Moves < *maxMoves {
			ms := legalMoves(g.Board)
			if len(ms) == 0 {
				break
			}
			move := ms[pick.Intn(len(ms))]
			preSpawn, _, _ := gameboard.MakeMove(g.Board, move) // pre-spawn board
			nextVal := g.Next
			g.Step(move)
			idx, r, c := spawnCell(preSpawn, g.Board)
			// sanity: the spawned index must equal the previewed Next
			if idx != nextVal {
				// mismatch would indicate a diff-detection bug; record it as -1
				// so the Python side flags it loudly rather than silently pass.
				idx = -idx
			}
			d.Steps = append(d.Steps, step{
				Move: move, Spawn: [3]int{idx, r, c},
				Board: flat(g.Board), Score: g.Score(),
			})
		}
		d.FinalScore = g.Score()
		d.FinalMax = g.MaxTile()
		d.Moves = g.Moves
		if err := enc.Encode(&d); err != nil {
			panic(err)
		}
	}
}
