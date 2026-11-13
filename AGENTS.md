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
- `harness/_claude_cli.py` and `_claude_hooks.py`: shared native arguments/observations,
  strict Single permissions and the newly authorized mandatory-delegation policy.
  Native/Structured leads may read/plan, but native hooks deny command execution
  and file writes and block Stop until a matching lead Agent/Task call produces
  SubagentStart. Workers are not gated. Keep exact organization prompts unchanged;
  never create a worker from the harness or restore loop detection. This is a new
  runtime protocol; require fresh free native proofs and separate paid authorization.
  On November 12 the user retired all
  loop detection hooks, including observation-only counters, warnings, worker
  stops, lead notices and host loop termination. Do not restore loop-mode launch
  options or pilot drivers. Preserve frozen paid sources/results; historical
  analysis may read recorded fields without executing a detector. Default solver
  settings are now thinking disabled, fixed T=1.0. See
  `docs/studies/loop-guard-retirement-20261112.md`.
- `harness/_cli.py`: CLI preflight, process lifetime, stdin and raw evidence only.
- The November 12 anomaly fix sets native print background-wait ceiling to zero
  in both adapters/containers; the common outer task deadline still applies.
  Do not reintroduce the native ten-minute truncation or custom continuation.
  Preserve recorded grades and paid sources; diagnostics distinguish native
  waiting-limit termination, model artifact errors and replay/reporting errors.
  The anomaly investigation authorizes server free checks only, not paid reruns.
  Follow-up diagnostics do not change timeout-zero scoring: report lead waiting
  and valid submission timing separately, leave unknown timing unknown. Replay
  attribution uses Docker container state, not reserved exit codes alone. An
  additional paired native-audit view must drop each unaudited task from every
  condition while preserving raw scores and all costs. Display known partial
  costs as lower bounds with unknown-request counts, never complete invoices.
- The November 11 review-fix request authorizes a shared explicit tool surface:
  Single's twelve tools plus Agent/Task, SendMessage and ListAgents for Subagents;
  disable skills/slash commands for both. Keep the frozen organization prompts exact.
  New runtime proofs must bind the environment/tool configuration and observed
  init surface. Historical paid runs retain their original tool configurations.
- FULL, OBS and their prompt-only ablations were retired on 2026-11-10.
  Do not restore their runtime, tools, hooks, prompts or launch choices. Preserve
  paid historical evidence and frozen sources; analysis may read recorded artifacts
  without reconstructing or executing the retired decision engine.
  Default conditions are strict Single and frozen Structured Subagents. On
  November 11 the user approved an opt-in KramaBench Native prompt condition:
  Structured's opening paragraph plus "Always deploy at least one subagent."
  This is minimally prompted native delegation, not unprompted CLI behavior.
  Keep it separate from Structured; do not change the frozen default.
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
  not baseline defaults. Do not port retired MAS mechanisms into either baseline.
- `benchmarks/dataclawbench/` and `benchmarks/hybriddeepresearch/` keep gold/reference
  fields host-side. The latter decodes the public release in memory; never publish
  decrypted questions, gold SQL, answers, or evaluation logs.
- On 2026-11-04 the user froze the current orchestrator-worker lead prompt
  (`scripts/common/prompts/structured_subagents.py`, selected through
  `scripts/common/prompts/conditions.py`)
  as the only Subagents default. The explicitly selected Native study uses
  `scripts/common/prompts/native_subagents.py`, not a replacement default.
  Superseded lead prompt files are removed; do not restore or version-label them. Preserve the exact
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
- The Krama Random20 three-repeat driver uses the same frozen 20 questions in
  Single/Native/Structured, three independent rounds (180 solvers). Its seeds
  control dispatch order only, not provider sampling. New preparations use the
  current thinking-off/T=1.0 default; frozen paid T=0.7/T=1.0 runs stay unchanged.
  Keep zero retries and equal-weight repeat reporting; see `docs/studies/krama-three-repeats.md`.
  Implementation/free checks do not authorize paid execution of the prepared plan.
- CooperBench is retired, not an active dependency or retained result source.
- FDABench is opt-in and local-only: exclude missing/invalid public scoring
  references and all cloud databases. Never mount gold subtasks, reference reports,
  rubric answers or frozen search results. Missing assets block preflight, not
  silently reduce the task pool. Choice scoring is offline; report judges need
  separate paid authorization. Existing Validation20/default matrix scope stays
  unchanged. See `docs/fdabench.md` for source pins and adaptation limitations.
