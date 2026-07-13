"""AlphaZero-style baseline for Threes (Phase 3 comparison), adapted for a
single-player STOCHASTIC game.

Standard AlphaZero targets deterministic two-player games. Threes needs two
changes: (1) decision nodes choose a swipe via PUCT over the policy net; (2)
chance nodes model the random tile spawn — here sampled one outcome per
simulation (a stochastic / sampled MCTS). Leaves are evaluated by a policy+value
net; self-play produces (state, visit-distribution, return) targets.

This is the heaviest and most experimental baseline — a runnable skeleton to be
tuned, included for completeness of the search-vs-learning comparison.

Run:  python alphazero.py --iters 200
"""
import argparse
import math

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from threes_env import ThreesEnv, encode, apply_move, score


class PVNet(nn.Module):
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
        return F.log_softmax(self.pi(x), dim=-1), torch.tanh(self.v(x)).squeeze(-1)


def net_eval(net, device, env):
    with torch.no_grad():
        logp, v = net(torch.from_numpy(encode(env.board, env.next)[None]).to(device))
    return np.exp(logp[0].cpu().numpy()), float(v.item())


class Node:
    __slots__ = ("P", "N", "W", "children", "legal")

    def __init__(self, prior_legal):
        self.legal = prior_legal
        self.P = {a: p for a, p in prior_legal}
        self.N = {a: 0 for a, _ in prior_legal}
        self.W = {a: 0.0 for a, _ in prior_legal}
        self.children = {}


def mcts(net, device, env, sims=64, c_puct=1.5):
    """Run a sampled stochastic MCTS from the current env state; return visit
    counts over the 4 actions (the improved policy)."""
    p, _ = net_eval(net, device, env)
    legal = env.legal_actions()
    if not legal:
        return np.zeros(4)
    root = Node([(a, p[a]) for a in legal])
    for _ in range(sims):
        _simulate(net, device, env, root, c_puct)
    visits = np.zeros(4)
    for a in legal:
        visits[a] = root.N[a]
    return visits


def _simulate(net, device, env, node, c_puct, depth=0):
    if depth > 40 or not node.legal:
        return 0.0
    total = sum(node.N.values()) + 1
    best_a, best_u = None, -1e18
    for a, _ in node.legal:
        q = node.W[a] / node.N[a] if node.N[a] > 0 else 0.0
        u = q + c_puct * node.P[a] * math.sqrt(total) / (1 + node.N[a])
        if u > best_u:
            best_u, best_a = u, a
    # apply move + reward, then sample a chance outcome (spawn)
    nb, changed, _ = apply_move(env.board, best_a)
    reward = score(nb) - score(env.board)
    child_env = ThreesEnv()
    child_env.rng = env.rng
    child_env.board = nb
    li = env.rng.choice([i for i in range(4) if changed[i]])
    r, c = {0: (3, li), 1: (0, li), 2: (li, 3), 3: (li, 0)}[best_a]
    child_env.board[r][c] = child_env._draw_bag() if not False else child_env.next
    child_env.next, child_env.next_bonus = child_env._gen_tile()

    if best_a not in node.children:
        p, v = net_eval(net, device, child_env)
        cl = child_env.legal_actions()
        node.children[best_a] = Node([(a, p[a]) for a in cl]) if cl else None
        value = reward + v
    else:
        value = reward + _simulate(net, device, child_env, node.children[best_a], c_puct, depth + 1) \
            if node.children[best_a] is not None else reward
    node.N[best_a] += 1
    node.W[best_a] += value
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--games-per-iter", type=int, default=32)
    ap.add_argument("--sims", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--out", default="models/alphazero.pt")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = PVNet().to(device)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    seed = 10_000_000

    for it in range(1, args.iters + 1):
        data = []  # (obs, pi, z)
        scores = []
        for _ in range(args.games_per_iter):
            env = ThreesEnv(); env.reset(seed=seed); seed += 1
            traj = []
            while env.legal_actions():
                visits = mcts(net, device, env, args.sims)
                if visits.sum() == 0:
                    break
                pi = visits / visits.sum()
                traj.append((encode(env.board, env.next), pi))
                env.step(int(np.random.choice(4, p=pi)))
            z = math.tanh(env.score() / 1e6)   # crude value target scaling
            for obs, pi in traj:
                data.append((obs, pi, z))
            scores.append(env.score())

        if data:
            obs = torch.from_numpy(np.stack([d[0] for d in data])).to(device)
            pi = torch.from_numpy(np.stack([d[1] for d in data]).astype(np.float32)).to(device)
            z = torch.tensor([d[2] for d in data], dtype=torch.float32, device=device)
            logp, v = net(obs)
            loss = -(pi * logp).sum(1).mean() + F.mse_loss(v, z)
            opt.zero_grad(); loss.backward(); opt.step()

        print(f"[iter {it:4d}] games={len(scores)} mean_score={sum(scores)/len(scores):.0f} "
              f"max={max(scores)} loss={loss.item():.4f}", flush=True)
        import os
        os.makedirs("models", exist_ok=True)
        torch.save(net.state_dict(), args.out)


if __name__ == "__main__":
    main()
