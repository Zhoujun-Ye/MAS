# MAS 传输损失：Motivation 验证框架

按《独立上下文间信息传输损失：Motivation 验证实验指南》（2026-10-28）实现的阶段 0 框架：
在模型、工具和预算不变的前提下，比较单 agent（C0）与几种中转形式的 MAS（C1–C4，可选 C5），
记录每一次跨边界消息，用于证明 P1–P4。

## 结构

| 路径 | 内容 |
| --- | --- |
| `mas_info/llm.py` | DeepSeek OpenAI 兼容接口；显式 `thinking`，`reasoning_content` 原样回传；400 不重试 |
| `mas_info/trace.py` | JSONL 日志（指南 §4）；可重建任一 agent 任一时刻的完整输入上下文 |
| `mas_info/agent.py` | 单个隔离上下文 + 工具循环；共享工具预算；轮数上限后强制作答 |
| `mas_info/relay.py` | C0–C5 定义与四种中转：自由摘要 / 附录 A 结构化 / 全量中转 / 引用+回查 |
| `mas_info/runner.py` | 批量执行、断点续跑、错误与失败分开、冻结配置校验 |
| `mas_info/bcp/` | BrowseComp-Plus：官方 BM25 与工具格式、主研究员 + ≤5 检索子 agent、官方 judge、R_sys / R_arrive / L |
| `mas_info/tau/` | τ²-bench：前台（对话、政策、无数据库工具）+ 操作员（数据库工具、政策），跑在 τ² 自己的 orchestrator 和评测器里 |
| `mas_info/analysis/` | McNemar、bootstrap CI、pass^k、逐题 oracle、Cohen's κ、P1–P4 判定、附录 B 损失类型 judge |
| `configs/` | 冻结的模型、检索、预算设置 |
| `scripts/` | 准备数据、运行、评分、汇总；`scripts/server/` 同步与服务器环境 |

## 条件

| 条件 | BrowseComp-Plus | τ²-bench |
| --- | --- | --- |
| C0 | 一个 agent，`search` + `get_document` | 一个 agent，全部数据库工具 |
| C1 | 子 agent 自由文本汇报，主 agent 只看到汇报 | 操作员自由文本汇报 |
| C2 | 汇报必须是附录 A 的 JSON（记录 `schema_valid`） | 同左 |
| C3 | 向上附全部工具调用与观察原文；向下附原始问题与主 agent 工作笔记（推理 + 发言 + 派发） | 向下附与用户的完整对话与前台笔记 |
| C4 | 所有观察自动存为 artifact，汇报只给摘要 + 索引，主 agent 可 `read_artifact` | 同左 |
| C5 | 单上下文按 C1 记录的子任务顺序逐个执行（需先跑 C1） | 未定义 |

所有条件共用同一 `BASE` 提示词，角色与中转说明在开跑前定稿；每个输出目录的 `manifest.json`
记录全部提示词及其长度，配置或提示词变化时拒绝写入同一目录。预算：BCP 每题 50 次
search+get_document、τ² 每次对话 30 次环境调用，所有 agent 共用；每个 agent 每次任务最多 60 / 20 轮。

## 日志

每次运行一个 `traces/<run_id>.jsonl`，事件类型：`run_start`、`agent_start`、`message`（每条进入上下文的消息）、
`llm_call`（输入长度、token、缓存命中、耗时）、`tool_call`（`obs_id`）、`boundary_msg`（`edge`、`direction`、
`msg_id`、送达原文，另存子 agent 原始汇报与附件）、`artifact_write`、`final`（`context_tokens`）、`error`、`run_end`。
`mas_info.trace.contexts(events, upto=t)` 重建 t 时刻每个 agent 的上下文，`llm_inputs` 重建每次调用的精确输入。

## 服务器上运行

```bash
scripts/server/sync.sh
```

```bash
scripts/server/remote.sh 'bash scripts/server/setup.sh && .venv/bin/python scripts/prepare_bcp.py'
```

```bash
scripts/server/remote.sh '.venv/bin/python -m pytest -q'
```

阶段 0（付费，需先确认）：每个条件 5 题，检查日志完整性与 `reasoning_content` 回传：

```bash
scripts/server/remote.sh '.venv/bin/python scripts/run_bcp.py --out outputs/bcp-phase0 --limit 5 --conditions C0 C1 C2 C3 C4 C5'
```

```bash
scripts/server/remote.sh '.venv/bin/python scripts/run_tau2.py --out outputs/tau2-phase0 --domain telecom --limit 5 --trials 1'
```

评分与汇总（`grade_bcp.py` 调用 judge，付费；`analyze.py` 不调用模型）：

```bash
scripts/server/remote.sh '.venv/bin/python scripts/grade_bcp.py --out outputs/bcp-phase0 && .venv/bin/python scripts/analyze.py outputs/bcp-phase0 outputs/tau2-phase0'
```

## 与指南的差异和待办

- 模型 ID：指南写 `deepseek-v4-flash`，2026-10-29 的 `GET /models` 只列出 `deepseek-flash` 与 `deepseek-v4-pro`，
  配置暂用 `deepseek-flash`，需在阶段 0 确认它就是 V4 Flash。
- 检索器：指南推荐官方 Qwen3-Embedding-8B 稠密检索，尚未部署（需模型与索引资产及 GPU 环境）；目前为官方 BM25。
- 答案 judge：官方用 gpt-4.1 / Qwen3-32B，这里用 `deepseek-v4-pro`（与被测模型分开），沿用官方提示词与解析。
- τ² COMMUNICATE 检查：τ² 2.0 默认调用 gpt-5.5 语义 judge，这里用 τ² 原始的 substring 检查。
- 诊断：R_arrive 目前只按 docid 引用 / 全量中转 / artifact 读取判断，judge 判定"关键事实出现在汇报里"未实现；
  τ² 只有参数溯源、委派次数和重复调用，约束覆盖率与向上矛盾需 judge；失败分解是规则版初筛。
- 损失类型标注：`mas_info/analysis/loss_judge.py` 提供附录 B 的提示词、上下文重建和解析，命令行与 50 例人工抽检导出未做。
