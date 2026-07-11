# Threes-AI 项目计划 (Project Plan)

> 目标：做一个强 Threes AI，在三个平台刷到顶尖分数；产出一篇 blog；产出一篇可发 arXiv 的 paper。
> 本文档是项目的权威规划，随进度更新。最后更新：2026-07-10。

---

## 0. 项目目标（已校准）

### 三大目标
1. **三榜刷分**（进入顶尖梯队 / 逼近记录）
   - http://play.threesgame.com/ （官方 web）
   - https://threesjs.io/ （JS clone，有全球排行榜）
   - Android 上的 Threes app
2. **Blog**：全程记录问题→算法→工程→ML→实战。
3. **Paper**：可发 arXiv 的系统性对比研究（cs.AI / cs.LG），并在 LinkedIn 等社交平台发布。

### 量化指标（North Star，已现实校准）
> 依据：2016 MS-TD SOTA 在 Threes 上达到 6144 的概率仅 **7.83%**（普通 TD 仅 0.45%，arXiv:1606.07374）；
> 12288 = 两个 6144 合并 = 游戏立即结束（史上极少数人/bot 做到），**不可能 100%**。

- **P1（必达）**：稳定拿到 6144，把命中率显著推高（目标 ≥ 30%，超过 2016 SOTA 即为可发表结论）。
- **P2（冲刺）**：至少复现一次 **12288**（做到一次 = 里程碑，blog 头条 + paper highlight + LinkedIn 爆点）。
- **P3（落地）**：三个榜单进入顶尖梯队 / 逼近记录（已知最强 AI 演示为 6144 tile / 736,254 分）。

> ⚠️「100% 合成 12288」已从目标中删除（不现实）。

---

## 1. 技术主线与架构

### 主线（production bot）
```
Deck-Aware Expectimax
  + N-Tuple TD value function (afterstate, multi-stage TD)
  + Transposition Table
  + Optional Beam Search (仅在 chance node 分支过大时近似加速)
```
- **核心 novelty**：Deck-Aware —— 精确追踪牌袋(bag)状态 + 利用 next-tile preview。这是 Threes 区别于 2048、且学术界几乎没系统做过的点。可量化「知道下一张牌值多少分」的 ablation。

### 对照组（research comparison，完整做）
- **DQN**：Q(s,a)，4 个动作，作为 RL baseline。
- **PPO**：policy/value，on-policy baseline。
- **AlphaZero-style stochastic MCTS**：policy/value net + chance-node MCTS（非标准双人 AlphaZero，需改成随机单人版）。
- 目的：证明「传统搜索 + 学习价值函数」在这类游戏仍是性价比之王，并支撑一篇完整对比 paper。

### 技术栈
- **Go**：游戏引擎（bitboard）、Expectimax 搜索、Transposition Table、N-Tuple 网络与 TD 自对弈训练、评测器（headless simulator）、三端刷分驱动。
- **Python + PyTorch**：仅 RL 对照组（DQN / PPO / AlphaZero-style MCTS）。
- **关键约束**：Go 引擎编译成 c-shared `.so`（repo 已有 `//export` 基础，见 [main.go](../main.go)），Python 通过 ctypes/cffi 封装成 Gym 风格 `ThreesEnv`，**保证所有 agent（Go 搜索类 + Python RL 类）跑在完全相同的模拟器上 → 苹果对苹果的公平对比**。
- **弃用 Meteor**（`threes!/` 仅作历史参考）。可选：Go 引擎 → WASM 做纯客户端 demo 页。

### 架构总览
```
                 ┌──────────────────────────────────────────┐
                 │   Canonical Threes Engine (Go, bitboard)   │
                 │   move / merge / bag / preview / bonus     │
                 └───────────────┬───────────────┬───────────┘
                         c-shared │ .so           │ native
                    ┌────────────▼────┐   ┌───────▼─────────────────────┐
                    │ Python ThreesEnv│   │ Go Agents                    │
                    │ (Gym API)       │   │  - Expectimax + heuristic    │
                    │  - DQN          │   │  - Deck-Aware Expectimax     │
                    │  - PPO          │   │  - N-Tuple TD + Expectimax   │
                    │  - AlphaZero-MCTS│  └───────┬──────────────────────┘
                    └────────┬────────┘           │
                             └──────────┬─────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │  Unified Eval Harness (Go)     │
                         │  N games, seeds, metrics, jsonl│
                         └──────────────┬─────────────────┘
                                        ▼
                        blog charts  +  paper tables  +  records
                                        ▲
                         ┌──────────────┴─────────────────┐
                         │  Deployment Drivers             │
                         │  - Playwright (web x2)          │
                         │  - ADB + OCR py3 (Android)      │
                         └─────────────────────────────────┘
```

---

## 2. 评测框架（贯穿全程，最先建）

所有 agent、所有阶段共用同一评测器，保证可比性。

