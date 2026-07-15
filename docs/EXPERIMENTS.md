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

### ★ Learning-curve comparison (T1 vs T2 vs T4) — the phase transition
> Consolidated view of the three greedy-eval curves (mean of 1000 held-out games,
> sampled every 100–500k training games). Interactive figure (hover for any point,
> both themes): **https://claude.ai/code/artifact/8ef3aedc-1ae2-4e62-9ecb-5567fe477049**
> — regenerate from the logs with `scripts/learning_curve.py`.

| run | tuples | α schedule | TC | games | peak mean | final mean | phase jump? |
|---|---|---|---|---|---:|---:|---|
| **T1** | small 4×4 (~1 MB) | const 0.1 | no | 5M | 10,709 | 9,868 | no — capacity-capped ≈10k |
| **T2** | big 4×6 (~270 MB) | const 0.1 | no | 10M | **21,371** | 20,968 | **yes, near 4M games** |
| **T4** | big2 8×6 (~540 MB) | 0.1→0.01 anneal | yes | 15M | 9,809 | 9,608 | no — smooth crawl, never jumps |

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

### T6 — big2 + constant α (complete the 2×2) — ★ RUNNING (machine 01)
`scripts/train_big2.sh` → `models/ntuple_big2.gob`, 15M games, big2, constant
α=0.1 (T2's recipe with big2's capacity). Fourth cell of the design
(big/big2 × const-α/TC+anneal); T4 vs T6 isolates whether TC+anneal hurt, T2 vs T6
isolates whether big2 is just under-trained. **Launched on machine 01** (freed after
T4). Expected reads: if T6 clears ~21k → TC+anneal was the culprit in T4; if T6 also
stalls near ~10k → big2's 2× weights are just badly under-trained at 15M. Fetch the
`.gob` + `train_big2.log` from `cloud-results` when done (no-overwrite), then curve
it vs T2/T4 with `scripts/learning_curve.py`.

_Planned later: DQN / PPO / AlphaZero-style baselines (Phase 3, needs a GPU box)._

## 6. Deployment / records (Phase 4 — live web scoring)

The strong deck-aware expectimax (`cmd/moveserver`, depth-cap 5) driving real web
Threes end-to-end. Each driver reads the live board, asks the Go moveserver, presses
the arrow key, and records the game as a replay in the exact `engine/replay.go`
schema (plays in `web/replay.html`); `deploy/recorder.py` keeps only the best game.

| Site | Engine | Final score | Max tile | Moves | Player name |
|------|--------|------------:|---------:|------:|-------------|
| threesjs.io (Unity WebGL) | canvas colour+OCR, engine-in-the-loop | **9,993** | 384 | 431 | Github halfrost |
| play.threesgame.com (WebGL) | localStorage slot.0 (exact board) | **23,634** | 768 | 407 | Github halfrost |
| **native iOS Threes on Apple-Silicon Mac** | screen vision + engine-trust tracking, MOUSE-drag driven | **30,285** | **768** | ~230 | in-app `Github halfrost` |

The two web sites went to a genuine game over ("Out of moves!"). For each we captured the site's own
**score-settlement screen** — threesjs.io shows `Your score: 9,993` on its Unity
game-over screen; play.threesgame.com flips every tile to its point value and
tallies `23,634` (the WebGL buffer must be preserved to screenshot it non-black,
and the reveal only arms on a live game over). Replays + these settlement
screenshots under `results/replays/{threesjs,threesgame}/` (gitignored artifacts).

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
  dark-panel probe fires), clears the default, and types `Github halfrost`. Earlier we
  wrongly concluded the name was an un-settable Game Center nickname — it is settable.
- **Score-vs-replay caveat.** Games that stay short (max ≤192) track cleanly — the
  recorded replay score matches the app's (e.g. **2,823** tracked ≈ 2,820). Games that
  climb to 384/768 develop endgame *value* drift (a 768 read as 384; alt-escape
  re-reads compound it), so the replay under-counts the real score (a **7,776** app
  score recorded as 2,283). The settlement screenshot + signed name are always real;
  a *perfect* high-score replay is the remaining CV limit. Signed settlement shots:
  `results/replays/mac/settlement_{7776,30285}_signed.png` (gitignored).

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
