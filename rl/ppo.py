"""PPO baseline for Threes (Phase 3 comparison).

A policy-gradient deep RL baseline: a shared conv trunk with policy (4 logits) and
value heads, on-policy rollouts, GAE advantages, and the clipped PPO objective.
Illegal actions are masked in the policy. Runnable skeleton to be tuned.

Run:  python ppo.py --updates 5000
"""
import argparse

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from threes_env import ThreesEnv, encode

# Rewards are divided by this before learning. Threes score deltas run 3..3^13, so raw
# returns reach 1e4-1e5; with a SHARED trunk the value loss (MSE on those returns) is
# ~1e8-1e10 against a policy term of O(1), i.e. essentially 100% of the gradient reaching
# the trunk is value-head gradient and the clipped policy objective does nothing. Learning
# on normalised returns keeps both terms comparable. Same constant as distill/alphazero.
VALUE_SCALE = 200_000.0


class ACNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1 = nn.Conv2d(17, 128, 2)
        self.c2 = nn.Conv2d(128, 128, 2)
        self.fc = nn.Linear(128 * 2 * 2, 256)
        self.pi = nn.Linear(256, 4)
        self.v = nn.Linear(256, 1)

    def forward(self, x):
        x = F.relu(self.c1(x))
        x = F.relu(self.c2(x))
        x = F.relu(self.fc(x.flatten(1)))
        return self.pi(x), self.v(x).squeeze(-1)


def masked_logits(logits, legal_mask):
    return logits + legal_mask  # legal_mask: 0 for legal, -1e9 for illegal


def collect(net, device, steps, seed0):
    """Roll out `steps` transitions across games; returns tensors + episode stats."""
    env = ThreesEnv()
    S, A, LOGP, R, V, M, DONE = [], [], [], [], [], [], []
    ep_scores = []
    g = seed0
    env.reset(seed=g)
    for _ in range(steps):
        legal = env.legal_actions()
        if not legal:
            ep_scores.append(env.score())
            g += 1
            env.reset(seed=g)
            legal = env.legal_actions()
        s = encode(env.board, env.next)
        mask = np.full(4, -1e9, dtype=np.float32)
        mask[legal] = 0.0
        with torch.no_grad():
            logits, val = net(torch.from_numpy(s[None]).to(device))
            logits = masked_logits(logits, torch.from_numpy(mask[None]).to(device))
            dist = torch.distributions.Categorical(logits=logits)
            a = dist.sample()
            logp = dist.log_prob(a)
        _, r, done, _ = env.step(int(a.item()))
        S.append(s); A.append(int(a.item())); LOGP.append(float(logp.item()))
        R.append(r / VALUE_SCALE)   # learn on normalised returns (see VALUE_SCALE)
        V.append(float(val.item())); M.append(mask); DONE.append(float(done))
        if done:
            ep_scores.append(env.score())
            g += 1
            env.reset(seed=g)
    # Bootstrap value of the state the rollout STOPPED in (it is almost never terminal).
    # Without it GAE treats every truncation as a game over and biases the whole tail.
    with torch.no_grad():
        legal = env.legal_actions()
        if legal:
            bs = encode(env.board, env.next)
            _, bv = net(torch.from_numpy(bs[None]).to(device))
            boot = float(bv.item())
        else:
            boot = 0.0
    return (np.stack(S), np.array(A), np.array(LOGP, dtype=np.float32),
            np.array(R, dtype=np.float32), np.array(V, dtype=np.float32),
            np.stack(M), np.array(DONE, dtype=np.float32)), ep_scores, g, boot


def gae(rewards, values, dones, bootstrap=0.0, gamma=0.999, lam=0.95):
    """GAE(lambda). `bootstrap` is V(s_T) for the state the rollout was CUT at — using 0
    there would tell the learner every truncated episode ended in death."""
    adv = np.zeros_like(rewards)
    last = 0.0
    for t in reversed(range(len(rewards))):
        nonterm = 1.0 - dones[t]
        nextv = values[t + 1] if t + 1 < len(values) else bootstrap
        delta = rewards[t] + gamma * nextv * nonterm - values[t]
        last = delta + gamma * lam * nonterm * last
        adv[t] = last
    return adv, adv + values