- **指标**：分数分布（mean / median / max / p90 / p99）、各砖块到达率（重点 6144 / 12288）、平均步数/局、ms/step、nodes/sec、TT 命中率。
- **协议**：每个 config 跑固定 N 局（快评 N=200，正式 N≥1000）；固定随机种子集合以复现；同一 harness 评所有 agent。
- **日志**：每局一行 jsonl（seed、逐步 move、终局 board、score、max tile），既喂 blog 图表也做 paper 表格。
- **产出物**：`bench/` CLI + 结果 jsonl + 画图脚本。

---

## 3. 阶段规划

> 相对排期，非死日期，取决于每周投入。含完整 RL 对照，总量约 **13–15 周**。

### Phase 0 — 地基与基准（~1.5 周）✅ 从这里开始
**任务**
- [ ] Bitboard 引擎：uint64 棋盘 + 行/列查表 move（替换 [gameboard](../gameboard/gameboard.go) 的 `[][]int` 热路径）。
- [ ] Headless 模拟器 + 统一评测器（见 §2），输出 jsonl + 汇总。
- [ ] c-shared `.so` + Python `ThreesEnv`（Gym API）封装，供后续 RL 使用。
- [ ] 复现现有 Expectimax baseline 数字（验证 README 的「~20%」说法），建立 baseline 报告。
- [ ] 引擎正确性测试：合并规则、1+2、双子、bonus tile、bag、preview、score 计算全部单测。

**交付**：可复现 benchmark 工具 + baseline 报告（blog 第 1 篇素材）。
**Exit**：能一键跑 1000 局并产出分数分布 + 6144 命中率；Go 与 Python 走同一引擎数字一致。

