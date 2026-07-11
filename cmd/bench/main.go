// Command bench runs the AI over many self-play games in the headless engine
// and reports the score distribution and per-tile reach rates. It is the single
// measurement backbone for the whole project: every agent and every phase is
// evaluated here, so results are apples-to-apples, and the per-game JSONL feeds
// both blog charts and paper tables.
//
// Usage:
//
//	go run ./cmd/bench -n 200 -seed 1 -out results/baseline.jsonl
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/halfrost/threes-ai/ai"
	"github.com/halfrost/threes-ai/engine"
	"github.com/halfrost/threes-ai/gameboard"
	"github.com/halfrost/threes-ai/utils"
)

// milestones are the tiles whose reach-rate we report (indices 9..15).
var milestones = []int{192, 384, 768, 1536, 3072, 6144, 12288}

// GameResult is one line of the JSONL log.
type GameResult struct {
	Seed       int64 `json:"seed"`
	Score      int   `json:"score"`
	MaxTile    int   `json:"max_tile"`
	Moves      int   `json:"moves"`
	DurationMs int64 `json:"duration_ms"`
}

// playGame runs one full game driven by the current AI and returns its result.
func playGame(seed int64, maxMoves int, bb bool) GameResult {
	g := engine.NewGame(seed)
	start := time.Now()
	engine.Play(g, func(gg *engine.Game) int {
		cand := gameboard.FindCandidates(gg.Board)
		if bb {
			return ai.ExpectSearchBB(engine.PackBoard(gg.Board), cand, []int{gg.Next})
		}
		return ai.ExpectSearch(gg.Board, cand, []int{gg.Next})
	}, nil, maxMoves)
	return GameResult{
		Seed:       seed,
		Score:      g.Score(),
		MaxTile:    g.MaxTile(),
		Moves:      g.Moves,
		DurationMs: time.Since(start).Milliseconds(),
	}
}

