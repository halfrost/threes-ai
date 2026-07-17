# T7 checkpoint — `big` (4x6) N-tuple, constant alpha, 30M games

`ntuple_big_t7_30m.gob` (72,702,310 bytes) — the archived result of T7
(`scripts/train_big_resume.sh`): T2's 10M checkpoint resumed for +20M games on
fresh seeds 20M-40M, alpha=0.1 constant, 41,674 s on the 240-core box.

Eval on the fixed held-out set (seeds 1..1000): **mean 23,507**, median 22,806,
3072 = 0.0%, 6144 = 0.0%.

Why it is archived under this name: T7 wrote *in place* over
`models/ntuple_big.gob`, which elsewhere means T2's 10M net (64,512,541 bytes,
mean 20,968). Two different nets, one default filename — so the 30M one gets an
unambiguous name here. T2's 10M remains on `origin/cloud-result2` as
`models/ntuple_big.gob`.

Read the verdict before spending compute on it: T7's curve FLATTENED (peak 24,788
at 20.5M cumulative, ending *below* that at 23,507) — `big` is at its capacity
ceiling and must not be resumed again. See docs/EXPERIMENTS.md section 5 (T7/T3).
