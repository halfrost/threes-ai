// Package engine is a faithful, headless Threes! environment (the "world"),
// kept strictly separate from any AI agent. It reuses the battle-tested move
// logic in package gameboard and adds the environment side: the tile bag,
// bonus tiles, the next-tile preview, spawn placement, scoring and game-over.
//
// Board representation: 4x4 of tile INDICES (not printed values):
//
//	index: 0  1  2  3  4  5  6  7   8   9   10  11   12   13   14   15
//	value: .  1  2  3  6 12 24 48  96 192 384 768 1536 3072 6144 12288
//
// Threes tile-generation rules encoded here (verified against public analyses):
//   - Base tiles are drawn from a shuffled bag of 12 cards: four 1s, four 2s,
//     four 3s. The bag is refilled when empty. Drawing depletes it, so the set
//     of upcoming base tiles is partially known — the basis for deck-aware play.
//   - Bonus tiles: once the max tile value on the board is >= 48 (index >= 7),
//     the incoming tile is a bonus with probability 1/21 (does NOT consume the
//     bag). Its value is uniform over {6, 12, ..., maxValue/8}, i.e. indices
//     4 .. maxIndex-3.
//   - The next incoming tile is previewed one step ahead.
package engine

import (
	"math/rand"

	"github.com/halfrost/threes-ai/gameboard"
)

// ValueTable maps a tile index (0..15) to its printed value.
var ValueTable = [16]int{0, 1, 2, 3, 6, 12, 24, 48, 96, 192, 384, 768, 1536, 3072, 6144, 12288}

// bonusFreq is the "1 in N" chance of a bonus tile when eligible (max >= 48).
const bonusFreq = 21

// initialTiles is how many tiles Threes places on the board at game start.
const initialTiles = 9

// Game is a faithful Threes environment. It is deterministic given its seed.
type Game struct {
	Board     [][]int    // 4x4 tile indices
	Next      int        // next incoming tile INDEX (previewed)
	NextBonus bool       // whether Next was generated as a bonus tile
	Moves     int        // moves applied so far
	bag       []int      // remaining bag cards (values 1/2/3)
	rng       *rand.Rand // per-game RNG for reproducibility
}

func newBoard() [][]int {
	b := make([][]int, 4)
	for i := range b {
		b[i] = make([]int, 4)
	}
	return b
}

// NewGame returns a fresh game seeded deterministically.
func NewGame(seed int64) *Game {
	g := &Game{rng: rand.New(rand.NewSource(seed)), Board: newBoard()}
	g.refillBag()
	g.placeInitial(initialTiles)
	g.Next, g.NextBonus = g.genTile()
	return g
}

func (g *Game) refillBag() {
	g.bag = g.bag[:0]
	for v := 1; v <= 3; v++ {
		for k := 0; k < 4; k++ {
			g.bag = append(g.bag, v)
		}
	}
}

// drawBag pops a uniformly random remaining card (== drawing from a shuffled bag).
func (g *Game) drawBag() int {
	if len(g.bag) == 0 {
		g.refillBag()
	}
	j := g.rng.Intn(len(g.bag))
	v := g.bag[j]
	g.bag = append(g.bag[:j], g.bag[j+1:]...)
	return v
}

func (g *Game) maxIndex() int {
	m := 0
	for i := 0; i < 4; i++ {
		for j := 0; j < 4; j++ {
			if g.Board[i][j] > m {
				m = g.Board[i][j]
			}
		}
	}
	return m
}

// genTile produces the next incoming tile INDEX per Threes rules.
func (g *Game) genTile() (int, bool) {
	maxIdx := g.maxIndex()
	if maxIdx >= 7 && g.rng.Intn(bonusFreq) == 0 {
		lo, hi := 4, maxIdx-3 // value 6 .. maxValue/8
		return lo + g.rng.Intn(hi-lo+1), true
	}
	return g.drawBag(), false
}

func (g *Game) placeInitial(n int) {
	pos := g.rng.Perm(16)
	for k := 0; k < n && k < 16; k++ {
		p := pos[k]
		g.Board[p/4][p%4] = g.drawBag()
	}
}

// Step applies a move (0=UP, 1=DOWN, 2=LEFT, 3=RIGHT). It returns false and
// leaves the board unchanged if the move is illegal (nothing slides/merges).
func (g *Game) Step(move int) bool {
	newBoard, change, changeNum := gameboard.MakeMove(g.Board, move)
	if changeNum == 0 {
		return false
	}
	lanes := make([]int, 0, 4)
	for i := 0; i < 4; i++ {
		if change[i] == 1 {
			lanes = append(lanes, i)
		}
	}
	lane := lanes[g.rng.Intn(len(lanes))]
	g.Board = gameboard.InsertBrick(newBoard, g.Next, move, lane)
	g.Moves++
	g.Next, g.NextBonus = g.genTile()
	return true
}

// Over reports whether no move can change the board (game over).
func (g *Game) Over() bool {
	for m := 0; m < 4; m++ {
		if _, _, n := gameboard.MakeMove(g.Board, m); n != 0 {
			return false
		}
	}
	return true
}

// Score is the Threes score: sum of 3^(index-2) over tiles with index >= 3.
func (g *Game) Score() int {
	sum := 0
	for i := 0; i < 4; i++ {
		for j := 0; j < 4; j++ {
			if v := g.Board[i][j]; v >= 3 {
				p := 1
				for k := 0; k < v-2; k++ {
					p *= 3
				}
				sum += p
			}
		}
	}
	return sum
}

// MaxTile returns the highest printed tile value on the board.
func (g *Game) MaxTile() int { return ValueTable[g.maxIndex()] }

// NextHint returns what the AI should be told about the incoming tile — matching
// what a real player sees. For a base tile it is the exact value [Next]. For a
// bonus tile the real game only shows a white "+", so the AI is given the full
// set of possible bonus indices {6, ..., maxTile/8} to average over, instead of
// the exact value it must not know.
func (g *Game) NextHint() []int {
	if !g.NextBonus {
		return []int{g.Next}
	}
	hi := g.maxIndex() - 3 // value maxTile/8
	if hi < 4 {
		return []int{g.Next}
	}
	hint := make([]int, 0, hi-3)
	for idx := 4; idx <= hi; idx++ {
		hint = append(hint, idx)
	}
	return hint
}

// DeckCounts returns the ground-truth remaining bag as [ones, twos, threes],
// counted as of *before* the current preview tile was drawn. This is the exact
// "deck-aware" signal to feed the search as its candidate: the search decrements
// the preview tile itself, so it expects the pre-preview distribution. Contrast
// with gameboard.FindCandidates, which only approximates the deck from the board.
func (g *Game) DeckCounts() []int {
	c := []int{0, 0, 0}
	for _, v := range g.bag {
		if v >= 1 && v <= 3 {
			c[v-1]++
		}
	}
	if !g.NextBonus && g.Next >= 1 && g.Next <= 3 {
		c[g.Next-1]++ // add the preview back: the search will decrement it
	}
	return c
}
