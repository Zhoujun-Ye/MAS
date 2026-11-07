# Project Instructions

The user retired Deep Agents on 2026-11-03. The active Claude Code harness contains Subagents and Single Agent adapters.
Claude Code Agent Teams was retired on 2026-11-04; do not restore its adapter,
historical readers, probes or launch choices. Research orchestration remains separate. Do not
restore the retired custom Team runtime, provider relay, Single/Team launchers,
coordinator/full modes, capability catalogs, or custom scheduling semantics.

## Ownership And Scope

- The active CLI pin is Claude Code 2.1.286. Codex adapters, launch choices and
  results were retired at the user's request. Do not restore active Codex paths.
  Retired runtime readers are removed; retain the authorized Claude comparisons
  listed in `docs/archive.md`.

- `harness/claude_code_subagents/`: print-mode ordinary native Claude subagents, with Teams disabled.
- `harness/claude_code_single_agent/`: print-mode strict Single, with native delegation tools removed and denied.
- `harness/_claude_cli.py` and `_claude_hooks.py`: shared native arguments/observations and opt-in Single permission policy.
- `harness/_cli.py`: CLI preflight, process lifetime, stdin and raw evidence only.
- `harness/evidence_mas/`: our opt-in MAS harness, currently the observation
  store, bounded delta sharing and decision-v4 FULL protocol. The manual
  historical ledger API was removed on 2026-11-07. On 2026-11-05
  the user authorized system-side candidate extraction and submission consistency
  gates, without Structured prompting for the explicit FULL/OBS studies. The user
  subsequently requested the exact existing Native (N) prompt in both, FULL as a
  superset of OBS access, intermediate estimand capture and one-time shadow grading.
  Preserve
  the frozen Structured baseline separately. No Independent Framer, custom
  scheduler, automatic semantic choice or automatic submission. Consistency is
  not correctness; same-UID writable stores are not a security boundary.
- `harness/runtime_support/`: reusable SQL/web tools, credential transport and
  native proof validation shared across conditions. Keep these libraries out of
  `scripts/`; scripts own executable workflows, not reusable harness mechanisms.
- Agent contexts, tools, communication and scheduling belong to the external CLI.
- Do not clone or vendor the upstream runtime, or import its SDK here.
- Deep Agents is retired. Do not keep historical readers or active adapters,
  executable requirements, mounts, environment settings, probes or launch choices.
- Do not label ordinary subagents as a native Agent Team.
- Claude Single is a strict single-agent baseline. Use explicit native single
  policies, not prompt-only discouragement. Subagent runs are not single baselines.
- Do not impose a new roster, decomposition policy, benchmark protocol or solver
  prompt as part of CLI adaptation without explicit user authorization.
- `benchmarks/` owns task data and evaluation, independently of the adapters.
- Each benchmark owns `tasks.py`/`evaluation.py` and matching
  `scripts/<benchmark>/{catalog,run,score}.py` entry points. Shared CLI environment,
  unchanged baseline prompts and workflow composition belong in `scripts/common/`;
  reusable containers, CLI environment and provenance belong in
  `harness/runtime_support/`; domain-independent persistence belongs in `common/`.
  Benchmark timeout policies belong in `benchmarks/policy.py`.
  read-only native evidence belongs in `analysis/native_evidence.py`.
  Historical study utilities and experiment drivers live in `scripts/studies/`,
  not baseline defaults. Reusable MAS mechanisms belong in `harness/evidence_mas/`,
  even when initially evaluated as a research condition.
- `benchmarks/dataclawbench/` and `benchmarks/hybriddeepresearch/` keep gold/reference
  fields host-side. The latter decodes the public release in memory; never publish
  decrypted questions, gold SQL, answers, or evaluation logs.