func main() {
	n := flag.Int("n", 100, "number of games")
	seed := flag.Int64("seed", 1, "base seed (game i uses seed+i)")
	workers := flag.Int("workers", runtime.NumCPU(), "concurrent games")
	maxMoves := flag.Int("maxmoves", 20000, "safety cap on moves per game")
	depthCap := flag.Int("depthcap", 0, "clamp adaptive search depth (0=uncapped)")
	bb := flag.Bool("bb", true, "use the bitboard search (faster; verified identical)")
	out := flag.String("out", "", "optional per-game JSONL output path")
	logPath := flag.String("log", "results/summaries.jsonl", "append a one-line JSON run summary here (blank to disable)")
	label := flag.String("label", "", "optional label for this run in the summary log")
	flag.Parse()

	ai.MaxDepthCap = *depthCap
	utils.InitGameScoreTable()

	fmt.Printf("Running %d games, %d workers, base seed %d...\n", *n, *workers, *seed)
	results := make([]GameResult, *n)
	var wg sync.WaitGroup
	sem := make(chan struct{}, *workers)
	var done int64
	wallStart := time.Now()
	for i := 0; i < *n; i++ {
		wg.Add(1)
		sem <- struct{}{}
		go func(idx int) {
			defer wg.Done()
			defer func() { <-sem }()
			results[idx] = playGame(*seed+int64(idx), *maxMoves, *bb)
			if d := atomic.AddInt64(&done, 1); d%10 == 0 || int(d) == *n {
				fmt.Printf("  %d/%d done (%.0fs elapsed)\n", d, *n, time.Since(wallStart).Seconds())
			}
		}(i)
	}
	wg.Wait()
	wall := time.Since(wallStart)
	report(results, wall)

	engineName := "slice"
	if *bb {
		engineName = "bitboard"
	}
	if *logPath != "" {
		s := summarize(results, wall, *label, engineName, *depthCap, *seed)
		if err := appendSummary(*logPath, s); err != nil {
			fmt.Fprintf(os.Stderr, "append summary: %v\n", err)
		} else {
			fmt.Printf("Run summary appended to %s\n", *logPath)
		}
	}

	if *out != "" {
		if err := writeJSONL(*out, results); err != nil {
			fmt.Fprintf(os.Stderr, "write jsonl: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("Per-game JSONL written to %s\n", *out)
	}
}

// Summary is the one-line-per-run record appended to the experiment log.
type Summary struct {
	Date         string             `json:"date"`
	Label        string             `json:"label,omitempty"`
	Agent        string             `json:"agent"`
	Engine       string             `json:"engine"`
	DepthCap     int                `json:"depth_cap"`
	Games        int                `json:"games"`
	Seed         int64              `json:"seed"`
	ScoreMean    float64            `json:"score_mean"`
	ScoreMedian  int                `json:"score_median"`
	ScoreP90     int                `json:"score_p90"`
	ScoreP99     int                `json:"score_p99"`
	ScoreMax     int                `json:"score_max"`
	MovesPerGame float64            `json:"moves_per_game"`
	MsPerMove    float64            `json:"ms_per_move"`
	WallSec      float64            `json:"wall_sec"`
	Reach        map[string]float64 `json:"reach"`
}

func summarize(results []GameResult, wall time.Duration, label, engineName string, depthCap int, seed int64) Summary {
	n := len(results)
	scores := make([]int, n)
	var totalScore, totalMoves, totalMs int64
	maxScore := 0
	for i, r := range results {
		scores[i] = r.Score
		totalScore += int64(r.Score)
		totalMoves += int64(r.Moves)
		totalMs += r.DurationMs
		if r.Score > maxScore {
			maxScore = r.Score
		}
	}
	sort.Ints(scores)
	reach := map[string]float64{}
	for _, m := range milestones {
		cnt := 0
		for _, r := range results {
			if r.MaxTile >= m {
				cnt++
			}
		}
		reach[fmt.Sprintf("%d", m)] = float64(cnt) / float64(n)
	}
	return Summary{
		Date:         time.Now().Format(time.RFC3339),
		Label:        label,
		Agent:        "expectimax",
		Engine:       engineName,
		DepthCap:     depthCap,
		Games:        n,
		Seed:         seed,
		ScoreMean:    float64(totalScore) / float64(n),
		ScoreMedian:  pct(scores, 50),
		ScoreP90:     pct(scores, 90),
		ScoreP99:     pct(scores, 99),
		ScoreMax:     maxScore,
		MovesPerGame: float64(totalMoves) / float64(n),
		MsPerMove:    float64(totalMs) / float64(max64(totalMoves, 1)),
		WallSec:      wall.Seconds(),
		Reach:        reach,
	}
}

func appendSummary(path string, s Summary) error {
	if dir := filepath.Dir(path); dir != "" {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	line, err := json.Marshal(s)
	if err != nil {
		return err
	}
	_, err = f.Write(append(line, '\n'))
	return err
}

func report(results []GameResult, wall time.Duration) {
	n := len(results)
	scores := make([]int, n)
	var totalMoves, totalScore, totalMs int64
	maxScore, maxTile := 0, 0
	tileHist := map[int]int{}
	for i, r := range results {
		scores[i] = r.Score
		totalMoves += int64(r.Moves)
		totalScore += int64(r.Score)
		totalMs += r.DurationMs
		if r.Score > maxScore {
			maxScore = r.Score
		}
		if r.MaxTile > maxTile {
			maxTile = r.MaxTile
		}
		tileHist[r.MaxTile]++
	}
	sort.Ints(scores)

	fmt.Printf("\n==================== BASELINE REPORT ====================\n")
	fmt.Printf("games=%d  wall=%.1fs  avg_game=%.2fs\n", n, wall.Seconds(), wall.Seconds()/float64(n))
	fmt.Printf("\nScore:\n")
	fmt.Printf("  mean   %10.0f\n", float64(totalScore)/float64(n))
	fmt.Printf("  median %10d\n", pct(scores, 50))
	fmt.Printf("  p90    %10d\n", pct(scores, 90))
	fmt.Printf("  p99    %10d\n", pct(scores, 99))
	fmt.Printf("  max    %10d\n", maxScore)
	fmt.Printf("\nMoves/game: %.0f    best max-tile: %d\n", float64(totalMoves)/float64(n), maxTile)
	fmt.Printf("Search speed: %.1f ms/move avg\n", float64(totalMs)/float64(max64(totalMoves, 1)))

	fmt.Printf("\nReach rate (games whose max tile >= T):\n")
	for _, m := range milestones {
		cnt := 0
		for _, r := range results {
			if r.MaxTile >= m {
				cnt++
			}
		}
		fmt.Printf("  %6d : %5.1f%%  (%d/%d)\n", m, 100*float64(cnt)/float64(n), cnt, n)
	}

	fmt.Printf("\nMax-tile distribution:\n")
	tiles := make([]int, 0, len(tileHist))
	for t := range tileHist {
		tiles = append(tiles, t)
	}
	sort.Ints(tiles)
	for _, t := range tiles {
		fmt.Printf("  %6d : %d\n", t, tileHist[t])
	}
	fmt.Printf("========================================================\n")
}

// pct returns the p-th percentile of a sorted slice (nearest-rank).
func pct(sorted []int, p int) int {
	if len(sorted) == 0 {
		return 0
	}
	idx := (p*len(sorted) + 99) / 100 // ceil(p/100 * n)
	if idx < 1 {
		idx = 1
	}
	if idx > len(sorted) {
		idx = len(sorted)
	}
	return sorted[idx-1]
}

func max64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

func writeJSONL(path string, results []GameResult) error {
	if dir := filepath.Dir(path); dir != "" {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	for _, r := range results {
		if err := enc.Encode(r); err != nil {
			return err
		}
	}
	return nil
}
