# Project Instructions

Motivation study for information lost between isolated agent contexts. The
historical experiment design is `MAS传输损失验证实验指南.pdf` (2026-10-28);
section numbers in legacy comments refer to it. The current Leader-led Agent
Team target and benchmark admission gates are in `docs/leader-led-team.md` and
`docs/experiment1.md`. No current main benchmark is approved.
The target uses fixed capability templates and task-adaptive member selection;
do not generate new role prompts/permissions per task or treat selection as RSI.
Motivation freezes each task's TeamSpec across communication conditions. Future
feedback updates target communication policy only; see `docs/communication-policy.md`.

## Directory Responsibilities

- `harness/`: benchmark-agnostic MAS harness. `llm.py` (DeepSeek client),
  `trace.py` (JSONL run log and integrity checks), `agent.py` (one context and
  its tool loop), `relay.py` (conditions C0-C5 and boundary forms), `runner.py`
  (batch, resume, error classes), `accounting.py` (cost estimates, balance).
- `benchmarks/`: BCP adapts the generic Leader planning and Information Harness;
  TravelPlanner is retired. Adapters use one folder each with ignored `upstream/`
  and `assets/`. Retained retired server source/assets are historical.
- `harness/planning.py`: generic once-only Leader decomposition and frozen plans.
  `harness/information.py`: authorized evidence/artifact/memory/state workspace.
  Leader has no domain tools; sharing storage never shares all contexts.
- `analysis/`: statistics, preregistered P1-P4 criteria, prompt-cache reuse,
  loss-type judge. No benchmark-specific code.
- `scripts/<benchmark>/`: prepare/run/grade entry points; `scripts/analyze.py`
  summarizes any output directory; `scripts/server/`: sync, remote, setup.
- `docs/`: engineering notes and measured harness behaviour.
- `outputs/<benchmark>/<run>/` (ignored): manifests, traces, results, grades,
  balances and summaries. Never rewrite them; failed attempts stay under
  `traces/attempts/`.

## Server Operations

- Local: `/Users/zhoujun/Desktop/MAS-information`. Standalone server (not HPC):
  `zhoujunye@10.123.4.30:22`, `/home/zhoujunye/MAS-information`. Key login
  works; `scripts/server/ssh.exp` is the password fallback.
- Run tests and experiments on the server, not locally. Inspect live processes
  and CPU ownership first; the `agent-team` project shares the machine.
- Sync scoped source only with `scripts/server/sync.sh`: never credentials,
  environments, caches, benchmark checkouts, assets, outputs or `--delete`.
- `.env` stays ignored and mode 0600; never print or commit credentials. The
  server's key comes from its own `agent-team/.env` (copied by setup.sh).
- Package installs on the server use the Tsinghua PyPI mirror (pypi.org stalls).
- BrowseComp-Plus reuses agent-team's verified BM25 index, Java 21 and decrypted
  test queries read-only; never modify files under `/home/zhoujunye/agent-team`.

## Necessary Constraints

- No paid run (agents, judge or user simulator) without explicit authorization
  for that run and its size. Offline tests use scripted models only.
- Prompts, budgets and model settings are frozen per output directory (the
  manifest digest refuses changes). Never tune prompts per condition; report
  prompt lengths. Use a new output directory for a new setup.
- All conditions share model settings, initial plan, roster/roles, domain-tool
  permissions, allowed communication graph, scheduler policy and budgets. A
  benchmark's retriever/index, when present, must also be fixed.
- Keep every agent context append-only and pass `reasoning_content` back
  verbatim; never inject timestamps, trace ids or other volatile text into
  model-visible prompts. These keep DeepSeek's prefix cache effective.
- Provider errors (any 400 included) are recorded and rerun, never scored as
  failures; context overflow ends a run as incomplete; key or balance errors
  stop the batch. Keep errors and ungraded outcomes apart from wrong answers.
- Report cache reuse token-weighted per condition and role, with estimated and
  actual (balance) cost. Prefer off-peak hours for large runs (half price).
- Pass criteria (guide §7) are fixed in `analysis/criteria.py` before any run;
  do not change thresholds after seeing results.
