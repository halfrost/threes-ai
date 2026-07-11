# Experiment Log

> The canonical, curated record of every experiment run in this project. It is
> the raw material for the blog and the paper, so **every run gets logged here**
> (config + key numbers + notes), newest first within each section. Raw per-game
> data lives in `results/*.jsonl` (git-ignored, but fully reproducible from the
> recorded seed + config since the engine is deterministic).

## Reproducibility / environment
- Engine is deterministic: game `i` uses `seed + i`; same config → same results.
- Machine: Apple Silicon (arm64), macOS 26. Go 1.21. Python 3.11.8.
- Reproduce a run: `go run ./cmd/bench -n <N> -seed <S> -depthcap <D> -bb -out results/<name>.jsonl`
- A machine-readable summary of each `bench` run is also appended to
  `results/summaries.jsonl` via `-log` (one JSON object per run).

## What to record (checklist for every experiment)
For each **agent evaluation**: agent name, engine (bitboard/slice), search depth
(cap), #games, seed range; score mean/median/p90/p99/max; per-tile reach rate
(esp. 384/768/1536/3072/**6144/12288**); moves/game; search speed (ms/move,
nodes/sec); wall time. For **ablations**: the one variable changed + the deltas.
For **training (N-tuple/RL)**: hyperparameters, learning curve (score & 6144-rate
vs self-play games), training wall time. For **deployment**: platform, final
score, max tile, screenshot/video links, any record achieved. Always note the
comparison point (prior baseline, or the 2016 MS-TD SOTA).

## Reference points (for paper positioning)
- **2016 MS-TD SOTA** (Yeh et al., arXiv:1606.07374): on Threes, reaching the
  6144 tile — MS-TD **7.83%**, plain TD **0.45%**.
- Known strong AI demo: **6144 tile, score 736,254** (public Threes AI video).
- 12288 tile = two 6144 merging = game ends (13th character); essentially the
  ceiling, achieved by only a handful of players/bots ever.

---

## 1. Baselines (existing hand-tuned Expectimax)

### B2 — Expectimax, bitboard, depth-cap 4, 30 games  ★ current reference baseline
- Config: `bench -n 30 -seed 1 -depthcap 4 -bb -workers 6`; `results/baseline_bb_depth4.jsonl`
- Score: mean **229,223** · median 209,715 · p90 550,095 · p99/max **793,014**
- Moves/game 1100 · best tile **6144** · wall 767.9s (~13 min) · ~125 ms/move (6-worker contended)
- Reach: 768 **100%** · 1536 **93.3%** · 3072 **56.7%** · **6144 13.3% (4/30)** · 12288 0%
- Note: **6144 rate 13.3% already exceeds the 2016 learning SOTA's 7.83%** — this
  is the honest strength of the *existing* hand-tuned heuristic once search depth
  is affordable (thanks to the bitboard port). This is the number to beat.

### B1 — Expectimax, slice, depth-cap 3, 12 games (preliminary floor)
- Config: `bench -n 12 -seed 1 -depthcap 3 -workers 6` (slice engine); `results/baseline_depth3_prelim.jsonl`
- Score: mean 102,640 · median 82,257 · p90 212,967 · max 238,758
- Moves/game 802 · best tile 3072
- Reach: 768 100% · 1536 75% · 3072 25% · 6144 0%
- Note: depth-3 **floor**, run on the slow `[][]int` engine while it was still the
  only option; superseded by B2. Kept for the depth-3 → depth-4 comparison.

---

## 2. Engine / performance benchmarks

### E1 — Move operation: bitboard vs slice
- `MoveBitboard` **10.57 ns/op, 0 B, 0 allocs** vs `gameboard.MakeMove` 191.2 ns/op, 256 B, 6 allocs.
- **~18× faster, zero allocations.** (`go test ./engine -bench Move`)

### E2 — Full search end-to-end: bitboard vs slice
- Same game (seed 1, depth-cap 3, 550 moves, score 29865, tile 768):
  slice **107.5 ms/move** (game 59.1s) → bitboard **11.2 ms/move** (game 6.2s).
- **~10× faster end-to-end, identical result.** (`go run ./cmd/diag -seed 1 -depthcap 3 [-bb]`)

---

## 3. Correctness verifications

### C1 — Bitboard move engine vs reference
- `MoveBitboard` vs `gameboard.MakeMove`: **2,000,000 random boards × 4 directions, 0 mismatches**
  (board, changed-lanes, moved-flag all bit-for-bit equal). `TestBitboardMatchesGameboard`.

### C2 — Bitboard search vs reference
- `ExpectSearchBB` vs `ExpectSearch`: **720 real gameplay positions, 0 move-decision mismatches**
  (depth-cap 2). `TestBBSearchMatchesSlice`. → the bitboard port is a verified pure speedup.

---

## 4. Ablations (planned — Phase 1+)
_deck-aware on/off; depth sweep 3/4/5/6; heuristic vs N-tuple leaf; beam on/off; TT on/off._

## 5. Training runs (planned — Phase 2/3)
_N-tuple TD, multi-stage TD; DQN / PPO / AlphaZero-style. Log learning curves + hyperparameters._

## 6. Deployment / records (planned — Phase 4)
_play.threesgame.com, threesjs.io, Android emulator: scores, max tiles, screenshots/videos._