- Preserve unrelated changes and current paired evidence. Snapshot overlapping
  uncommitted source before removing it; Git alone does not preserve that work.

See `docs/cli-adapters.md` for pinned versions, references and limitations.

## Server Operations

- On November 12 the user selected fixed T=0.7 and retired the temporary
  temperature pilot, post-session repetition screen and sampling override API.
  The T=0.3/T=0.5 scope ended with 23 completed and one user-interrupted attempt;
  all twelve T=0.7 attempts completed before the subsequent stop request.
  Preserve these paid outputs, frozen source stages and accounting; see
  `docs/archive.md`. Cleanup authorizes free verification, not further paid runs.

- The later November 12 review found sustained model-directed repeated debugging
  in a T=0.7 regression attempt. The user selected T=1.0 for all future runs,
  prioritizing this issue over reduced sampling variability. Keep the T=0.7
  frozen attempt unchanged; this observation is not a causal temperature result
  or authorization to restore a loop detector. Fresh T=1.0 native proofs are
  required before separately scoped paid dispatch.

- Current DeepSeek reproducibility policy: thinking disabled, fixed temperature 1.0,
  effective reasoning effort not applicable (`--effort none`). Configure this
  through the pinned CLI, not request-body rewriting in the gateway. Native
  main/worker requests must match the frozen policy before upstream dispatch.
  If the user explicitly re-enables thinking, use high unless separately
  authorized otherwise; never silently default to max. Keep historical actual
  high/max settings unchanged. Configuration changes require free native
  verification before any separately authorized paid dispatch.
- The subsequent harness review authorizes nine T=0.7 solvers on astronomy-easy-5,
  biomedical-hard-7 and biomedical-hard-8 in Single/Native/Structured, zero retries
  and no required judges, CNY20 budget with CNY18 account stop-loss. After observing
  repeated model debugging the user separately authorized the same nine fresh
  solvers at T=1.0, zero retries/judges and an independent CNY20 budget/CNY18 stop-loss.
  Each round uses frozen source, CPU8/thread4, concurrency three and unchanged
  prompts/3600-second limits. Keep both outputs and all accounting; never treat
  the second round as replacements or reuse paid authorization after completion.
  Both nine-slot rounds are now complete (zero retries/judges); these scopes
  are consumed. Preserve the T=0.7 timeout/repeated-debugging trace and T=1.0
  model-pipeline OOM evidence. The post-run OOM telemetry repair received free
  validation only, not paid replacement attempts.
- The completed November 12 authorization permitted exactly three Structured solvers,
  once each on legal-easy-11, astronomy-easy-5 and wildfire-hard-10, thinking off,
  T=1.0, loop observation only, 900 seconds, concurrency three, CPU8/thread4,
  zero retries and paid judges. Independent CNY20 budget; stop at CNY18 account
  spend to leave in-flight margin, not a provider hard cap. See
  `docs/studies/temperature1-pilot-20261112.md`. This authorization is consumed;
  the cleanup that followed was free verification plus Git commit/push.
- A later November 12 request authorizes source sync and one new frozen Random20
  attempt per Single/Native/Structured condition: 60 solvers, at most six one-call
  semantic judges, zero retries, thinking disabled/T=1.0, no loop detector,
  concurrency sixteen with two overlapping graders, CPU8/thread4 and unchanged
  task limits/prompts. The user explicitly requested no monetary cap and active
  monitoring. Preserve all failures and accounting; do not hot-change paid source
  or retry failures. See `docs/studies/krama-random20-temperature1-20261112.md`.
  That run has completed all 60 solver slots and six judge calls; its scope is
  consumed and does not authorize additional paid attempts or replacements.
- The subsequent November 12 cleanup-and-launch request authorizes one three-round
  Krama Random20 comparison: 180 solvers, at most 18 one-call semantic judges,
  zero retries, thinking off/T=1.0, no guard, frozen prompts/tasks, CPU8/thread4.
  Seeds 0/1/2 affect task-group dispatch order only. Rounds run sequentially at
  solver concurrency 16 with two overlapping graders. The user explicitly chose
  no monetary cap and continuous monitoring. Preserve failures and all costs;
  no replacement, expansion or hot source changes. Output prefix:
  `krama-random20-three-repeats-20261112-01`. See `docs/studies/krama-three-repeats.md`.
