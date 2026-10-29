# Project Instructions

Motivation study for information lost between isolated agent contexts. The
experiment design is `MAS传输损失验证实验指南.pdf` (2026-10-28); section
numbers in code comments (§3.2 etc.) refer to it.

## Directory Responsibilities

- `mas_info/`: framework. `llm.py` (DeepSeek client), `trace.py` (JSONL run
  log), `agent.py` (one context and its tool loop), `relay.py` (conditions
  C0-C5 and boundary forms), `runner.py` (batch, resume, error handling).
- `mas_info/bcp/`, `mas_info/tau/`: benchmark adapters, frozen prompts and
  transmission diagnostics. τ² keeps its own orchestrator, user simulator and
  evaluator; only the agent side is ours.
- `mas_info/analysis/`: statistics, preregistered P1-P4 criteria, loss judge.
- `scripts/`: entry points; `scripts/server/`: sync, remote commands, setup.
- Ignored: `external/` (pinned upstream checkouts), `data/`, `.cache/`,
  `outputs/` (run snapshots, never rewritten), `.env`.

## Server Operations

- Local: `/Users/zhoujun/Desktop/MAS-information`. Standalone server (not HPC):
  `zhoujunye@10.123.4.30:22`, `/home/zhoujunye/MAS-information`. Key login
  works; `scripts/server/ssh.exp` is the password fallback.
- Run tests and experiments on the server, not locally. Inspect live processes
  and CPU ownership first; the `agent-team` project shares the machine.
- Sync scoped source only with `scripts/server/sync.sh`: never credentials,
  environments, caches, data, outputs or `--delete`.
- `.env` stays ignored and mode 0600; never print or commit credentials. The
  server's key comes from its own `agent-team/.env` (copied by setup.sh).
- BrowseComp-Plus reuses agent-team's verified BM25 index, Java 21 and decrypted
  test queries read-only; never modify files under `/home/zhoujunye/agent-team`.

## Necessary Constraints

- No paid run (agents, judge or user simulator) without explicit authorization
  for that run and its size. Offline tests use scripted models only.
- Prompts, budgets and model settings are frozen per output directory (the
  manifest digest refuses changes). Never tune prompts per condition; report
  prompt lengths. Use a new output directory for a new setup.
- All conditions share one model setting, retriever, index, tool budget and turn
  limit. τ²'s user simulator is fixed across conditions.
- Pass `reasoning_content` back verbatim on every request with tools. Provider
  errors (any 400 included) are recorded and rerun, never scored as failures;
  keep errors and ungraded outcomes apart from wrong answers.
- Preserve native data, scoring, licenses and evidence; keep failed attempts
  under `traces/attempts/`.
- Pass criteria (guide §7) are fixed in `mas_info/analysis/criteria.py` before
  any run; do not change thresholds after seeing results.
