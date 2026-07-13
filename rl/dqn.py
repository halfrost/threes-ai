"""DQN baseline for Threes (Phase 3 comparison).

A standard value-based deep RL baseline: a conv Q-network over the (17,4,4)
observation, experience replay, a target network, and epsilon-greedy behaviour
masked to legal actions. This is a runnable skeleton to be tuned, not a finished
agent — the point of Phase 3 is to compare deep RL against the search + N-tuple
main line, and DQN is the simplest such baseline.

Run:  python dqn.py --episodes 20000
"""
import argparse
import random
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from threes_env import ThreesEnv, encode


class QNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1 = nn.Conv2d(17, 128, 2)   # 4x4 -> 3x3
        self.c2 = nn.Conv2d(128, 128, 2)  # 3x3 -> 2x2
        self.fc1 = nn.Linear(128 * 2 * 2, 256)
        self.fc2 = nn.Linear(256, 4)

    def forward(self, x):
        x = F.relu(self.c1(x))
        x = F.relu(self.c2(x))
        x = F.relu(self.fc1(x.flatten(1)))
        return self.fc2(x)


class Replay:
    def __init__(self, cap=200_000):
        self.buf = deque(maxlen=cap)

    def push(self, *t):
        self.buf.append(t)

    def sample(self, n):
        batch = random.sample(self.buf, n)
        s, a, r, s2, legal2, done = zip(*batch)
        return (np.stack(s), np.array(a), np.array(r, dtype=np.float32),
                np.stack(s2), np.stack(legal2), np.array(done, dtype=np.float32))

    def __len__(self):
        return len(self.buf)


def legal_mask(env):
    m = np.full(4, -1e9, dtype=np.float32)
    for a in env.legal_actions():
        m[a] = 0.0
    return m


def evaluate(q, device, n=200):
    env = ThreesEnv()
    scores = []
    for g in range(n):
        env.reset(seed=g + 1)
        while True:
            legal = env.legal_actions()
            if not legal:
                break
            with torch.no_grad():
                qv = q(torch.from_numpy(encode(env.board, env.next)[None]).to(device))[0].cpu().numpy()
            qv[[a for a in range(4) if a not in legal]] = -1e9
            env.step(int(qv.argmax()))
        scores.append(env.score())
    scores.sort()
    return sum(scores) / n, scores[n // 2], max(scores)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=20000)
    ap.add_argument("--gamma", type=float, default=0.99)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--eps-end", type=float, default=0.02)
    ap.add_argument("--eps-decay", type=int, default=100_000)
    ap.add_argument("--target-sync", type=int, default=2000)
    ap.add_argument("--eval-every", type=int, default=2000)
    ap.add_argument("--out", default="models/dqn.pt")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    q, tgt = QNet().to(device), QNet().to(device)
    tgt.load_state_dict(q.state_dict())
    opt = torch.optim.Adam(q.parameters(), lr=args.lr)
    replay = Replay()
    env = ThreesEnv()
    steps = 0

    for ep in range(1, args.episodes + 1):
        env.reset(seed=10_000_000 + ep)   # train seeds disjoint from eval (1..N)
        while True:
            legal = env.legal_actions()
            if not legal:
                break
            eps = max(args.eps_end, 1.0 - steps / args.eps_decay)
            s = encode(env.board, env.next)
            if random.random() < eps:
                a = random.choice(legal)
            else:
                with torch.no_grad():
                    qv = q(torch.from_numpy(s[None]).to(device))[0].cpu().numpy()
                qv[[x for x in range(4) if x not in legal]] = -1e9
                a = int(qv.argmax())
            _, r, done, _ = env.step(a)
            s2 = encode(env.board, env.next)
            replay.push(s, a, r, s2, legal_mask(env), float(done))
            steps += 1

            if len(replay) >= args.batch:
                s_b, a_b, r_b, s2_b, m2_b, d_b = replay.sample(args.batch)
                s_b = torch.from_numpy(s_b).to(device)
                s2_b = torch.from_numpy(s2_b).to(device)
                with torch.no_grad():
                    q2 = tgt(s2_b).cpu().numpy() + m2_b       # mask illegal next actions
                    target = r_b + args.gamma * (1 - d_b) * q2.max(1)
                    target = torch.from_numpy(target).to(device)
                qa = q(s_b).gather(1, torch.from_numpy(a_b).to(device)[:, None]).squeeze(1)
                loss = F.smooth_l1_loss(qa, target)
                opt.zero_grad(); loss.backward(); opt.step()
                if steps % args.target_sync == 0:
                    tgt.load_state_dict(q.state_dict())
            if done:
                break

        if ep % args.eval_every == 0:
            mean, med, mx = evaluate(q, device)
            print(f"[ep {ep:6d} | {steps:8d} steps | eps {eps:.3f}] eval mean={mean:.0f} median={med} max={mx}", flush=True)
            import os
            os.makedirs("models", exist_ok=True)
            torch.save(q.state_dict(), args.out)


if __name__ == "__main__":
    main()
