# MAS 传输损失：Motivation 验证框架

历史记录，非当前使用说明。旧 benchmark 适配、配置与入口已移除；下文命令不再可用。
历史 outputs 保持原样。当前入口见仓库 README.md。

按《独立上下文间信息传输损失：Motivation 验证实验指南》（2026-10-28）实现：在模型、工具和预算不变的
前提下，比较单 agent（C0）与几种中转形式的 MAS（C1–C4，可选 C5），记录每一次跨边界消息，用于证明 P1–P4。

## 目录

```
harness/            与 benchmark 无关的 MAS harness
  llm.py            DeepSeek 接口：显式 thinking，reasoning_content 原样回传，错误分类
  trace.py          JSONL 日志（指南 §4），上下文重建，日志完整性检查
  agent.py          单个隔离上下文 + 工具循环，共享预算，轮数上限后强制作答
  relay.py          C0–C5 定义与四种中转：自由摘要 / 附录 A 结构化 / 全量中转 / 引用+回查
  runner.py         批量执行、断点续跑、错误分类、冻结配置
  accounting.py     按价目表估算费用（含高峰时段），记录账户余额
benchmarks/         每个 benchmark 一个文件夹，见 benchmarks/README.md
  browsecomp_plus/  适配代码 + upstream/（官方仓库，忽略）+ assets/（准备好的题目与分词器，忽略）
  tau2_bench/       适配代码 + upstream/（官方仓库，忽略，可编辑安装）
analysis/           McNemar、bootstrap、pass^k、oracle、κ、P1–P4、缓存命中、损失类型 judge
configs/            base.yaml（模型、价目表）、browsecomp_plus.yaml、tau2_bench.yaml
scripts/            browsecomp_plus/{prepare,run,grade}.py、tau2_bench/run.py、analyze.py、server/
tests/              离线测试（脚本化模型，不调用 API）
docs/engineering.md harness 工程说明与实测数据（缓存、费用、错误、并发）
outputs/            运行产物（忽略）：outputs/<benchmark>/<run>/
```

## 条件

| 条件 | BrowseComp-Plus | τ²-bench |
| --- | --- | --- |
| C0 | 一个 agent，`search` + `get_document` | 一个 agent，全部数据库工具 |
| C1 | 子 agent 自由文本汇报，主 agent 只看到汇报 | 操作员自由文本汇报 |
| C2 | 汇报必须是附录 A 的 JSON（记录 `schema_valid`） | 同左 |
| C3 | 向上附全部工具调用与观察原文（按序编号）；向下附原始问题与主 agent 工作笔记 | 向下附与用户的完整对话与前台笔记 |
| C4 | 所有观察自动存为 artifact，汇报只给摘要 + 索引，主 agent 可 `read_artifact` | 同左 |
| C5 | 单上下文按 C1 记录的子任务顺序执行（需先跑 C1） | 未定义 |

所有条件共用同一 `BASE` 提示词；每个输出目录的 `manifest.json` 记录全部提示词及长度，配置变化时拒绝写入。
预算：BCP 每题 50 次 search+get_document、τ² 每次对话 30 次环境调用，所有 agent 共用。

## 服务器上运行

```bash
scripts/server/sync.sh
```

```bash
scripts/server/remote.sh 'bash scripts/server/setup.sh && .venv/bin/python scripts/browsecomp_plus/prepare.py'
```

```bash
scripts/server/remote.sh '.venv/bin/python -m pytest -q'
```

付费运行（需先确认规模）：

```bash
scripts/server/remote.sh '.venv/bin/python scripts/browsecomp_plus/run.py --out outputs/browsecomp_plus/phase0 --sample 5 --conditions C0 C1 C2 C3 C4 C5'
```

```bash
scripts/server/remote.sh '.venv/bin/python scripts/browsecomp_plus/grade.py --out outputs/browsecomp_plus/phase0 && .venv/bin/python scripts/analyze.py outputs/browsecomp_plus/phase0'
```

`analyze.py` 输出每个条件的成功率、token、token 加权缓存命中率、单上下文最大长度、估算费用与余额变化、
预算耗尽情况、传输损失指标、日志完整性问题，以及 P1–P4 判定。

## 阶段 0 结果（BCP，2026-10-29）

5 题 × C0–C5 共 30 次运行：27 完成、1 未完成、0 个接口错误、0 个日志问题，实际花费 ¥23.78。
token 加权缓存命中率 C0 88%、C1 84%、C2 83%、C3 66%、C4 84%、C5 94%；相邻两次调用中 777/795 命中了
上一次的输入加输出。工程问题的修复与需要决定的设计问题（共享预算被并行子 agent 抢光、docid 引用判定过宽）
见 [docs/engineering.md](docs/engineering.md)。

## 与指南的差异和待办

- 模型：`deepseek-flash`，官方价目页（2026-10-29）显示由 DeepSeek-V4.1-Flash-1017 提供；指南中的
  `deepseek-v4-flash` 已是退役别名，同样路由到该模型。
- 检索器：指南推荐的 Qwen3-Embedding-8B 稠密检索尚未部署；目前为官方 BM25。
- 答案 judge：`deepseek-v4-pro`（与被测模型分开），沿用官方提示词与解析；官方用 gpt-4.1 / Qwen3-32B。
- τ² COMMUNICATE 检查用 τ² 原始的 substring，避免 τ² 2.0 默认的 gpt-5.5 语义 judge。
- 诊断：docid 到达率仅为代理指标；`scripts/browsecomp_plus/judge_arrival.py` 默认离线准备事实到达
  判定案例，付费 judge 需另行授权。未完成判定保持未知。τ² 仍只有参数溯源、委派次数和重复调用；
  因果补回实验和人工一致性验证尚未执行。分析报告使用 `--report-dir` 写入新目录。

## Architecture v2

Experiment 1 now uses a once-planned **complete initial task** protocol and five
handoff forms. ToolHop is the first candidate, not yet confirmed unsaturated for
our backbone. Its tool adapter and preflight are offline-only; BFCL multi-turn
is retired from the main experiment. See the current
[Experiment 1 design and admission gates](docs/experiment1.md). Historical C0-C5
results and thresholds are not evidence for this new protocol.

The current hierarchical MAS runtime is benchmark-independent (`harness/team.py`).
All workers receive the full public task and common constraints; C1-C4 vary
upward communication rather than withholding the original task. This requires
a new output directory, not resuming phase 0. See [architecture-v2](docs/architecture-v2.md)
for integration boundaries and limits of causal interpretation.
