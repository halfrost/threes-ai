// Command moveserver exposes the strong Threes agent over HTTP so a browser
// driver (deploy/web) can ask for the next move while scoring on a live site.
//
// POST /move  {"board": [[v..]x4], "next": v, "deck": [ones,twos,threes]}
//   board: 4x4 of printed VALUES (0,1,2,3,6,12,...). next: the previewed tile
//   VALUE, or <=0 for a bonus "+" (unknown value → the search averages the range).
//   deck (optional): remaining bag counts for deck-aware play; omit to fall back
//   to the board approximation.
// -> {"move": 0..3}   (0=UP,1=DOWN,2=LEFT,3=RIGHT), or -1 if no legal move.
//
// Usage: go run ./cmd/moveserver -addr :9010 -depthcap 5 -deckaware
package main

import (
	"encoding/json"
	"flag"
	"log"
	"net/http"

	"github.com/halfrost/threes-ai/ai"
	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

type moveReq struct {
	Board   [][]int `json:"board"`   // printed values
	Next    int     `json:"next"`    // value, or <=0 for a bonus "+"
	NextSet []int   `json:"nextset"` // optional exact candidate next values (OCR/deck); overrides Next
	Deck    []int   `json:"deck"`    // optional [ones,twos,threes] remaining
}

func toIndexBoard(vals [][]int) [][]int {
	b := make([][]int, 4)
	for i := 0; i < 4; i++ {
		b[i] = make([]int, 4)
		for j := 0; j < 4 && j < len(vals[i]); j++ {
			b[i][j] = utils.ReValueMap[vals[i][j]]
		}
	}
	return b
}

func maxIndex(b [][]int) int {
	m := 0
	for _, row := range b {
		for _, v := range row {
			if v > m {
				m = v
			}
		}
	}
	return m
}

func main() {
	addr := flag.String("addr", ":9010", "listen address")
	depthCap := flag.Int("depthcap", 5, "search depth cap")
	deckAware := flag.Bool("deckaware", true, "use the supplied deck counts when present")
	flag.Parse()

	ai.MaxDepthCap = *depthCap
	utils.InitGameScoreTable()

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("moveserver ok\n")) })
	http.HandleFunc("/move", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*") // allow the browser driver to call
		var req moveReq
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil || len(req.Board) != 4 {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		board := toIndexBoard(req.Board)

		candidate := gameboard.FindCandidates(board)
		if *deckAware && len(req.Deck) == 3 {
			candidate = req.Deck
		}

		var nextBrick []int
		if len(req.NextSet) > 0 { // exact candidate set (OCR next-preview or deck): use verbatim
			for _, v := range req.NextSet {
				nextBrick = append(nextBrick, utils.ReValueMap[v])
			}
		} else if req.Next >= 1 { // known tile value; index == value for 1/2/3
			nextBrick = []int{utils.ReValueMap[req.Next]}
		} else { // bonus "+": average over the possible bonus indices {6..maxTile/8}
			hi := maxIndex(board) - 3
			for idx := 4; idx <= hi; idx++ {
				nextBrick = append(nextBrick, idx)
			}
			if len(nextBrick) == 0 {
				nextBrick = []int{1}
			}
		}

		move := ai.ExpectSearchBB(engine.PackBoard(board), candidate, nextBrick)
		json.NewEncoder(w).Encode(map[string]int{"move": move})
	})

	log.Printf("moveserver on %s (depthcap=%d deckaware=%v)", *addr, *depthCap, *deckAware)
	log.Fatal(http.ListenAndServe(*addr, nil))
}
