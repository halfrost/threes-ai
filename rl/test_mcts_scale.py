"""证明尺度修复有效：修复前搜索塌缩成 one-hot，修复后访问分布分散。
不需要 torch —— 只取 alphazero 的纯 Python MCTS 部分。"""
import sys, math, random, types
sys.path.insert(0, '.')
# 打桩 torch，让 alphazero 能被 import（我们只用它的纯 Python 部分）
fake = types.ModuleType('torch')
fake.nn = types.ModuleType('torch.nn'); fake.nn.Module = object
fake.nn.functional = types.ModuleType('torch.nn.functional')
fake.nn.Conv2d = fake.nn.Linear = lambda *a, **k: None
fake.no_grad = lambda: types.SimpleNamespace(__enter__=lambda s: None, __exit__=lambda s,*a: None)
sys.modules['torch'] = fake; sys.modules['torch.nn'] = fake.nn
sys.modules['torch.nn.functional'] = fake.nn.functional
import numpy as np
import alphazero as az
from threes_env import ThreesEnv

def run(scaled, sims=64, games=12, c_puct=1.5):
    """scaled=True 用修复后的 _backup；False 复刻修复前 (v = r + v)"""
    orig = az._backup
    if not scaled:
        def old_backup(path, leaf_value):
            v = leaf_value
            for node, a, r in reversed(path):
                v = r + v                      # ← 修复前：原始分数
                node.N[a] += 1; node.W[a] += v
        az._backup = old_backup
    onehot = 0; spreads = []
    for g in range(games):
        env = ThreesEnv(); env.reset(seed=1000+g)
        for _ in range(6):                     # 每局看前几步
            legal = env.legal_actions()
            if not legal: break
            pri = np.ones(len(legal))/len(legal)
            root = az.Node(list(zip(legal, pri)))
            for s in range(sims):
                rng = random.Random(g*10007 + s)
                path, leaf = az._descend(root, env, c_puct, rng)
                az._backup(path, 0.3 if leaf is not None else 0.0)
            visits = np.array([root.N.get(a,0) for a in range(4)], float)
            if visits.sum() == 0: break
            pi = visits/visits.sum()
            spreads.append((pi>0.01).sum())    # 有多少动作被真正探索
            if pi.max() > 0.98: onehot += 1
            env.step(int(pi.argmax()))
    az._backup = orig
    return onehot, len(spreads), sum(spreads)/max(len(spreads),1)

print("=== 修复前 (v = r + v，原始分数) ===")
oh, n, avg = run(scaled=False)
print(f"  one-hot 塌缩: {oh}/{n} 步 ({100*oh/max(n,1):.0f}%) | 平均探索动作数 {avg:.2f}/4")
print()
print("=== 修复后 (v = r/VALUE_SCALE + v) ===")
oh2, n2, avg2 = run(scaled=True)
print(f"  one-hot 塌缩: {oh2}/{n2} 步 ({100*oh2/max(n2,1):.0f}%) | 平均探索动作数 {avg2:.2f}/4")
print()
print("判定:", "✅ 修复生效 —— 搜索不再塌缩" if oh2 < n2*0.5 and avg2 > avg else "⚠️ 仍有问题")
