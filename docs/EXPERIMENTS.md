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

## Evaluation protocol (seeds)
- A run `-seed S -n N` plays N **distinct** games with seeds `S..S+N-1` (game i
  uses seed `S+i`). So "seed 1, N=1000" is 1000 different games, not one repeated.
- All configs use the **same** seed range (1..N) so comparisons are **paired** —
  the deck-blind vs deck-aware gap comes from the mode, not luck. Keep this.
- N=1000 is tight for mean/median and the 6144 rate (SE ~1.3%); a **rare event
  like the 12288 rate needs a much larger N** (e.g. 10000) to pin down — plan a
  one-off large-N run for the final 12288 number.
- Learned agents (Phase 2 N-tuple / Phase 3 RL): train on the self-play RNG
  stream, then report on a **fixed held-out eval seed set** (seeds 1..N), the
  SAME set for every agent and disjoint from training — never evaluate on
  training games.

## Reference points (for paper positioning)
- **2016 MS-TD SOTA** (Yeh et al., arXiv:1606.07374): on Threes, reaching the
  6144 tile — MS-TD **7.83%**, plain TD **0.45%**.
- Known strong AI demo: **6144 tile, score 736,254** (public Threes AI video).
- 12288 tile = two 6144 merging = game ends (13th character); essentially the
  ceiling, achieved by only a handful of players/bots ever.

---

## 0. Headline results (canonical: cloud box, corrected engine, N=1000)
> The full 2×6 grid — deck-blind AND deck-aware at every depth 1-6, N=1000, paired
> seeds 1..1000, bitboard + bonus-range engine (`scripts/rerun_cloud.sh`). These
> supersede all earlier numbers (laptop B1/B2/A1/A2 and the mixed-N first pass),
> which used an over-informed bonus preview and/or too few games.

### ★ MILESTONE — 12288 tile (game end) reproduced, now firm  [P2 achieved]
- Deck-aware depth-6 reaches **12288** — two 6144 merging, which ends the game —
  in **1.1% of games (11/1000)**. Deck-blind reaches it only once at depth 5
  (0.1%) and never at depth 6 → knowing the deck clearly helps close the game out.
- Best game: **2,161,704 points** (a 12288 *with a 6144 still on the board*),
  seed 960, depth 6, 2228 moves → `web/record_12288.json` (watch it in the viewer).
  Our hand-tuned Expectimax reaches the ceiling before any learning.
- Context: only a handful of humans/bots have ever reached 12288.

### H1 — Strength vs depth, both deck modes (N=1000)
| depth | mean (blind / aware) | 3072 (b/a) | 6144 (b/a) | 12288 (b/a) | ms/move |
|---|---|---|---|---|---|
| 1 | 23,109 / 23,872 | 0.1% / 0.2% | 0% / 0% | 0 / 0 | 4 |
| 2 | 61,211 / 63,184 | 6.7% / 7.5% | 0% / 0.1% | 0 / 0 | 3 |
| 3 | 111,253 / 117,292 | 26.1% / 28.8% | 0.9% / 1.3% | 0 / 0 | 70 |
| 4 | 179,460 / 177,042 | 51.9% / 51.9% | 5.9% / 4.6% | 0 / 0 | 360 |
| 5 | 234,732 / 251,707 | 68.0% / 69.8% | 11.6% / **15.2%** | 0.1% / 0 | 1380 |
| 6 | 264,119 / **301,228** | 72.2% / 73.9% | 16.4% / **21.2%** | 0 / **1.1%** | 2600 |
- Monotonic and still climbing at depth 6 (deck-aware 6144 15.2%→21.2%). ms/move
  growth *slows* at high depth (d5→d6 only ~1.9×) because the `CprobMin=1e-4`
  cutoff increasingly binds — depth 7+ gives diminishing returns for rising cost.

### H2 — ★ Key finding: the deck-aware advantage GROWS with depth
| depth | Δ mean (aware − blind) | Δ 6144 |
|---|---|---|
| 1 | +3.3% | 0 |
| 2 | +3.2% | +0.1 |
| 3 | +5.4% | +0.4 |
| 4 | −1.3% (noise) | −1.3 |
| 5 | **+7.2%** | **+3.6** |
| 6 | **+14.0%** | **+4.8** |
- Knowing the deck is nearly worthless at shallow depth but worth **+14% mean and
  +4.8 pts on the 6144 rate at depth 6** — more lookahead is needed to exploit the
  known upcoming tiles. This depth×deck interaction is the paper's core result;
  the earlier single-depth ablation (old A1, +25%) missed it entirely.

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

