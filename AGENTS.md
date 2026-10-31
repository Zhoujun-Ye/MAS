# Project Instructions

Exploratory study of collaboration failures between isolated agent contexts. The
historical experiment design is `MAS传输损失验证实验指南.pdf` (2026-10-28);
section numbers in legacy comments refer to it. The current Leader-led Agent
Team target and benchmark admission gates are in `docs/leader-led-team.md` and
`docs/experiment1.md`. CooperBench is the selected benchmark; native environment
validation and real-model headroom remain separate empirical gates.
The target uses fixed capability templates and task-adaptive member selection;
do not generate new role prompts/permissions per task or treat selection as RSI.
Motivation freezes each task's TeamSpec across communication conditions. Future
feedback informs which Harness mechanism to study; do not preselect information
loss as the only target. See `docs/experiment1.md` and `docs/communication-policy.md`.

## Directory Responsibilities

- `harness/`: benchmark-agnostic MAS harness. `llm.py` (DeepSeek client),
  `trace.py` (JSONL run log and integrity checks), `agent.py` (one context and
  its tool loop), `agent_team.py` (fixed team and message scheduling), `runner.py`
  (bounded batch dispatch and atomic JSON persistence), `accounting.py` (cost estimates, balance).
- `benchmarks/cooperbench/`: the sole benchmark adapter, pinned official source
  and data under ignored `upstream/`. Use private feature assignments, isolated
  worker repositories and evaluator-only hidden tests/gold patches.
- `harness/planning.py`: generic once-only Leader decomposition and frozen plans.
  `harness/information.py`: frozen sender policy and authorized evidence/artifact
  workspace; all substantive outgoing reports use the same validation boundary.
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
- Never modify files, images or shared resources belonging to `/home/zhoujunye/agent-team`.
- CooperBench uses local Docker only; cloud backends are not authorized. Do not
  provision images/containers or install the full upstream dependency stack implicitly.
- Official worker images retain future Git history. Before model access, require
  base-history-only-v1 sanitation and independent run.py verification (refs,
  reflogs, unreachable objects, alternate stores and /patches). A clean HEAD alone
  is not admission. Keep new run evidence immutable unless the user explicitly
  requests deletion; never carry historical scores into a fresh study.

## Necessary Constraints

- No paid run (agents, judge or user simulator) without explicit authorization
  for that run and its size. Offline tests use scripted models only.
- Runtime owns scheduling, transport, permissions and task state. Information
  Harness policy cannot mutate them. Submission is an immutable version, not
  correctness; evaluator verdicts must bind to the exact current artifacts.
  Only explicit submission counts. CooperBench workers share a coder template,
  not identity or budgets. Keep per-member quotas and source-only snapshot rules fixed.
- Shared Team behavior belongs in harness/, not in a benchmark-specific prompt
  or scheduler. Adapters supply task/evaluation facts and domain tools; do not
  add repository-specific coordination strategies to the runtime.
- Read-only file/hash checks do not invalidate a submission; writes and terminal
  execution automatically reopen and require a new explicit submission.
  See docs/lite100-20261030.md for the newly authorized study and superseding limits.
  Context/output exhaustion is member-local.
  Distinguish ordinary nonzero command observations, execution failures and
  protocol denials in analysis. Tool-output and snapshot-export limits are separate.
- Prompts, budgets and model settings are frozen per output directory (the
  manifest digest refuses changes). Never tune role/domain prompts per condition;
  declared policy comparisons may vary only the frozen CommunicationPolicy.
  Report prompt lengths. Use a new output directory for a new setup.
- All conditions share model settings, initial plan, roster/roles, domain-tool
  permissions, allowed communication graph, scheduler policy and budgets.
  The exploratory pilot uses fixed async scheduling and autonomous communication.
  Controlled scheduling is diagnostic only, not the current primary condition.
- Keep every agent context append-only and pass `reasoning_content` back
  verbatim; never inject timestamps, trace ids or other volatile text into
  model-visible prompts. These keep DeepSeek's prefix cache effective.
- Provider errors (any 400 included) are recorded, never scored as
  model failures; context overflow, deadlock and agent quota exhaustion are
  incomplete agent failures in the all-started denominator. Provider/infrastructure
  errors remain separate. Paid reruns require new authorization; the pilot has no
  automatic retries. Key/balance errors stop further paid calls. Never drop
  incomplete attempts to improve a policy score.
- Report cache reuse token-weighted per condition and role, with estimated and
  actual (balance) cost. Prefer off-peak hours for large runs (half price).
- Pass criteria (guide §7) are fixed in `analysis/criteria.py` before any run;
  do not change thresholds after seeing results.
