# Experiment Log

> The canonical, curated record of every experiment run in this project. It is
> the raw material for the blog and the paper, so **every run gets logged here**
> (config + key numbers + notes), newest first within each section. Raw per-game
> data lives in `results/*.jsonl` (git-ignored, but fully reproducible from the
> recorded seed + config since the engine is deterministic).

## Reproducibility / environment
- Engine is deterministic: game `i` uses `seed + i`; same config → same results.
- Reproduce a run: `go run ./cmd/bench -n <N> -seed <S> -depthcap <D> -bb -deckaware -out results/<name>.jsonl`
- A machine-readable summary of each `bench` run is also appended to
  `results/summaries.jsonl` via `-log` (one JSON object per run).

**Machines**
- **Dev laptop**: Apple Silicon (arm64), macOS 26. Go 1.21, Python 3.11.8. Used
  for the early small-N runs (B1/B2/A1/A2) before the corrected engine.
- **Cloud compute box** (canonical large-N reruns, `scripts/rerun_cloud.sh`):
  - Intel Xeon **6986P-C** (Granite Rapids), x86_64, single socket.
  - **240 vCPUs** = 120 physical cores × 2 threads/core. 3 NUMA nodes (0-79 / 80-159 / 160-239).
  - Cache: L1d 5.6 MiB, L1i 7.5 MiB, L2 240 MiB, **L3 504 MiB**.
  - ISA highlights: AVX-512 (F/DQ/BW/VL/VNNI/BF16/FP16/VBMI2), **AMX** (tile/int8/bf16), SHA-NI, VAES. BogoMIPS 5600.
  - Virtualized: KVM (QEMU pc-i440fx-5.2).
  - Note: expectimax / N-tuple are CPU-bound and scale ~linearly with cores here;
    there is **no GPU**, so the RL baselines (DQN/PPO/AlphaZero, Phase 3) will be
    the slow part. Cross-arch: aggregate stats match the laptop; rare single games
    can differ by a `math.Pow` ULP, so paper numbers come from this one box.

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

## 0. Headline results (canonical: cloud box, corrected bonus-range engine)
> These supersede the earlier small-N laptop runs (B1/B2/A1/A2), which used an
> over-informed bonus preview (exact value instead of a "+") and very few games.
> Config: bitboard + deck-aware unless noted, `scripts/rerun_cloud.sh`, seeds from 1.
> NOTE: this first cloud pass used mixed N (d5 1000, d1-d4 500, d6 **only 200** —
> so the 12288 rate below rests on just 3 games) and only compared deck modes at
> depth 5. A uniform rerun is queued: **both deck-blind and deck-aware at every
> depth 1-6, all N=1000** (a full 2×6 grid, paired seeds), which firms up the
> 6144/12288 rates and gives the deck-aware gap at every depth.

### ★ MILESTONE — the 12288 tile (game end) reproduced  [P2 achieved]
- Reached **12288** — two 6144 merging, which ends the game — in the deck-aware
  depth-6 run: **1.5% (3/200 games)**, and once at depth-5 deck-blind (0.1%, 1/1000).
- Best game: **1,973,688 points**, max tile **12288**, seed 172, depth 6, 2055 moves
  → `results/records/record_1973688.json` (load it in web/replay.html to watch it).
- Context: 12288 is essentially the ceiling; only a handful of humans/bots have
  ever done it. Our hand-tuned Expectimax reaches it before any learning.

### H1 — Depth sweep, deck-aware — strength vs depth
| depth | N | mean | median | 3072 | 6144 | 12288 | ms/move |
|---|---|---|---|---|---|---|---|
| 1 | 500 | 24,658 | 22,254 | 0.4% | 0% | 0% | 4 |
| 2 | 500 | 61,193 | 62,619 | 6.2% | 0% | 0% | 3 |
| 3 | 500 | 117,568 | 86,922 | 28.6% | 1.6% | 0% | 64 |
| 4 | 500 | 176,111 | 187,518 | 51.4% | 4.4% | 0% | 327 |
| 5 | 1000 | 251,707 | 219,912 | 69.8% | **15.2%** | 0% | 1334 |
| 6 | 200 | 319,029 | 253,029 | 77.0% | **22.5%** | 1.5% | 1983 |
- Monotonic and still climbing at depth 6 (6144: 15.2%→22.5% from d5→d6). Numbers
  are lower than the old laptop estimates because the bonus preview is now a range
  (not the exact value) and N is far larger. Cost ~4-5x per depth level.