def evaluate(net, device, n=1000, max_moves=20000):
    """Greedy play on the FIXED held-out seeds 1..n — the project's evaluation protocol
    (docs/EXPERIMENTS.md): never report training-rollout scores, and never sample here.
    The rollout scores in the training loop come from the stochastic exploration policy on
    TRAINING seeds and are length-biased (only episodes finishing inside the window get
    counted), so they are a progress trace, not a number to put in the paper."""
    scores = []
    env = ThreesEnv()
    for g in range(1, n + 1):
        env.reset(seed=g)
        while env.moves < max_moves:
            legal = env.legal_actions()
            if not legal:
                break
            mask = np.full(4, -1e9, dtype=np.float32)
            mask[legal] = 0.0
            with torch.no_grad():
                logits, _ = net(torch.from_numpy(encode(env.board, env.next)[None]).to(device))
                logits = masked_logits(logits, torch.from_numpy(mask[None]).to(device))
            env.step(int(logits[0].argmax().item()))
        scores.append(env.score())
    scores.sort()
    return sum(scores) / len(scores), scores[len(scores) // 2], scores[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--updates", type=int, default=5000)
    ap.add_argument("--rollout", type=int, default=4096)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--out", default="models/ppo.pt")
    ap.add_argument("--eval-every", type=int, default=200, help="updates between held-out evals")
    ap.add_argument("--eval-n", type=int, default=200, help="held-out eval games (seeds 1..N)")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = ACNet().to(device)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    seed = 10_000_000  # train seeds disjoint from eval (1..N)

    for upd in range(1, args.updates + 1):
        (S, A, LOGP, R, V, M, D), ep_scores, seed, boot = collect(net, device, args.rollout, seed)
        adv, ret = gae(R, V, D, bootstrap=boot)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        S = torch.from_numpy(S).to(device); A = torch.from_numpy(A).to(device)
        LOGP = torch.from_numpy(LOGP).to(device); M = torch.from_numpy(M).to(device)
        adv = torch.from_numpy(adv).to(device); ret = torch.from_numpy(ret).to(device)

        idx = np.arange(len(A))
        for _ in range(args.epochs):
            np.random.shuffle(idx)
            for b in range(0, len(idx), args.batch):
                j = idx[b:b + args.batch]
                logits, val = net(S[j])
                dist = torch.distributions.Categorical(logits=masked_logits(logits, M[j]))
                ratio = torch.exp(dist.log_prob(A[j]) - LOGP[j])
                s1 = ratio * adv[j]
                s2 = torch.clamp(ratio, 1 - args.clip, 1 + args.clip) * adv[j]
                pol = -torch.min(s1, s2).mean()
                vloss = F.mse_loss(val, ret[j])
                ent = dist.entropy().mean()
                loss = pol + 0.5 * vloss - 0.01 * ent
                opt.zero_grad(); loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()

        if ep_scores and upd % 20 == 0:
            import os
            # NOTE: a training-progress trace only (stochastic policy, training seeds,
            # length-biased). The number for the paper is the held-out eval below.
            print(f"[update {upd:5d}] train_rollout episodes={len(ep_scores)} "
                  f"mean={sum(ep_scores)/len(ep_scores):.0f} max={max(ep_scores)}", flush=True)
            os.makedirs("models", exist_ok=True)
            torch.save(net.state_dict(), args.out)

        if upd % args.eval_every == 0:
            mean, med, mx = evaluate(net, device, n=args.eval_n)
            print(f"[update {upd:5d}] HELD-OUT eval(seeds 1..{args.eval_n}): "
                  f"mean={mean:.0f} median={med} max={mx}", flush=True)


if __name__ == "__main__":
    main()