- On 2026-11-04 the user froze the current orchestrator-worker lead prompt
  (`scripts/common/prompts/structured_subagents.py`, selected through
  `scripts/common/prompts/conditions.py`)
  as the only Subagents default. Superseded lead
  prompt files are removed; do not restore or version-label them. Preserve the exact
  default; there is no backup prompt. Changes and study overrides require user authorization.
  This is a prompted native baseline, not untouched default CLI behavior. Do not
  add our specialist roles, fixed roster, judge mechanism or cost-reduction policy.
  Lead-only instructions belong in the lead prompt, not worker-visible rule files.
  Run limits are shared task rules: state them identically to every condition.
- `analysis/` owns generic utilities and current Claude evidence analysis.
- Validation20 v1 is the user-adopted reusable development/validation set: exactly
  20 frozen questions per active benchmark. See `docs/studies/validation20.md`
  and its public ID/hash manifest. Do not reroll questions based on results, silently
  replace failures, or describe this repeatedly used set as an independent final test.
- CooperBench is retired, not an active dependency or retained result source.
- Preserve unrelated changes and current paired evidence. Snapshot overlapping
  uncommitted source before removing it; Git alone does not preserve that work.

See `docs/cli-adapters.md` for pinned versions, references and limitations.

## Server Operations

- Local `/Users/zhoujun/Desktop/MAS`; server
  `zhoujunye@10.123.4.30:22`, `/home/zhoujunye/mas`.
- External server data and evaluation environment: `/home/zhoujunye/mas-data`.
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
  Docker or cloud resources implicitly. Preserve required current images/assets.
- Deploy, launch jobs and clean server files only within user authorization.

## Runtime And Evidence

- The completed CPU8 paired run and its authorized upstream recovery are retained.
  Earlier interrupted batches were deleted by user request. Do not launch another
  paid comparison without renewed run-specific authorization. See
  `docs/studies/krama-cpu8-paired.md` and `docs/studies/evidence-infra.md`.
- No paid agents, judges, simulators or retries without run-specific authorization
  and size. Offline tests use fake CLIs and must not invoke a paid provider.
- For user-authorized reruns of attempts terminated by confirmed upstream HTTP
  5xx errors, use the rerun artifact as the primary result for that same task and
  condition. Do not keep the infrastructure-failed first attempt in the primary
  score denominator as an extra task, and do not select whichever score is better.
  Preserve the original failed attempt and its accounting as audit evidence;
  disclose rerun counts and total incurred costs, including failed calls. This
  replacement policy does not authorize retries for wrong answers, lifecycle-only
  exceptions, or additional paid attempts without run-specific permission.
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

## Current Infra And Retention Override (2026-11-07)

- The user authorized generic sharing/decision/infra repairs and offline tests,
  not new paid experiments. Use decision-v4 and the canonical workflow in
  `docs/studies/evidence-infra.md` going forward. Keep the Structured baseline
  exact and do not hardcode validation task IDs, answers or reference-specific logic.
- Observation context is bounded and incremental. Hook emissions, evidence reads,
  semantic correctness and actual model incorporation are distinct measurements.
  Native scheduling remains external; never add automatic semantic selection,
  submission, retries or a custom worker scheduler.
- The user explicitly revoked earlier retain-all-history instructions: delete
  earlier results, interrupted batches, obsolete receipts/stages, retired sources
  and result-only compatibility code without making result backups. Base retention is
  `krama-cpu8-paired-20261106-03` and its one-time upstream recovery, including
  original failures, all incurred accounting and frozen provenance. Keep current
  trajectory/infra validation receipts. See `docs/archive.md`.
- Later paid authorizations added smoke4 batches `krama-infra-smoke4-20261107-01`
  and `-02`. Preserve both raw batches and frozen paid sources: they provide the
  before/after speed comparison. Superseded offline iterations and duplicate logs
  are disposable; do not delete paid evidence merely because its implementation
  has since changed. Full-scale operation is documented in `docs/studies/fullscale-infra.md`.
- Read-only decision-v3 support remains solely for that retained paired run;
  old protocols and manual ledgers are not launch options. Active data, environments,
  credentials, required images, fixed question manifests and unrelated user work
  remain protected. Never touch `agent-team` resources or rewrite Git history.
