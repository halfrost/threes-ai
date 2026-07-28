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
> The full 2×9 grid — deck-blind AND deck-aware at every depth 1-9, N=1000, paired
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
| 7 | 290,900 / 313,775 | 72.9% / 76.3% | 20.7% / 23.0% | 0.5% / 1.1% | 3195 |
| 8 | 295,419 / **321,016** | 73.2% / 75.7% | 21.9% / **25.2%** | 0.6% / 1.1% | 3313 |
| 9 | 293,524 / 319,441 | 73.2% / 75.7% | 21.9% / 25.0% | 0.4% / 1.0% | 3316 |
- **Depth returns saturate at d7–d8** (cloud box, N=1000, seed-paired, extends the
  grid to 9). Deck-aware mean: d6 301k → d7 314k → **d8 321k (peak)** → d9 319k;
  the d8→d9 change is negative, i.e. noise. 6144 rate peaks at d8 (25.2%).
- **d8 ≈ d9 are the same policy**: identical median (250,587), ms/move (3313 vs
  3316) and moves/game (1207 vs 1206). The adaptive depth `DeptMax≈emptyCount−2`
  (plus the `CprobMin=1e-4` cutoff) caps the *effective* depth below 8 in almost
  every node, so raising the cap from 8→9 changes almost nothing. **d8 is the
  practical ceiling for this search; deeper is wasted compute.** For the paper: the
  strength-vs-depth curve is concave and flattens by d7, motivating the learned
  leaf (T3) as the way to buy strength that raw depth no longer can.

### H2 — ★ Key finding: the deck-aware advantage GROWS with depth
| depth | Δ mean (aware − blind) | Δ 6144 |
|---|---|---|
| 1 | +3.3% | 0 |
| 2 | +3.2% | +0.1 |
| 3 | +5.4% | +0.4 |
| 4 | −1.3% (noise) | −1.3 |
| 5 | **+7.2%** | **+3.6** |
| 6 | **+14.0%** | **+4.8** |
| 7 | +7.9% | +2.3 |
| 8 | +8.7% | +3.3 |
| 9 | +8.8% | +3.1 |
- Knowing the deck is nearly worthless at shallow depth but worth **+8–14% mean and
  +3–5 pts on the 6144 rate at depth 6–9** — more lookahead is needed to exploit the
  known upcoming tiles. The advantage holds firm (≈+8–9%) once depth saturates; it
  doesn't wash out with more search. This depth×deck interaction is the paper's core
  result; the earlier single-depth ablation (old A1, +25%) missed it entirely.
  (The d6 +14% is the widest point; d7–9 settle at ≈+9% as both modes plateau.)

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

### ★ Training runs at a glance (T1–T6) + learning-curve comparison
> Every N-tuple TD self-play run so far, greedy-eval mean of 1000 fixed held-out games.
> Raw logs: `results/cloud_t3/train{,_big}.log` (T1/T2), `results/cloud_t4/…` (T4),
> `results/cloud_t5/train_big_tc.log` (T5), `results/cloud_t6/train_big2.log` (T6).
> Interactive figure (T1/T2/T4; T5/T6 pending refresh):
> **https://claude.ai/code/artifact/8ef3aedc-1ae2-4e62-9ecb-5567fe477049** —
> regenerate from any log with `scripts/learning_curve.py`.

| run | tuples | α schedule | TC | games | peak mean | final mean | 3072 | verdict |
|---|---|---|---|---:|---:|---:|---:|---|
| **T1** | small 4×4 (~1 MB) | const 0.1 | no | 5M | 10,709 | 9,868 | 0% | capacity-capped ≈10k (no phase jump) |
| **T2** | big 4×6 (~270 MB) | const 0.1 | no | 10M | **21,371** | 20,968 | 0% | **best** — phase jump ~4M; still rising @10M |
| **T3** | — (T2 model as expectimax **leaf**) | — | — | — | — | — | — | beats hand heuristic only at d3; loses d4–d5, 8–11× slower |
| **T4** | big2 8×6 (~540 MB) | 0.1→0.01 anneal | yes | 15M | 9,809 | 9,608 | 0% | **regressed** — both bad levers stacked |
| **T5** | big 4×6 (~270 MB) | 0.1→0.01 anneal | yes | 15M | 16,028 | 16,028 | 0% | TC+anneal hurts big by −24% (vs T2) |
| **T6** | big2 8×6 (~540 MB) | const 0.1 | no | 15M | 16,506 | 16,506 | 0% | big2 under-trained (−21% vs T2 but steepest still-rising curve) |

Two clean results fall out of this table: (1) T2's **phase transition** (the representation-strength story), and (2) the **2×2 ablation** (const-α ≫ TC+anneal; big2 under-trained; T4 = both) — detailed below. Best model so far: **T2** (big, const α). Every run's 3072-rate is 0% (all are greedy depth-0 values, an order of magnitude below the depth-6 expectimax — their use is as a search leaf, T3/T9).

- **The single most important shape in the whole training story is T2's phase
  transition.** All three curves rise fast to ~10k in the first ~200k games; then
  they diverge. T1 flatlines at its capacity ceiling. T2 sits with T1 at ~10k until
  ~4M games and then **jumps to ~21k over 4M–5.6M** (bimodal during the crossover)
  — the point where the value table starts *reliably building a 768 tile*
  (768 = 19,683 pts ≈ the new median). T4, despite 2× capacity + TC + anneal + 50%
  more games, **never leaves the low plateau** and ends *below* even the small-tuple
  T1 baseline.
- **Headline for the blog/paper:** more capacity and more machinery did not help — it
  hurt. Capacity alone (T1→T2) unlocked the transition; adding capacity *together
  with* TC + α-anneal (T4) suppressed it. Whether the culprit is the extra levers or
  simple under-training of 2× weights at 15M is exactly what the T5/T6 ablations
  resolve (see T4 and T6 below).