- The user subsequently stopped that batch to introduce mandatory delegation.
  Preserve its partial first round and all incurred accounting; rounds two/three
  were not dispatched. Do not resume or replace it under changed source. The new
  delegation policy is authorized for implementation and free server checks only;
  a new paid run requires separate confirmation.
- That confirmation now authorizes `krama-random20-forced-repeats-20261112-01`:
  reuse the two complete T=1.0 Single rounds from `krama-random20-20261112-01`
  and the stopped repeat batch's first round, each exactly once. Run one new
  Single round (20), plus three new Native and Structured rounds (60 each):
  140 new solvers, at most 14 one-call judges, zero retries, CPU8/thread4,
  thinking off/T=1.0, mandatory delegation for MAS only, unchanged frozen prompts,
  concurrency 16 plus two graders, no monetary cap and continuous monitoring.
  The user explicitly authorized deletion of Native/Structured results only from
  the stopped repeat batch, retaining its Single and incurred accounting. Do not
  delete earlier historical batches or duplicate the two retained Single rounds.
  All 140 new solvers and fourteen judges have completed; that authorization is
  consumed. Subsequent anomaly fixes/review authorize free server validation and
  Git commit/push only, not paid replacement attempts or production deployment.
- The subsequent Native/Single causal study excludes Structured. The user approved
  initially five arms x twenty tasks, then explicitly expanded after review to
  six arms x thirty frozen tasks x seeds 0/1/2 (540 solvers), ninety independent
  recon sessions and one-call judges only for actually eligible frozen questions
  (eligible tasks x six arms x three rounds), zero retries, no monetary cap.
  Solver/recon share sixteen slots, with two graders and shared CPU reservations.
  The user supplied the requested review and authorized fixing it then launching
  thirty tasks, including the prompt-only brief arm. Require fresh free checks and
  freeze the expanded plan before dispatch. Nonfatal 5xx and model deviations
  remain recorded without retry and do not stop the assigned study; fatal errors,
  confirmed leakage, integrity/cleanup failure and unknown execution still stop.
  Keep study-only interventions under
  `scripts/studies/causal_experiments/`; do not change baseline prompts or restore
  loop detection. The existing `0eb2850` fixes were separately authorized for
  production source sync; that does not authorize deployment of unfinished study code.
- The subsequent T=0.7 authorization is a fresh six-arm thirty-task comparison,
  three rounds (540 solvers and 90 independent recon), plus E4 on ten targeted
  tasks: three brief variants, three repeats, 90 worker-role replays and 90 paired
  lead continuations. Total 810 new sessions, at most 72 one-call semantic judges,
  zero retries, no monetary cap, active monitoring, shared concurrency 16 plus
  two graders and CPU8/thread4. E4 sessions have 900-second limits. Use fresh
  frozen source and native fake-provider role/resume proofs; never copy final
  workspaces or later transcripts into replay prefixes. Immediate first-report
  delivery and regenerated worker-role main-session prompts are study limitations,
  not exact reproduction of historical asynchronous native subagents. Seeds only
  control dispatch order. The user delegated remaining within-scope launch decisions
  and requested durable offline execution while asleep; no extra sessions or retries.
- Local `/Users/zhoujun/Desktop/MAS`; server
  `zhoujunye@10.123.4.30:22`, `/home/zhoujunye/mas`.
- External server data and evaluation environment: `/home/zhoujunye/mas-data`.
  The old server KramaBench upstream path is a compatibility symlink. Current
  provisioning receipts and source-stage location are in `docs/server-preparation.md`.
- Run tests and experiments on the server, not locally. Inspect live processes and
  CPU ownership first. Never modify `/home/zhoujunye/agent-team` or its resources.
- All four benchmarks and all supported conditions default to 8 CPUs and 4 numerical
  threads per solver. Use the shared defaults in `harness/runtime_support/runtime.py`
  and explicit child flags; never silently fall back to 2 CPUs. Freeze CPU/thread
  settings and capture resources in paid infra studies. Historical frozen runs
  retain their actual profiles; do not hot-change or replay paid attempts.
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
- HF asset preparation defaults to server-direct `https://hf-mirror.com`, with
  pinned revisions and hash checks; no automatic official-site fallback. FDABench
  corpus authentication to that mirror is user-authorized; send the host-only HF
  token only to its exact host for the gated corpus, never CDN redirects or solvers.
  This asset-only exception does not change solver web access.