## 5. Training runs (N-tuple TD self-play)

### T1 — Small tuples (4× 4-cell), 5M games, α=0.1 — capacity-limited plateau
- `cmd/train -games 5000000 -alpha 0.1` (default small tuples). Greedy eval on
  fixed held-out seeds 1..1000.
- Learning curve: mean 627 (untrained) → 7,391 @100k → plateaus at **~10,000**
  for the rest of the 5M games (median ~8,000, 3072 rate stays 0%).
- Diagnosis: fast rise then a hard flat = **capacity limit**. The 4× 4-cell set
  (~1 MB) can't represent strong Threes play; greedy caps around the 768-1536 tile.
- Corroboration: this small model as an expectimax leaf (`ntuple-search`) scores
  ~52k @depth-3 — still below the hand heuristic at the same depth (deck-aware d3
  = 117k). So small tuples are insufficient even with search. → motivates BigTuples.

### T2 — Big tuples (4× 6-cell, ~270MB), 10M games, α=0.1 — breaks the T1 plateau
- `cmd/train -games 10000000 -alpha 0.1 -tuples big -eval-every 200000 -eval-n 1000`
  → `models/ntuple_big.gob`. Greedy eval on held-out seeds 1..1000. Wall 17,375s
  (~4.8h) on the 240-core box. (Curve extracted with `scripts/learning_curve.py`.)
- Learning curve (greedy mean / median): 627/468 → 11.1k/9.3k @1M → 15.5k/10.0k
  @2.4M → **20.9k / 21.5k @10M** (peak mean 21.4k @9.2M). Near-saturating: mean
  reaches 95% of final by ~7.4M.
- **Key result — capacity WAS the bottleneck.** Big tuples roughly double the
  small-tuple ceiling (mean ~10k → ~21k), confirming T1's plateau was the ~1 MB
  weight table, not training time or α.
- **Phase-transition in the median** (nice figure for the paper): median sits at
  ~9-10k (like T1) until ~4M games, then jumps to ~21k over 4M–5.6M (bimodal
  during the crossover), then holds. Interpretation: the policy crosses a
  threshold where it *reliably builds a 768 tile* (768 = 19,683 pts ≈ median).
- Caveat: still a **depth-0 greedy** policy — 3072 rate stays 0% throughout, best
  games top out at 1536 (max score ~88k). An order of magnitude below the depth-6
  expectimax (6144 @21%). Its real job is as a **search leaf** → T3.

### T3 — Big-tuple value function as an expectimax leaf vs the hand heuristic — running
- `scripts/eval_ntuple_search.sh models/ntuple_big.gob` — for depths 3/4/5, same
  seeds, `ntuple-search` (learned leaf) vs `expectimax` (hand heuristic), both
  deck-aware, N=1000. The paper's central learned-value-vs-hand-heuristic test:
  can a learned leaf let a *shallower* search match a *deeper* hand-heuristic one
  (a compute win), and/or lift the 3072/6144 rates? (Results: TBD.)

### T4 — big2 + temporal-coherence + α anneal, to break the T2 plateau — ready to run
- `scripts/train_big2_tc.sh` → `models/ntuple_big2_tc.gob`. Three levers stacked
  on T2: (a) **big2** tuple set — eight 6-cell shapes (~540 MB), ~2x the capacity
  of big; (b) **temporal-coherence** (`train -tc`) — per-weight adaptive step
  |N_i|/A_i that damps oscillating weights (~1.6 GB resident); (c) **α anneal**
  (`-alpha-final`) — linear decay so the run settles instead of dithering at a
  constant 0.1. Hypothesis: greedy asymptote clears the T2 ~21k ceiling; then
  re-run T3 with this model as the leaf. (Results: TBD.)

_Planned later: DQN / PPO / AlphaZero-style baselines (Phase 3, needs a GPU box)._

## 6. Deployment / records (planned — Phase 4)
_play.threesgame.com, threesjs.io, Android emulator: scores, max tiles, screenshots/videos._