- Note the axes caveat: these are **depth-0 greedy** asymptotes (no search), the
  clean signal for *representation strength*. All three are an order of magnitude
  below the depth-6 expectimax; the learned value's real use is as a search leaf (T3).

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

### T3 — Big-tuple value function as an expectimax leaf vs the hand heuristic — ★ done (cloud, N=1000)
`scripts/eval_ntuple_search.sh models/ntuple_big.gob` — depths 3/4/5, same seeds,
`ntuple-search` (the T2 big model as the leaf) vs `expectimax` (hand heuristic),
both deck-aware. Head-to-head (`results/ntsearch_summaries.jsonl`):

| depth | mean (hand / ntuple) | 3072 (h/n) | 6144 (h/n) | ms/move (h/n) |
|---|---|---|---|---|
| 3 | 117,292 / **126,952** | 28.8% / **33.6%** | 1.3% / 0.8% | 67 / 579 |
| 4 | **177,042** / 159,011 | **51.9%** / 47.5% | **4.6%** / 2.9% | 346 / 3,650 |
| 5 | **251,707** / 190,246 | **69.8%** / 56.2% | **15.2%** / 6.4% | 1,348 / 14,284 |

- **The learned leaf helps only at shallow depth.** At d3 the T2 model beats the
  hand heuristic (+8.2% mean, +4.8 pts on 3072); at d4 and d5 the hand heuristic
  pulls ahead and the gap *widens* (−10% at d4, −24% at d5, and less than half the
  6144 rate at d5).
- **The compute-win hypothesis fails.** The learned leaf is 8–11× slower per move
  (the big 4×6 table is costly to evaluate at every leaf), so ntuple-leaf-d3
  (127k @ 579 ms) does not come close to hand-heuristic-d4 (177k @ 346 ms) — at
  equal or less compute the hand heuristic dominates.
- **Why:** T2 was trained as a **depth-0 greedy** value function (greedy asymptote
  ~21k, saturated). Such a value is fine as a *shallow* leaf but a hand heuristic
  with explicit merge / monotonicity / empty terms is a better and far cheaper
  evaluator once search does the lookahead. **This is the motivation for T4** — a
  *stronger* learned value (break the greedy plateau) is needed before a learned
  leaf can beat the hand heuristic at useful depths.
- Best single game across all T3 runs: **860,298 (6144 tile)** — from the hand
  heuristic at d4 (`results/records/record_860298.json`).

### T4 — big2 + temporal-coherence + α anneal — ★ done, and it REGRESSED
`scripts/train_big2_tc.sh` → `models/ntuple_big2_tc.gob`, 15M games, big2 (eight
6-cell shapes, ~540 MB) + `-tc` + α 0.1→0.01 (cloud box, machine 01,
`results/cloud_t4/train_big2_tc.log`). Greedy (depth-0) asymptote:

| games | 2.5M | 5M | 10M | 15M |
|---|---|---|---|---|
| mean | 6,080 | 7,472 | 9,053 | **9,608** |

- **The three levers made it WORSE, not better.** T4 tops out ~9.6k greedy vs
  **T2's ~21k** (big, constant α) — despite 2× the capacity, TC, anneal, and 15M vs
  10M games. 3072/6144 stay 0% throughout; max only ~70k.
- **No phase transition.** T2 jumped to ~21k around 4M games; T4 just climbs
  smoothly and is *still rising* at 15M — i.e. either big2's 2× parameters are
  badly under-trained at 15M, or TC/anneal changed the dynamics and suppressed the
  jump. Can't attribute it from T4 alone → the ablations decide it:
  - **T5** (big + TC + anneal, machine 02) isolates the TC+anneal levers vs T2.
  - **T6** (big2 + constant α) isolates big2's capacity vs the levers.
- **Not worth evaluating as a search leaf.** T2's stronger big model already lost
  to the hand heuristic as an expectimax leaf (T3); a weaker greedy value won't beat
  it, so skip the T3-style leaf eval for T4.

### T5 — big + TC + α anneal (ablation for T4) — ★ done
`scripts/train_big_tc.sh` → `models/ntuple_big_tc.gob` (60 MB), 15M games, `big`
(4×6) + `-tc` + α 0.1→0.01 (machine 02, `results/cloud_t5/train_big_tc.log`). Greedy
mean: 8.5k@1M → 14.0k@7M → 14.7k@10M → **16.0k@15M** (peak 16k, 3072/6144 stay 0%).
Isolates the TC+anneal levers with the tuple set held at `big`: **T2 (big, const α,
21.0k) → T5 (big, TC+anneal, 16.0k) = −24%.** TC+anneal *hurts*, and the curve
flattens early (only +0.7k over 7M→10M) — the α-anneal starves late learning.

### T6 — big2 + constant α (complete the 2×2) — ★ done
`scripts/train_big2.sh` → `models/ntuple_big2.gob` (117 MB), 15M games, `big2` (8×6),
constant α=0.1 (machine 01, `results/cloud_t6/train_big2.log`). Greedy mean:
6.2k@1M → 11.1k@7M → 13.5k@10M → **16.5k@15M** (still rising steeply, +3.0k over
10M→15M; 3072/6144 stay 0%). Isolates big2's capacity with α held constant: **T2
(big, 21.0k) → T6 (big2, 16.5k) = −21% at 15M** — but T6 has the *steepest* late slope
of any run and has not plateaued, so big2 is **under-trained, not inherently worse.**

### ★ The 2×2 ablation — TC+anneal HURTS, big2 is UNDER-TRAINED (T4 stacked both)
> Greedy self-play mean (N=1000 held-out), at each run's end. This is the clean
> attribution of T4's regression, and a tidy paper result.

|             | constant α | TC + α-anneal |
|---|---:|---:|
| **big** (4×6)  | **T2 = 20,968** (@10M) | T5 = 16,028 (@15M) |
| **big2** (8×6) | T6 = 16,506 (@15M) | **T4 = 9,608** (@15M) |

