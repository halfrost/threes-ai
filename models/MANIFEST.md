# N-tuple checkpoint archive — the authoritative, stable home

Every `cloud-result*` branch is **force-pushed** (reflog shows cloud-result2 forced 4x,
cloud-results 3x), so anything living only there can vanish. It already did: T2's 10M
checkpoint was overwritten on cloud-result2 when T7 resumed **in place** and pushed a
different net under the same `models/ntuple_big.gob` name — for a while the sole copy in
existence was one laptop's working tree. Hence this branch: stable, never force-pushed,
one unambiguous filename per experiment.

| file | bytes | experiment | greedy mean (seeds 1..1000) |
|---|---|---|---|
| `ntuple_t1_small_5m.gob` | 394,113 | T1 — small 4x4, 5M games, a=0.1 | ~9.9k (capacity-limited) |
| `ntuple_t2_big_10m.gob` | 64,512,541 | T2 — big 4x6, 10M games, const a=0.1 | **20,968** |
| `ntuple_t4_big2_tc_15m.gob` | 94,136,981 | T4 — big2 8x6, 15M, TC + a anneal | ~9.6k (regressed) |
| `ntuple_t5_big_tc_15m.gob` | 60,022,301 | T5 — big 4x6, 15M, TC + a anneal | ~16k |
| `ntuple_t6_big2_15m.gob` | 117,275,545 | T6 — big2 8x6, 15M, const a | ~17k (under-trained) |
| `ntuple_t7_big_30m.gob` | 72,702,310 | T7 — T2 resumed +20M (30M total), const a | **23,507** |

Numbers and verdicts: `docs/EXPERIMENTS.md` section 5. Headline: T7's curve FLATTENED
(peak 24,788, ends 23,507) — `big` is at its capacity ceiling, do not resume it again.

## Do not trust `git show` to verify these
LFS stores a ~133-byte pointer in the tree; `git show <branch>:<file>` prints **the
pointer**, not the model. Overwriting a real file with that output destroys it (learned
the hard way). To verify an archive, do a real clone and check the byte size:

    git clone --branch archive/ntuple-checkpoints --single-branch --depth 1 \
      https://github.com/halfrost/threes-ai.git /tmp/chk
    ls -la /tmp/chk/models/

## Same-name hazard
`models/ntuple_big.gob` means **T2's 10M** on some machines and **T7's 30M** on others
(T7 resumed in place). Always check the byte size — 64,512,541 = T2, 72,702,310 = T7.
`scripts/train_leaf_aligned.sh` prints which base it loaded for exactly this reason.
