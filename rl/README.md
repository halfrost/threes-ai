# RL baselines (Phase 3)

Deep-RL **comparison baselines** for the paper — DQN, PPO, and an AlphaZero-style
stochastic MCTS. They are *not* the main method; they exist to show how deep RL
stacks up against the search + N-tuple main line (the expected take-away: on a
4×4 discrete stochastic puzzle, search + a learned value function is the
higher-value route, while these need far more compute for less).

## Files
- `threes_env.py` — faithful, pure-Python Threes environment (Gym-style). No hard
  numpy dependency in the core; `encode()` (numpy) produces the (17,4,4) tensor
  the nets consume. Run `python threes_env.py` for a random-policy self-check.
- `dqn.py` — conv Q-net + replay + target net, epsilon-greedy masked to legal moves.
- `ppo.py` — conv actor-critic, GAE, clipped PPO objective, masked policy.
- `alphazero.py` — policy+value net + sampled stochastic MCTS (decision nodes via
  PUCT, chance nodes sampled), self-play targets. The heaviest / most experimental.

These are **runnable skeletons to be tuned**, not finished agents.

## Setup & run
```bash
pip install -r requirements.txt
python dqn.py --episodes 20000
python ppo.py --updates 5000
python alphazero.py --iters 200
```
Trained weights are checkpointed under `models/`.

## Important consistency notes
- **Same seeds protocol** (see docs/EXPERIMENTS.md): training uses seeds from
  10_000_000+; evaluation uses the fixed held-out set (seeds 1..N), the SAME set
  every agent (and the Go search/N-tuple agents) reports on.
- **Engine parity** (done — keep it green): `bash scripts/rl_parity.sh` proves
  `threes_env.py` reproduces the Go engine exactly. The Go `cmd/paritydump` emits
  random games as event streams; `parity_check.py` replays each move and
  force-places the recorded spawn, asserting board+score match cell-for-cell
  (RNG-independent). Re-run after any change to the move/merge/score logic on
  either side. For final paper numbers you can additionally export a trained
  policy and score it through the Go `cmd/bench` harness so every agent is
  measured on the *identical* environment.
- **No GPU on the cloud box**: these nets train much faster on a GPU. On the
  CPU-only 240-core machine they will be the slow part of the project — plan
  accordingly (smaller nets / fewer iterations, or a separate GPU box).