- Solver web GETs require the local-Mac Clash tunnel maintained by
  `scripts/server/web_tunnel.py` and documented in `docs/studies/web-infra.md`.
  Keep its server Unix socket private; no direct/provider-fetch fallback, public
  proxy listener or solver-container networking. Search/model/judge APIs remain
  server-direct. Preserve the installed local launch agent/runner and live socket.

## Runtime And Evidence

- The completed CPU8 paired run and its authorized upstream recovery are retained.
  Earlier interrupted batches were deleted by user request. Do not launch another
  paid comparison without renewed run-specific authorization. See
  `docs/studies/krama-history.md` and `docs/studies/evidence-infra.md`.
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
- Mark observed host-ledger upstream 5xx independently as `infra_degraded`; never
  automatically replace or retry those attempts. Retry only free pre-dispatch TLS
  readiness (at most three probes), not a solver or a paid model/search request.
  New Krama timeout outcomes score zero consistently with the other benchmarks;
  retain submitted artifacts and diagnostic artifact grades without rewriting history.
- Lifecycle status, CLI final text and enabled team flags do not establish
  correctness, actual team creation, member shutdown or workspace quiescence.
- No old frozen-artifact, shared-budget, bounded-team or append-only-message
  guarantee carries over automatically to the native CLIs.
- New studies must freeze settings and bind evaluation to exact artifacts.
  Historical results, static inspection and fake-CLI tests do not establish gains.
- Report prompt lengths, token-weighted cache reuse by role, estimated/actual
  costs and unverified behavior when native evidence makes them available.
  Missing accounting is unknown, never zero.

## Current Infra And Retention Override (2026-11-10)

- On November 11 the user requested preparing a fresh random twenty-task
  KramaBench comparison for Single, Native and Structured: sixty solver slots,
  zero retries and no paid judges. Native must actually delegate at least once;
  its prompt is the approved minimal prefix, with the same native audit as
  Structured. Preserve the original Validation20 and the independently seeded
  new ID/hash manifest. A subsequent November 11 request explicitly authorizes
  deployment and one run of these sixty slots at concurrency sixteen, CPU8/thread4,
  with zero retries and paid semantic judges only where required (two task IDs
  across three conditions, at most six one-call grades). Preserve all failures
  and accounting; no replacement solver or judge retry is authorized. See
  `docs/studies/krama-random20-20261111.md`.
- The user retired FULL/OBS and authorized one FDABench choice smoke: four fixed
  questions times Single/Structured, eight solver attempts, no retries or paid
  judges. This is not standing authorization for further paid experiments.
  Shared infra is documented in `docs/studies/evidence-infra.md`. Keep the
  Structured baseline exact and never hardcode answers or reference-specific logic.
- A subsequent authorization permits one CPU8/thread4 rerun of those same four
  FDABench choices in Single/Structured: eight new solvers, no retries or paid
  judges, compared with the retained 2-CPU diagnostic. See
  `docs/studies/fdabench-cpu8-rerun-20261110.md`; this is not standing authorization.
- On November 11 the user authorized two existing Validation20 tasks each from
  DataClaw, HybridDeepResearch and KramaBench, once per Single/Structured: twelve
  solvers, zero retries and zero paid judges. SQLite image upgrade is authorized
  after compatibility validation. Once the replacement is validated, use it for
  active runs and remove unused MAS old images; retain historical image IDs,
  frozen sources and paid traces. This overrides old-image retention only, not
  paid-evidence retention or protection of other projects' images/resources.
- After reviewing the November 11 infra results, the user authorized broad MAS
  repo/server cleanup. Remove confirmed disposable temporary sources, caches and
  superseded synthetic payloads, preserving paid evidence and runtime resources.
  This does not authorize new paid calls or changing the Clash node; the observed
  intermittent downstream TLS EOF remains an external risk.
- Hook emissions, evidence reads, semantic correctness and actual model
  incorporation are distinct measurements.
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
- Read-only recorded artifact analysis remains for retained paid runs;
  old protocols and manual ledgers are not launch options. Active data, environments,
  credentials, required images, fixed question manifests and unrelated user work
  remain protected. Never touch `agent-team` resources or rewrite Git history.
