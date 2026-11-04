# Project Instructions

The user retired Deep Agents on 2026-11-03. The active Claude Code harness contains Subagents and Single Agent adapters.
Claude Code Agent Teams was retired on 2026-11-04; preserve historical evidence,
but do not restore its adapter, probes or launch choices. Research orchestration remains separate. Do not
restore the retired custom Team runtime, provider relay, Single/Team launchers,
coordinator/full modes, capability catalogs, or custom scheduling semantics.

## Ownership And Scope

- The active CLI pin is Claude Code 2.1.286. Codex adapters, launch choices and
  results were retired at the user's request. Do not restore active Codex paths.
  Read-only historical evidence readers may remain; preserve Claude comparisons.

- `harness/claude_code_subagents/`: print-mode ordinary native Claude subagents, with Teams disabled.
- `harness/claude_code_single_agent/`: print-mode strict Single, with native delegation tools removed and denied.
- `harness/_claude_cli.py` and `_claude_hooks.py`: shared native arguments/observations and opt-in Single permission policy.
- `harness/_cli.py`: CLI preflight, process lifetime, stdin and raw evidence only.
- Agent contexts, tools, communication and scheduling belong to the external CLI.
- Do not clone or vendor the upstream runtime, or import its SDK here.
- Deep Agents is retired. Keep historical evidence/readers, not active adapters,
  executable requirements, mounts, environment settings, probes or launch choices.
- Do not label ordinary subagents as a native Agent Team.
- Claude Single is a strict single-agent baseline. Use explicit native single
  policies, not prompt-only discouragement. Subagent runs are not single baselines.
- Do not impose a new roster, decomposition policy, benchmark protocol or solver
  prompt as part of CLI adaptation without explicit user authorization.
- `benchmarks/` owns task data and evaluation, independently of the adapters.
- Each benchmark owns `tasks.py`/`evaluation.py` and matching
  `scripts/<benchmark>/{catalog,run,score}.py` entry points. Shared CLI environment,
  unchanged baseline prompts and containers belong in `scripts/common/`;
  read-only native evidence belongs in `analysis/native_evidence.py`.
  Historical study utilities live in `scripts/studies/`, not baseline defaults.
- `benchmarks/dataclawbench/` and `benchmarks/hybriddeepresearch/` keep gold/reference
  fields host-side. The latter decodes the public release in memory; never publish
  decrypted questions, gold SQL, answers, or evaluation logs.
- On 2026-11-04 the user adopted orchestrator-worker lead prompt v4
  (`scripts/common/runtime.py`) as the Subagents default. Earlier prompts are kept
  verbatim in `docs/studies/` (see its README) for ablations. Preserve the exact
  default; changes and study overrides require user authorization.
  This is a prompted native baseline, not untouched default CLI behavior. Do not
  add our specialist roles, fixed roster, judge mechanism or cost-reduction policy.
  Lead-only instructions belong in the lead prompt, not worker-visible rule files.
  Run limits are shared task rules: state them identically to every condition.
  `benchmarks/organization.py` retains a research-intervention renderer only;
  bounded evidence-judge pilots are not native baseline results.
- `analysis/` retains generic utilities and read-only historical-schema readers.
- CooperBench is retired; preserve its evidence and retention exceptions in
  `docs/archive.md`, not an active dependency.
- Preserve unrelated changes and historical evidence. Snapshot overlapping
  uncommitted source before removing it; Git alone does not preserve that work.

See `docs/cli-adapters.md` for pinned versions, references and limitations.

## Server Operations

- Local `/Users/zhoujun/Desktop/MAS-information`; server
  `zhoujunye@10.123.4.30:22`, `/home/zhoujunye/MAS-information`.
- External server data and evaluation environment: `/home/zhoujunye/MAS-information-data`.
  The old server KramaBench upstream path is a compatibility symlink. Current
  provisioning receipts and source-stage location are in `docs/server-preparation.md`.
- Run tests and experiments on the server, not locally. Inspect live processes and
  CPU ownership first. Never modify `/home/zhoujunye/agent-team` or its resources.
- Prefer bounded parallel execution for independent experiment conditions and
  independent grading jobs to reduce wall-clock time. Choose concurrency after
  checking server capacity and provider rate limits; isolate workspaces and outputs,
  and preserve the authorized total attempts and cost scope. Serialize only when
  dependencies, shared mutable resources, or measurement validity require it, and
  explain that reason before launching. Record concurrency for timing comparisons.
- Use `scripts/server/sync.sh` for scoped source only. Never sync credentials,
  environments, caches, checkouts, assets, archives or outputs; never `--delete`.
- A sync does not remove retired files. Remote source cleanup or deployment needs
  explicit authorization; local cleanup is not automatic remote deployment.
- `.env` stays ignored and mode 0600. Never print or commit credentials.
- Never pass real provider keys into solver containers, tool subprocesses or
  solver-visible mounts. Live DataClaw/HDR calls use a per-run host credential
  gateway over a mounted Unix socket; the container receives only an ephemeral
  run token. Live solver containers use network=none. Authoritative request
  accounting is host-side; solver-writable logs are not a billing ledger.
  Token access does not authenticate which same-UID process made a request;
  record that limitation rather than claiming OS-level model-call isolation.
  The gateway must preserve native wire protocols, fixed destinations,
  and no retries; it must not implement model orchestration or scheduling.
  A leaked provider key must be revoked before paid experiments resume.
- Installs use the Tsinghua PyPI mirror. Do not provision environments, CLIs,
  Docker or cloud resources implicitly. Preserve historical images/assets and runs.
- Deploy, launch jobs and clean server files only within user authorization.

## Runtime And Evidence

- No paid agents, judges, simulators or retries without run-specific authorization
  and size. Offline tests use fake CLIs and must not invoke a paid provider.
- Planning is the default; execution requires an explicit `execute=True` or
  `--execute` plus run-specific user authorization.
- Never automatically bypass CLI permissions. A shell allow-list is neither a
  sandbox nor a guarantee of read-only behavior.
- Use exact CLI pins and disable automatic updates. Record native version output
  and raw stdout/stderr; a launcher hash is not a dependency/environment lock.
- Request retries=0 in native CLIs and do not retry in the adapter. Provider
  retry semantics and fatal key/balance handling need native-runtime validation
  before paid studies; do not recreate a provider client to claim enforcement.
- Keep failed attempts. Native context/output exhaustion is incomplete work.
- Lifecycle status, CLI final text and enabled team flags do not establish
  correctness, actual team creation, member shutdown or workspace quiescence.
- No old frozen-artifact, shared-budget, bounded-team or append-only-message
  guarantee carries over automatically to the native CLIs.
- New studies must freeze settings and bind evaluation to exact artifacts.
  Historical results, static inspection and fake-CLI tests do not establish gains.
- Report prompt lengths, token-weighted cache reuse by role, estimated/actual
  costs and unverified behavior when native evidence makes them available.
  Missing accounting is unknown, never zero.