- **TC + α-anneal consistently hurts** (hold tuples fixed): big −24% (T2→T5), big2
  −42% (T6→T4). The linearly-annealed α (0.1→0.01) drops the learning rate too low too
  early, so the net under-learns; TC compounds it. **Verdict: drop TC+anneal for this
  task.**
- **big2 is under-trained, not worse** (hold α fixed): big2 is −21% (const) / −40%
  (TC+anneal) vs big *at 15M*, but its curve is the steepest still-rising one (+3.0k in
  its last 5M). 2× the weights need ≫15M games to fill.
- **T4's regression = both handicaps compounding** (big2 under-training × TC+anneal's
  LR-starvation) → ~9.6k, less than half of T2.
- **T2 (big + constant α) remains the best model** (~21k, and it too was still rising at
  10M — the const-α/big recipe both learns fastest *and* highest at this budget).
- Skip the T3-style leaf eval for T5/T6: both are *weaker* greedy than T2, and T2 as a
  leaf already lost to the hand heuristic at d4–d5 (and is 8–11× slower), so weaker
  learned leaves won't beat it either. (Re-open only if a resumed run clears ~25k.)

### ★ T7 — resume T2 (`big` + const α) 10M → 30M — DONE, and it says **STOP**
- Config: `scripts/train_big_resume.sh`; resume `models/ntuple_big.gob` (T2's 10M),
  +20,000,000 games, α=0.1 const, `big` (4×6), train seeds 20M–40M (disjoint from T2's),
  eval on the fixed held-out seeds 1..1000. 41,674 s ≈ **11.6 h** on the 240-core box.
  Archived: `models/ntuple_big_t7_30m.gob` (72.7 MB) — see §7.
- Result: mean **20,968 → 23,507 (+2,539, +12.1%)**, median 21,507 → 22,806.
- **But the curve FLATTENED — the shape matters more than the endpoint:**

| games (cum.) | 10M (T2) | 15M | 20.5M | 23M | 25M | 27.5M | 30M |
|---|---|---|---|---|---|---|---|
| mean | 20,968 | 21,773 | **24,788** | 24,146 | 24,061 | 24,291 | 23,507 |

  It peaks at **24,788 (20.5M cumulative)** and then just oscillates in a 22–24.8k band
  with **no trend** — the final point is *below* the peak. **The last ~10M games (≈6 h ×
  240 cores) bought nothing.** `big` (4×6) is at its capacity ceiling, ~23–24k.
- **3072 = 0.0%, 6144 = 0.0% at every single eval.** The greedy N-tuple essentially never
  reaches a high tile (max ≈ 85–90k).
- **The sobering comparison: T7's 23,507 ≈ deck-aware depth-1 expectimax (23,872).**
  30M games of TD ≈ one ply of search, and **12× weaker than depth-6 (301k)**. Against the
  2016 MS-TD SOTA (6144 in **7.83%**) our greedy net is at **0.0%**.
- **Verdict: do not resume `big` again.** The open question is no longer "more games?" but
  "is it capacity?" — which is exactly what **T8** tests.

### ★ T3 — the learned net as the expectimax leaf — DONE (negative, and instructive)
`run_ntsearch.sh` (`results/ntsearch_big_d{3,4,5}.jsonl` vs `results/expectimax_d{3,4,5}.jsonl`,
paired seeds, deck-aware). Swaps the hand heuristic leaf for the T2 net:

| depth | N-tuple leaf: 1536 / 3072 / 6144 | hand heuristic: 1536 / 3072 / 6144 | winner |
|---|---|---|---|
| 3 | 88.2% / **33.6%** / 0.8% | 81.5% / 28.8% / **1.3%** | ntuple on 3072, heuristic on 6144 |
| 4 | 88.8% / 47.5% / 2.9% | **93.0% / 51.9% / 4.6%** | heuristic |
| 5 | 91.3% / 56.2% / 6.4% | **96.6% / 69.8% / 15.2%** | heuristic, by 2.4× on 6144 |

- **The learned leaf loses, and the gap WIDENS with depth** (it only wins the 3072 rate at
  d3, the shallowest). Self-consistent with T7: a leaf worth ~1 ply cannot pay for itself
  once the search is doing 4–5 plies, and the deeper the search the more a good leaf matters.
  It is also 8–11× slower to evaluate.
- This is why **T9 (leaf-aligned)** matters: T3 trains the net greedily and then *uses* it
  as a search leaf — a train/test mismatch. T9 trains it the way it is used
  (`cmd/train -search-depth 1`). It is the honest attempt to rescue this line.
- (Aside: `results/records/record_860298.json` — **860,298, 6144 tile, 2040 moves** — is a
  lucky *expectimax d4* game from this run's baseline arm, not a new record; our best
  remains the 2,161,704 / 12288 at d6.)

### ★ T8 — resume T6 (`big2` + const α) 15M → 40M — DONE. **Capacity is NOT the bottleneck.**
- Config: `scripts/train_big2_resume.sh`; resume `models/ntuple_big2.gob` (T6's 15M),
  +25,000,000 games, α=0.1 const, `big2` (8×6 = 2× the weights of `big`), train seeds 25M–50M,
  held-out eval seeds 1..1000. 77,380 s ≈ **21.5 h** on the 240-core box. Log:
  `docs/runs/train_big2_resume_t8.log`.
- Curve: 16,506 (T6) → 19k (5M) → 21k (13M) → **plateau ~22–23k**. Peak **22,911** at 36.5M
  cumulative, final (40M) **22,269**. From 12M cumulative on it just oscillates in a 20.5–23k
  band with no trend — converged.
- **The verdict: `big2` (22.3k) never catches `big` (T7: 23.5k), despite 2× the weights AND
  40M vs 30M games.** More capacity did not help — if anything it's ~1k worse. **3072 = 0.0%,
  6144 = 0.0%** at every eval (max spikes to 88k, rarely 180–256k). So capacity is decisively
  **not** the lever; the ceiling is the single-net greedy-TD *recipe*.
- (Nice detail for the paper: the *median* steps from ~10k to ~20k around 4–5M games — the
  policy crosses a threshold where it reliably banks a mid tile — then stalls. Mean and median
  converge (~22k/22k), i.e. the distribution tightened but its ceiling didn't rise.)

### ★ T9 — leaf-aligned bootstrap (approach "A") — DONE. Greedy **collapsed**; very likely dead.
- Config: `scripts/train_leaf_aligned.sh`; warm-start **T7's 30M net (23,507)**, α=0.03,
  `-search-depth 1` (moves chosen by depth-1 expectimax with the net at the leaf), 1.5M games,
  train seeds from 90M, out `models/ntuple_big_leaf.gob`. 155,056 s ≈ **43 h** (the box was
  contended in the last third — 1.0M→1.1M games took 27k s vs ~6.8k s earlier). Log:
  `docs/runs/train_leaf_t9.log`.
- Curve (greedy eval): 23,507 → **8,478** (100k) → 5,974 → 4,048 → … → **3,263** (1.5M).
  A **monotonic 7× collapse with no recovery**; median 22,806 → 1,143.
- Read carefully: greedy score is *not* the intended metric (the net is being re-aimed from
  greedy player to search leaf, so *some* greedy drop is expected). **But a collapse to ~3.3k
  is near-random play** — greedy move choice only needs the value's *ordering*, and losing the
  ordering this badly means the value is very likely a *worse* leaf too, not a re-calibrated
  one. Strong prior: **A failed** — α=0.03 with the net bootstrapping its own leaf diverged.
- To confirm (needs the model, not uploaded): on machine 02 run
  `bash scripts/eval_ntuple_search.sh models/ntuple_big_leaf.gob $(nproc) "3 4 5"` and compare
  to T3's leaf numbers. If it doesn't clear T3 (it almost certainly won't), approach A is dead.

### ★ The N-tuple line is capped — three levers tried, all negative → multi-stage (T10)
Putting T7/T8/T9/T3 together, every single-net lever has now been ruled out:
| lever | experiment | result |
|---|---|---|
| more games | T7 (`big` 10M→30M) | plateau 23.5k, **flat** |
| more capacity | T8 (`big2` →40M) | 22.3k, **≤ big** |
| align the leaf | T9 (search-depth-1 FT) | greedy **collapsed to 3.3k** |
| use net as leaf | T3 (net in expectimax) | **loses** to hand heuristic, gap widens with depth |

A single net tops out at **~23–24k greedy, 0.0% at 3072**, and cannot beat the hand-tuned
leaf. This is a clean, convergent negative result and it points at exactly one structural
change left.

### ★ T10 — multi-staging — DONE. Broke the plateau (23.5k → 28k, +19%); endgame still uncracked.
The 2016 MS-TD paper reaches the 6144 in **7.83%** with a *learned* agent (vs 0.45% for a
plain net); our single net is at **0.0%**. Their "**MS**" is literally *multi-stage*:
**separate value functions per game phase**. A board's value changes character once big tiles
dominate, so one weight set averages over irreconcilable regimes and ends up mediocre at all
of them — exactly the ~23k plateau we hit from every direction (T7/T8/T9). T10 gives each
phase its own net.

**Implementation** (`cmd/train-ms`, `scripts/train_ms.sh`; `cmd/train` left untouched so all
baselines still run):
- **Stages by max-tile index**: `-stages 10,13` ⇒ 3 stages `≤192 | 384–1536 | ≥3072` (indices
  10=384, 13=3072). One full `big` net per stage — `big`, not `big2`, since T8 proved the
  extra capacity is wasted.
- **Learning** — afterstate TD(0) that flows across stage boundaries: the update touches the
  stage net of the *previous* afterstate, and the bootstrap `V(s')` uses the stage net of the
  *next* afterstate. Move selection dispatches each candidate afterstate to its own stage net.
- **Warm-start every stage from T7's 30M** (`-init`): the top stages are otherwise data-starved
  (from-scratch self-play reaches stage 1 only ~66 times in 200 games and stage 2 never). The
  eval line prints per-stage `touched` counts so starvation is visible.
- **Validated (smoke)**: warm-started, stage 1 got **35k** updates in 200 games (vs 66 from
  scratch) and greedy mean rose **21.2k → 23.0k immediately** — the split is already helping and
  the mechanics are correct. Seeds from 100M (disjoint from T1–T9).

**RESULTS — DONE (both variants, 20M games each, ~11–14 h).** Logs:
`docs/runs/train_ms_t10_s10{12,13}.log`.

| variant | stages | final mean (20M) | peak | median | 3072 | top-stage `touched` |
|---|---|---|---|---|---|---|
| A `10,12` | ≤192 \| 384–768 \| **≥1536** | **28,011** | 28,388 (14M) | 23,145 | ~0.1% | 363M (well-fed) |
| B `10,13` | ≤192 \| 384–1536 \| **≥3072** | **28,009** | 28,009 (20M) | 23,538 | ~0.1% | **82k (starved)** |

- **★ Multi-staging is the FIRST lever to break the single-net plateau: 23,507 → ~28,000
  (+19%).** More games (T7), more capacity (T8), leaf-align (T9) all failed to move it; splitting
  the value function by phase moved it immediately and monotonically. The MS hypothesis holds —
  one net really was averaging over irreconcilable regimes.
- **But the gain is upper-tail, not endgame.** Median barely moved (22,806 → ~23,300, +2%) while
  the mean jumped +19% — multi-staging fattened the high-scoring tail (max spikes to ~180k, a
  3072 game, more often) but **3072% stayed ~0.0%** (0.1% blips). It makes the mid-game more
  efficient; it does **not** crack the 3072 barrier. Still far from MS-TD's 6144 @ 7.83%.
- **The two boundaries tie (~28k), and it's NOT the top stage doing the work.** B's ≥3072 stage
  got only 82k updates (starved — the chicken-and-egg: can't reach 3072 to learn to reach 3072),
  yet B ≈ A whose ≥1536 stage got 363M. So the whole +19% comes from **stages 0/1 specialising**
  (opening + mid), not from an endgame net. Feeding the top stage more didn't help.
- **Takeaway / next:** multi-staging is real and worth keeping (best learned agent so far, 28k),
  but greedy multi-stage TD still can't reach the endgame. Cracking 3072+ likely needs one of:
  (a) **more/finer stages** in the mid-game where the gain lives; (b) **multi-stage × search** —
  use the per-stage nets as expectimax leaves (T3 redux, now each leaf is phase-calibrated);
  (c) a **curriculum** that seeds the endgame stage with data (e.g. start some self-play games
  from high-tile boards) to break the starvation. (b) is the most promising — the search already
  reaches 6144 21% of the time, and a phase-calibrated leaf is exactly what T3 lacked.

**Success = greedy mean clears T7's 23,507 and/or 3072% goes non-zero.** If T10 works, the same
per-stage nets also become the expectimax leaf worth re-testing (T3 redux) now that each is
calibrated to its phase.

### ★ T11 — the T10 stage nets as the expectimax leaf — DONE. **Decisive negative: worse, not better.**
`cmd/bench -agent ntuple-ms-search` (dispatches each leaf to its phase's net), both T10 variants,
deck-aware N=1000 at d3/4/5 vs the single-net(T7 30M) leaf and the hand heuristic on identical
seeds. Logs: `docs/runs/eval_ms_search_t11_s10{12,13}.log`.

| | d3 3072/6144 | d4 3072/6144 | d5 3072/6144 |
|---|---|---|---|
| **ms-search** (s1012, 10,12) | 27.5% / 0.4% | 34.8% / 1.3% | 40.4% / 1.9% |
| **ms-search** (s1013, 10,13) | 24.7% / 0.4% | 32.5% / 1.4% | 38.6% / 3.1% |
| single-net leaf (T7 30M) | 37.0% / 0.6% | 44.5% / 2.2% | 53.6% / 4.7% |
| **hand heuristic** (the bar) | 28.8% / 1.3% | **51.9% / 4.6%** | **69.8% / 15.2%** |

- **The multi-stage leaf is WORSE than BOTH baselines at every depth** — below the single-net leaf
  AND far below the hand heuristic. The exact opposite of the hope. Multi-staging *helped* greedy
  play (T10, +19%) but *hurts* as a search leaf.
- **Why (the real lesson): multi-staging breaks the one thing search needs — a globally consistent
  value scale.** Greedy move choice compares only the 4 afterstates of the *current* board, which
  almost always sit in the *same* stage, so a per-stage net is fine (and specialises well → T10's
  +19%). But an expectimax leaf set spans *many* stages at once (deep lines that reach a higher
  tile cross a boundary), and each stage net is an *independent* function on its own scale — so
  comparing a stage-1 leaf against a stage-2 leaf is comparing apples to oranges. The boundary
  discontinuities mislead the search. (The starved high-stage nets — s1013's ≥3072 at 82k updates
  — make the deep leaves worse still.) A better greedy player is not a better search leaf; here it
  is actively a worse one.
- **This closes the learned-value-as-leaf line for good.** T3: single greedy net loses to the hand
  heuristic, gap widening with depth. T11: multi-staging it makes it worse. The hand-tuned heuristic
  remains the best expectimax leaf, and the project's strength is the **search** (deck-aware
  expectimax: 6144 @ 21%, 12288 @ 1.1%), not any learned value.

### N-tuple arc (T1–T11) — the settled conclusion for the paper
Across eleven experiments the learned N-tuple value function was pushed every way it can be:
more games (T7), more capacity (T8), leaf-alignment (T9), multi-staging for greedy (T10, the one
win: 23.5k→28k), and multi-staging as a search leaf (T11). Net finding: **greedy N-tuple caps
around 28k and never reaches the endgame (3072 ≈ 0%), and as an expectimax leaf a learned value —
single or multi-stage — never beats the hand heuristic.** For this deck-aware, high-variance 4×4
game, *search with a good hand heuristic* dominates *learned value*, both as a standalone policy
and as a leaf. That is the paper's spine; the RL baselines (DQN/PPO/AlphaZero, Phase 3) are the
final leg of the same comparison.

## 6. Deployment / records (Phase 4 — live web scoring)

The strong deck-aware expectimax (`cmd/moveserver`, depth-cap 5) driving real web
Threes end-to-end. Each driver reads the live board, asks the Go moveserver, presses
the arrow key, and records the game as a replay in the exact `engine/replay.go`
schema (plays in `web/replay.html`); `deploy/recorder.py` keeps only the best game.

| Site | Engine | Final score | Max tile | Moves | Player name |
|------|--------|------------:|---------:|------:|-------------|
| threesjs.io (Unity WebGL) | canvas colour+OCR, engine-in-the-loop | **62,403** | **1536** | 991 | Github halfrost |
| play.threesgame.com (WebGL) | localStorage slot.0 (exact board) | **200,142** | **3072** | 2034 | Github halfrost |
| **native iOS Threes on Apple-Silicon Mac** | screen vision + engine-trust tracking, MOUSE-drag driven | **30,285** | **768** | ~230 | in-app `Github halfrost` |

The two web sites went to a genuine game over ("Out of moves!"). For each we captured the site's own
**score-settlement screen** — threesjs.io shows `Your score: 62,403` on its Unity
game-over screen (a **1536** tile, 991 moves — `results/replays/threesjs/settlement_62403.png`);
play.threesgame.com flips every tile to its point value and
tallies **200,142** on its best game (a **3072** tile, 2034 moves —
`results/replays/threesgame/settlement_200142.png`; the WebGL buffer must be preserved
to screenshot it non-black, and the reveal only arms on a live game over). Getting that
clean high game needed two fixes to the headless supervisor: only keep a **natural**
game-over as "best" (a run that just exhausts its restart budget leaves a black/wedged
canvas at a mid-game score — this is how a raw 67,428 with no real settlement briefly
looked like the best), and a large restart budget (300) so a long ~2000-move game can
reach its real "Out of moves!" through the ~15-plies-per-wedge WebGL stalls. Replays +
settlement screenshots under `results/replays/{threesjs,threesgame}/` (gitignored).

**Scaling threesgame to the 240-core box** (chasing the 12288 = two 6144, a ~1.1% event even
at depth-6, so ~90 games are needed; `scripts/cloud_threesgame.sh`, depth-6, many parallel
headless sessions). The box has **no GPU**, so Chrome software-renders the WebGL through
SwiftShader — which surfaced three harness bugs, each fixed: (1) `_pkill_profile` matched the
supervisor's own `--profile` argv and SIGKILL'd itself the instant a session started (match
Chrome's `user-data-dir=` instead); (2) at 64 sessions the renderer starved — a pressed move
took longer than the driver's 3.6s "did it register?" poll, so *every* move looked un-registered
and the whole grind thrashed (1554 wedges, games capped at 1536); raising the poll to 40s and
cutting to 16 sessions fixed it (0 moves/30s → 215 moves/min); (3) a fresh game read before its
tiles spawned recorded a 0-move score=0 dud, burning the slot (now retried). After the fixes a
16-session run reached **197,775 / 3072** — real depth-6 play on a GPU-less box, matching the
Mac's 200,142/3072 — though 3072 is still only ~1 game in 15 there, so the 12288 hunt continues.

threesjs.io needed a different fix — one that took it from 9,993 to **62,403** (6x).
Its board is read by an engine-in-the-loop tracker that stays pixel-perfect (a per-move
engine-vs-full-OCR audit showed **0 mismatches**), yet depth-4 kept collapsing at a ~384
ceiling. The audit found the real culprit in the **next-tile preview**: a "3" preview
renders as an almost blank white card whose faint digit tesseract read as `-1` (=bonus)
**100 %** of the time — never once reading a 3. That silently told the deck-aware search a
bonus "+" was coming on ~⅓ of all turns (every 3) and desynced the `DeckTracker`, starving
the search of the one certain look-ahead it has. The preview is only ever 1/2/3/bonus
(never a high tile), so reading it by **colour** (red=1, blue=2, near-white card=3,
else bonus) instead of OCR fixed it: `nv=3` began appearing immediately and a single game
jumped to 20,769 / 768 — and a 12-game grind then hit **62,403 / 1536**, 6x the old record.
A reminder that a perfectly-tracked *board* can still be sabotaged
by a mis-read *hint*.

The **native iOS Threes app running on an Apple-Silicon Mac** is the third target and
the hardest — no DOM, no localStorage we could decode, an obfuscated + cfprefsd-cached
save file, and a window that ignores synthetic input in surprising ways. Best game so
far: **30,285, max tile 768** (`deploy/mac/driver.py`, moveserver depth-4 deck-aware),
captured on the app's own game-over settlement screen (`results/replays/mac/
settlement_30285.png`, gitignored). Clean start-to-finish replays at **7,701 / 384** and
**10,482 / 768** (`results/replays/mac_{clean,final}/best.json`). Two hard-won
mechanisms make it work:
- **Drive by MOUSE-DRAG, not arrow keys.** The app accepts synthetic *arrow keys* only
  while its window holds genuine keyboard first-responder — which a synthetic
  app-launch or menu-click never grants, so keys silently stop registering after an
  automated restart. But a synthetic **mouse drag** (a CGEvent with intermediate
  `MouseDragged` points) is honoured regardless of focus. So the driver plays *and*
  restarts entirely by mouse (drag to move; click `retry`/`PLAY THREES` to start over).
- **Engine-trust, spawn-only board reading.** We never glyph-read the high tiles
  (12/24/48/96/384 confuse a fixed-crop matcher, and 768 isn't even in the template
  library so it reads as 384). Instead `apply_move` computes every existing tile's
  value deterministically; the screen is read only to (a) confirm a move landed —
  wait for two identical consecutive colour grids so we never catch a mid-animation
  frame — and (b) place the single spawned tile, whose value is the `next` we
  previewed (a 1/2/3 by colour). Occupancy drift triggers a resync that keeps the
  engine's high-tile values and only re-reads low tiles from the screen. Result:
  `occ_mis = 0` across a whole game. Game-over is decided the real way — a completely
  full 16-tile board with no legal move — never by a failed input (the driver used to
  read the score-reveal / carousel as a drifted board and wander the menus; now it
  detects "left the board" via a uniform dark-panel probe + a whole-board occupancy jump).
- **Sign the leaderboard name IN-APP.** The Mac game-over shows a "SWIPE & SIGN YOUR
  NAME" card with a text field (default "Threeby"). Plain `osascript keystroke` /
  keycodes are ignored (same no-genuine-focus wall as the arrow keys), but a
  **CGEvent keyboard event with `CGEventKeyboardSetUnicodeString`** on the HID tap DOES
  land in the field. So the driver navigates to the sign card (swipe until a 4-point
  dark-panel probe fires), clears the default, types `Github halfrost`, **and presses
  Return (CGEvent) to COMMIT** — typing alone leaves the name blinking in the edit box,
  unsaved; Return flips it to the final settlement card (name in orange, no cursor,
  with retry/gamecenter/share). Earlier we wrongly concluded the name was an un-settable
  Game Center nickname — it is settable. Best signed+committed game: app **9,117**
  (`settlement_9117_signed.png`), name posted "Github halfrost".
- **Score-vs-replay caveat.** Games that stay short (max ≤192) track cleanly — the
  recorded replay score matches the app's to within one spawn (best fully-clean signed
  game: app **3,390** vs replay **3,381**, `occ_mis=0` all game — `results/replays/mac/
  {settlement_3390_signed.png, replay_3390_clean.json}`). Games that climb to 384/768
  develop endgame *value* drift (a 768 read as 384; alt-escape re-reads compound it),
  so the replay under-counts the real score (a **7,776** app score recorded as 2,283 —
  `settlement_7776_signed.png`). The settlement screenshot + signed name are always
  real; a *perfect high-score* replay is the remaining CV limit. So: the auto-signed,
  auto-captured, perfectly-replayed game is done end-to-end; pushing the *clean* score
  higher is the open item (all gitignored artifacts under `results/replays/mac/`).

Full blow-by-blow (every board-read method tried, the watchdog's evolution, and
the four bugs it surfaced) is in [`WEB_SCORING_WARSTORIES.md`](WEB_SCORING_WARSTORIES.md)
— raw material for the blog. The two headline findings:
- **Board is exact from localStorage, no vision needed.** `play.threesgame.com`
  (Threes.min.js) persists the live game to `localStorage["com.underscorediscovery/
  Threes/slot.0"]` every move — a haxe-serialized `Grid0..15`, `NextValue`,
  `NumMoves`, `InProgress`. Decoding it gives the exact board (all high tiles) with
  no OCR and no canvas capture. **Gotcha:** `Grid0..3` is the *bottom* screen row —
  read rows bottom-to-top or the board is vertically flipped, which silently inverts
  UP/DOWN and eventually strands the run (moveserver returns a move that's legal on
  the flipped board but a no-op in the game). Found via engine-vs-game legality diff.
- **The WebGL page wedges under automation; recover by killing, not waiting.**
  Repeatedly automating the animating WebGL page intermittently wedges the
  Chrome↔Playwright channel — an in-flight keypress/read blocks forever, and page
  timeouts, CDP timeouts, and SIGALRM all fail to interrupt the sync greenlet. The
  only reliable cure is to kill the whole process. `threesgame_supervisor.py` runs
  the driver on a persistent profile; on a heartbeat stall it SIGKILLs and relaunches
  — the game persisted itself to slot.0, so it resumes the exact in-progress board
  (a full replay is assembled from a JSONL move log across restarts). The 23,634 game
  took 47 relaunches through 22 wedges; 11/407 replay steps show a one-ply seam.

## 7. Theoretical maximum score (analysis, not an experiment)

How far is our record from the ceiling? The board is fixed at 16 cells, and — as the
question that prompted this puts it — **the bigger the tiles you accumulate, the more cells
they occupy and the sooner you jam**. That intuition has an exact form, derived below.
Two rule regimes are computed, because **our engine and the real game differ at the very top**
(see the divergence note at the end).

### 7.1 Scoring and the "3-unit" abstraction
`engine/score.go`: a board scores **`Σ 3^(index-2)`** over tiles of index ≥ 3, i.e. score is a
function of the **current board**, not of accumulated merge rewards. Tiles 1 and 2 score 0.

| index | 3 | 4 | … | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|
| value | 3 | 6 | … | 1536 | 3072 | 6144 | 12288 |
| score | 3 | 9 | … | 59,049 | 177,147 | 531,441 | **1,594,323** |

Write **`w = 2^(index-3)`** = how many 3s a tile contains (3 → w=1, 12288 → w=2¹²). Merging
conserves w, so w only ever concentrates. Since score = 3·w^log₂3 is *convex* in w,
concentration always pays — the maximum board is the one holding the largest tiles it can.

### 7.2 The space constraint (the formal version of "big tiles crowd the board")
Let **M(n)** = the largest w buildable with n free cells. To double a tile you must **park one
copy in a cell** and rebuild a second copy in what remains, then merge:

> **M(n) = 2·M(n−1)**

Base case = whatever a *single* free cell can receive from a spawn:
- **without bonus tiles**: the bag is four 1s / four 2s / four 3s, so a **3** can spawn directly → `M(1) = 2⁰`
- **with bonus tiles** (`engine/sim.go`: once max ≥ 48, p = 1/21, uniform over indices 4 … maxIndex−3):
  a tile of **maxValue/8** can spawn directly → `M(1) = 2^(maxIndex−3−3)`

Now order the final board's tiles largest-first. When the j-th is built, j−1 are already parked,
leaving 17−j cells:

> **w_j ≤ M(17−j)** ← this is exactly "each big tile you keep steals space from the next one"

### 7.3 Scenario 1 — 12288 does NOT end the game; play until the board jams
(This is what **our engine** implements: `Over()` only tests "no move changes the board".)

Extra constraint, and it is the binding one — a quirk of the 4-bit representation
(`engine/bitboard.go mergeVal`, mirrored in `gameboard.MakeMove`):

```go
if a == b && a >= 3 {
    if a != 15 { return a + 1, true }
    return 15, true          // two 12288s "merge" into ONE 12288 — a tile is destroyed
}
```

This **still changes the board**, so it is a legal move ⇒ on a *jammed* board **no two 12288s may
be adjacent**. The 4×4 grid graph is bipartite with parts 8/8 and has a perfect matching, so by
König its maximum independent set is **8** ⇒ **at most eight 12288s**.

**With bonus** (maxIndex = 15 ⇒ bonus up to index 12 = 1536 ⇒ M(1) = 2⁹, w capped at 2¹²):
`M(1)=2⁹, M(2)=2¹⁰, M(3)=2¹¹, M(n≥4)=2¹²`. So w_j = 2¹² for j ≤ 13 — but adjacency caps the
12288s at 8, and j=14/15/16 fall to 2¹¹/2¹⁰/2⁹:

```
board = {12288 ×8, 6144 ×6, 3072, 1536}
score = 8·3¹³ + 6·3¹² + 3¹¹ + 3¹⁰
      = 12,754,584 + 3,188,646 + 177,147 + 59,049
      = 16,179,426
```

```
12288  6144 12288  6144      the eight 12288s sit on one checkerboard colour class;
 3072 12288  6144 12288      the other class holds six 6144s, the 3072 and the 1536.
12288  6144 12288  6144      Verified with our own code: gameboard.MakeMove returns
 1536 12288  6144 12288      changeNum==0 in all four directions (genuinely jammed),
                             and engine.ScoreBB returns exactly 16,179,426.
```

**Without bonus** (M(1)=2⁰ ⇒ w_j = min(2^(16−j), 2¹²), so only j ≤ 4 reach 12288):

```
board = {12288 ×4, 6144, 3072, 1536, 768, 384, 192, 96, 48, 24, 12, 6, 3}
score = 4·3¹³ + Σ_{i=1..12} 3^i = 6,377,292 + 797,160 = 7,174,452
```

### 7.4 Scenario 2 — creating 12288 ends the game immediately (the REAL rule)
Then no 12288 can ever be *parked*: before the final merge the board's max is 6144 (index 14),
so bonus tops out at index 11 = 768 ⇒ **M(1) = 2⁸**, and w is capped at 2¹¹ (6144).
`M(1)=2⁸, M(2)=2⁹, M(3)=2¹⁰, M(n≥4)=2¹¹` ⇒ w_j = 2¹¹ for j ≤ 13, then 2¹⁰/2⁹/2⁸.

Note the board here need **not** be jammed — we *want* a legal merge — so the independent-set
constraint of §7.3 does not apply and 6144s may sit adjacent.

```
just before the last move:  {6144 ×13, 3072, 1536, 768}          (full board)
merge two adjacent 6144s →  12288 appears → GAME ENDS, points totalled as usual
final board:                {12288, 6144 ×11, 3072, 1536, 768}   (15 tiles)
score = 3¹³ + 11·3¹² + 3¹¹ + 3¹⁰ + 3⁹
      = 1,594,323 + 5,845,851 + 177,147 + 59,049 + 19,683
      = 7,696,053
```

**Without bonus** (M(1)=2⁰ ⇒ w_j = min(2^(16−j), 2¹¹), so j ≤ 5 reach 6144):

```
before:  {6144 ×5, 3072, 1536, 768, 384, 192, 96, 48, 24, 12, 6, 3}
final:   {12288, 6144 ×3, 3072, 1536, …, 3}
score = 3¹³ + 3·3¹² + Σ_{i=1..11} 3^i = 1,594,323 + 1,594,323 + 265,719 = 3,454,365
```

### 7.5 Results, and where we stand

| regime | bonus tiles | theoretical max | our record 2,161,704 is |
|---|---|---|---|
| **1 — no 12288 ending, play to jam** (our engine) | yes | **16,179,426** | 13.4% |
| 1 — same, ignoring bonus tiles | no | 7,174,452 | 30.1% |
| **2 — 12288 ends the game** (real game) | yes | **7,696,053** | **28.1%** |
| 2 — same, ignoring bonus tiles | no | 3,454,365 | 62.6% |

A single 12288 alone is worth 1,594,323 — so **one 12288 plus a decent board is already ~20–30%
of the ceiling**, which is why our 2,161,704 game (a 12288 with a 6144 still on the board) sits
where it does.

**These are UPPER BOUNDS, not achieved maxima.** §7.2's recursion bounds *space* only; it ignores
geometry (tiles slide whole lanes, you cannot place a tile in an arbitrary cell), the one-merge-
per-lane-per-move rule, and the astronomically small probability of the required spawn sequence
(the maximizing board's own last ply needs a 1/189 bonus spawn). Scenario 1's number was
cross-checked by three independent derivations plus adversarial verification, including a proof
that the tempting `{12288 ×8, 6144 ×7, 1536}` (16,533,720) is genuinely **infeasible**: creating a
15th index-≥14 tile would require 17 simultaneously-occupied cells. Scenario 2 is derived the same
way but has not had the same adversarial treatment.

### 7.6 ⚠️ Our engine diverges from the real game at the very top
Confirmed from public sources — the real game **ends the instant 12288 is created**:

> "There is also a 13th character that is unlocked when two 6,144 tiles are combined; this
> character is marked by a triangle rather than the number 12,288. **When this character is
> revealed, the game ends immediately even if the player has moves available, and points are
> totaled as usual.**" — [Wikipedia](https://en.wikipedia.org/wiki/Threes)
> (see also [AV Club, "Hold the phone—Threes! has an ending?"](https://www.avclub.com/hold-the-phone-threes-has-an-ending-1798263214))

So **12288 is the mathematical end of the game — there is no 24576** — and there is **no documented
score cap**; the ceiling is entirely implied by that ending rule.

| | real game | our `engine/` |
|---|---|---|
| a 12288 is created | game ends immediately | keeps playing until jammed |
| two 12288s adjacent | cannot happen | "merge" into one, destroying 1,594,323 points |

The 4-bit ceiling is not unique to us — [nneonneo's Threes AI](https://github.com/nneonneo/threes-ai/blob/master/threes.h) has the identical limit
(*"The maximum possible board value that can be supported is 12288 (=15) … The highest tile in
the game appears to be 6144"*), and its `INITIAL_DECK (0x00040404) // four of each` and
`HIGH_CARD_FREQ 21` match our bag and 1/21 bonus rate exactly — so our **generation** rules are
right; only the **terminal** rule differs.

**Impact on our numbers (not yet corrected):** in the ~1.1% of games that reach 12288, our engine
keeps playing afterwards, so those games' scores may be **inflated** relative to the real game,
which would have stopped at that instant. Everything below 12288 is unaffected, and our web
deployments independently validate the scoring (engine score == on-screen score, desync 0, up to
3072 tiles and 200k points). Fixing this would change the depth-5..9 headline numbers, so it is
recorded here rather than silently patched.
