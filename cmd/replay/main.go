// Command replay plays one self-play game and writes a JSON replay file that the
// standalone viewer (web/replay.html) can step through. Useful for eyeballing
// what the AI actually does, debugging, and producing blog/paper material.
//
// Usage: go run ./cmd/replay -seed 1 -depthcap 3 -out results/replay.json
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/halfrost/threes-ai/ai"
	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

func main() {
	seed := flag.Int64("seed", 1, "seed")
	depthcap := flag.Int("depthcap", 3, "clamp adaptive search depth (0=uncapped)")
	maxmoves := flag.Int("maxmoves", 20000, "safety cap on moves")
	out := flag.String("out", "results/replay.json", "output replay JSON path")
	flag.Parse()

	utils.InitGameScoreTable()
	ai.MaxDepthCap = *depthcap

	g := engine.NewGame(*seed)
	rec := &engine.Replay{Seed: *seed, Agent: "expectimax", DepthCap: *depthcap}
	engine.Play(g, func(gg *engine.Game) int {
		return ai.ExpectSearch(gg.Board, gameboard.FindCandidates(gg.Board), []int{gg.Next})
	}, rec, *maxmoves)

	if dir := filepath.Dir(*out); dir != "" {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
	f, err := os.Create(*out)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer f.Close()
	if err := json.NewEncoder(f).Encode(rec); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("replay: seed=%d score=%d maxtile=%d moves=%d steps=%d -> %s\n",
		*seed, rec.FinalScore, rec.MaxTile, rec.Moves, len(rec.Steps), *out)
}