### H2 — Deck-aware vs deck-blind @ depth 5 (N=1000, paired seeds 1..1000)
| metric | deck-blind | deck-aware | Δ |
|---|---|---|---|
| score mean | 234,732 | **251,707** | **+7.2%** |
| score median | 213,213 | 219,912 | +3.1% |
| 3072 reach | 68.0% | 69.8% | +1.8 pts |
| 6144 reach | 11.6% | **15.2%** | **+3.6 pts** (~2.4σ) |
- Deck-aware is a real but **modest** edge at N=1000. The earlier +25% (A1) was a
  50-game estimate on the over-informed engine; this is the honest number. (The
  deck-blind max of 1,833,213 is a single lucky 12288 game — tail noise; the mean,
  median and 6144-rate all favour deck-aware.)

---

## 1. Baselines — early small-N laptop runs (SUPERSEDED by section 0)

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

## 4. Ablations

### A1 — Deck-aware vs deck-blind (the "value of knowing the deck") ★ flagship result
- Setup: Expectimax, bitboard, depth-cap 4, **50 games, paired seeds 1–50**. Only
  variable: the `candidate` fed to the search — `FindCandidates` board
  approximation (**deck-blind**) vs `Game.DeckCounts` true remaining bag (**deck-aware**).
- `results/ablation_deckblind_d4.jsonl`, `results/ablation_deckaware_d4.jsonl`

| metric | deck-blind | deck-aware | Δ |
|---|---|---|---|
| score mean | 209,633 | **262,348** | **+25.1%** |
| score median | 187,800 | **246,165** | **+31.1%** |
| score p90 | 277,410 | **600,201** | +116% |
| score max | 793,014 | 745,299 | −6% (one lucky blind game; distribution clearly higher) |
| 3072 reach | 54% | **74%** | **+20 pts** |
| 6144 reach | 10% (5/50) | **14% (7/50)** | +4 pts (small-sample) |
| 1536 reach | 92% | **100%** | early collapses eliminated |
| moves/game | 1034 | 1177 | survives longer |

- Takeaway: **using the true remaining bag instead of a board approximation is worth
  ~+25% mean score and +20 points on the 3072 rate at equal search depth**, and it
  removes early collapses (deck-blind died at 192/768 in a few games; deck-aware's
  worst tile was 1536). The 6144 delta is positive but within 50-game noise — rerun
  larger to firm it up. This is the paper's core novelty result.
- Note: deck-blind here (50 games) sits a bit below B2 (30 games, 6144 13.3%) —
  expected sampling difference; this 50-game paired run is the cleaner reference.

### A2 — Depth sweep (deck-aware) — deeper search still helps
- Expectimax, bitboard, deck-aware. Same seeds from 1. `results/eval_deckaware_d5.jsonl`

| depth | games | score mean | 3072 | 6144 | max |
|---|---|---|---|---|---|
| 4 | 50 | 262,348 | 74% | 14% | 745,299 |
| 5 | 30 | 345,976 | 83.3% | **26.7% (8/30)** | 797,169 |

- Takeaway: depth 4→5 nearly **doubles the 6144 rate (14%→26.7%)** and lifts mean score +32%.
  Search depth has NOT plateaued — depth 6 should push 6144 past the P1 target (>=30%),
  even before any learning. Cost: depth-5 is ~456 ms/move (~103 s/game); depth 6 will be
  ~3-5x that, which is why the 240-core cloud box matters (and why N-tuple, giving deep-
  quality play at shallow cost, is the long-term answer).
- Best replay of the depth-5 run saved: `results/records/record_797169.json` (797,169).

_Planned: depth 6 (on cloud); heuristic vs N-tuple leaf; beam on/off; TT on/off._

## 5. Training runs (planned — Phase 2/3)
_N-tuple TD, multi-stage TD; DQN / PPO / AlphaZero-style. Log learning curves + hyperparameters._

## 6. Deployment / records (planned — Phase 4)
_play.threesgame.com, threesjs.io, Android emulator: scores, max tiles, screenshots/videos._