### Phase 1 — 搜索强化 + Deck-Aware（~1.5 周）
**任务**
- [ ] Transposition Table（chance node 复用）、迭代加深、时间管理。
- [ ] **精确牌袋建模**：追踪真实 bag 状态（替换 [`FindCandidates`](../gameboard/gameboard.go#L278) 的粗近似）。
- [ ] **preview 感知**：把 next-tile（含颜色/数值区间提示）纳入 chance node。
- [ ] Bonus tile 概率严谨化（现有 [`maxEle>=7` 分支](../ai/ai.go#L232)）。
- [ ] Beam Search（可选，仅 chance node，top-k / 累计概率截断）。

**交付**：Deck-aware vs deck-blind 第一组 ablation 数据（paper 核心图之一）。
**Exit**：deck-aware 相对 baseline 有可测量提升；有 ablation 数据。

### Phase 2 — N-Tuple TD 价值函数（~2.5–3 周，项目重心）
**任务**
- [ ] N-tuple 网络设计（行/列/蛇形/局部块 pattern，含对称性）。
- [ ] **Afterstate TD 学习**（swipe 后、新砖块前的状态做价值目标——最适合随机游戏）。
- [ ] 大规模 self-play 训练 pipeline。
- [ ] **Multi-stage TD**（对标 arXiv:1606.07374）冲 6144 命中率。
- [ ] learned value 替换手工启发式 leaf，接回 expectimax（depth 3→4→5 逐步加）。

**交付**：learned vs hand-crafted 对比曲线 + 新的 6144/12288 命中率（paper 主结果）。
**Exit**：learned value + expectimax 明显超过手工启发式 baseline，6144 命中率力争 > 7.83%。

### Phase 3 — RL 对照组（~2.5 周，Python/PyTorch）
**任务**
- [ ] DQN（board + next tile → Q(4)），作 RL baseline。
- [ ] PPO（policy/value），on-policy baseline。
- [ ] AlphaZero-style stochastic MCTS（policy/value net + chance-node MCTS）。
- [ ] 三者全部在 §2 统一 harness 上评测，与主线同口径对比。

**交付**：完整方法对比表 + 训练曲线 + 样本效率分析（paper 对比章节主体）。
**Exit**：三个 RL agent 均能训练收敛并产出可比数据；对比结论清晰。

### Phase 4 — 三端落地刷分（~2 周）
**任务**
- [ ] **Web 统一驱动（Playwright）**：threesjs.io 优先尝试直接 hook JS 读游戏状态（比 OCR 可靠）；官方站若 canvas 则 OCR 兜底；注入 swipe；追踪 bag。
- [ ] **Android（模拟器，无真机）**：Android Studio AVD（arm64 + Google Play 镜像，macOS 26 Apple Silicon 原生）。正版 app：付费 Threes!（`vo.threes.exclaim`，无广告，适合无人值守）优先；免费 Threes! Freeplay（`vo.threes.free`，有广告+次数限制）为备选。购买需用户 Google 账号登录+付款。
- [ ] OCR 从 Python 2 移植到 Python 3（[android/ocr/ocr.py](../android/ocr/ocr.py)）+ 按模拟器分辨率标定 tile 坐标（模拟器像素确定，OCR 极稳）+ ADB 长时间无人值守循环（自动重开局）。
- [ ] 先用现有 Go expectimax 驱动模拟器跑通整条流水线（截图→OCR→引擎→swipe→重开局），验证后再换强 AI。
- [ ] 长时间 campaign 冲记录，录屏/截图。
- [ ] （可选）Go→WASM demo 页，替代 Meteor。

**交付**：三端高分截图/视频（blog 高潮 + LinkedIn 素材 + paper「真机部署」章节）。
**Exit**：三端均能稳定无人值守刷分；至少各拿到一次高分证据。

### Phase 5 — Blog 收尾（穿插进行，最后 ~1 周）
- 全程记录整理成系列，图表全部来自 §2 评测器。见 §5。

### Phase 6 — Paper（~2 周）
- 撰写、arXiv 投稿、LinkedIn 发布。见 §4。

---

## 4. Paper 计划

**定位**：Threes 被严重研究不足（2048 烂大街，Threes 只有零星几篇）。我们做**第一个系统性、开源、可复现的强 baseline + 完整方法对比**，并带一个干净的 novelty。

**题目方向（待定）**：
> *The Value of Knowing What's Next: Deck-Aware Expectimax and a Systematic Comparison of Search and Learning Methods for Threes!*

**卖点**
1. 系统性对比：Expectimax(+heuristic / +N-tuple) vs DQN vs PPO vs AlphaZero-style MCTS，同一引擎、同一评测口径。
2. **Novelty**：量化牌袋/预览信息的价值（deck-aware ablation）。
3. 实证 SOTA：把 6144 命中率推过 2016 MS-TD 的 7.83%，力争复现 12288。
4. 真机落地：不止模拟器，三端真实刷分。
5. Take-away：传统搜索 + 学习价值函数在这类游戏仍是性价比之王。

**图表清单**：方法对比总表；6144/12288 到达率；deck-aware ablation；搜索深度 vs 强度/耗时；RL 训练曲线与样本效率；真机高分证据。
**Venue**：arXiv (cs.AI / cs.LG)，可后续投 IEEE CoG / ToG。
**社交**：LinkedIn 长文 + demo 视频（标题走「The Value of Knowing What's Next」）。

---

## 5. Blog 计划（系列）
1. 立项 & baseline：Threes 为什么比 2048 难，现有 expectimax 能打多少。
2. 搜索工程：bitboard、TT、迭代加深、deck-aware。
3. 学习价值函数：N-tuple + afterstate/multi-stage TD 自对弈。
4. RL 对照：DQN/PPO/AlphaZero 踩坑与对比。
5. 三端实战：Playwright + ADB/OCR，冲记录。
6. 总结 & paper 导读。

---

## 6. 目标仓库结构
```
threes-ai/
├── engine/        # Go bitboard 引擎（move/merge/bag/preview/bonus）+ 单测
├── search/        # Expectimax, TT, deck-aware, beam
├── ntuple/        # N-tuple 网络 + TD 自对弈训练
├── bench/         # 统一评测器 CLI + jsonl + 画图
├── cshared/       # c-shared .so 导出（供 Python）
├── rl/            # Python: env wrapper + DQN / PPO / AlphaZero-MCTS
├── deploy/        # Playwright (web) + ADB/OCR py3 (Android)
├── docs/          # 本计划 + blog 草稿 + paper 草稿
├── ai/ gameboard/ utils/ main.go   # 现有实现（逐步重构/迁移）
└── threes!/       # 旧 Meteor 站，历史参考，弃用
```

---

## 7. 风险登记
| 风险 | 影响 | 缓解 |
|---|---|---|
| 12288 概率极低 | P2 可能只做到一次或零次 | 明确为「冲刺项」，主指标锁 6144 命中率 |
| 官方站读盘困难（canvas） | 刷分不稳 | 优先 threesjs.io（可 hook JS）；OCR 兜底 |
| Android 模拟器标定/长跑稳定性 | 无人值守失败 | 用付费版(无广告)+模拟器像素确定；先小时级跑通再长跑；异常自动重启 |
| 付费 app 购买需用户手动 | 阻塞 Android 刷分 | 模拟器我搭好，Google 登录+$5.99 购买由用户完成 |
| Go/Python 引擎不一致 | 对比不公平 | 单一 c-shared 引擎 + 一致性单测 |
| AlphaZero-style 工程重、算力大 | 拖累排期 | 作对照组、限定规模；不达标也能写「负结果」 |
| self-play 训练慢 | Phase 2 拖长 | bitboard 提速 + 并行自对弈 |

---

## 8. 决策记录（LOCKED，2026-07-10）
1. 目标校准：稳定 6144 + 至少复现一次 12288 + 三榜顶尖梯队。删除「100% 12288」。
2. 语言：主线全 Go；RL 对照组（DQN/PPO/AlphaZero）用 Python/PyTorch。
3. Paper 范围：完整对照（含 DQN/PPO/AlphaZero）。
4. Meteor：弃用，仅历史参考；可选 Go→WASM 现代 demo 替代。
5. 起步：Phase 0（bitboard 引擎 + 统一评测器）。
6. Android：无真机 → 用 Android Studio AVD 模拟器（arm64 + Google Play 镜像）；正版付费 app 优先（无广告，利于无人值守）；模拟器搭建与 Phase 0 并行，可先用现有 expectimax 验证流水线。
