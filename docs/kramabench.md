# KramaBench Adapter

## Active Team Runtime

As of 2026-11-01 the active modes are `team` and `single`. The foreground source
and prior documentation are snapshotted at commit `f9c9a4a`; `mas` and `delegated`
are rejected rather than silently mapped to Team. The remaining sections below
record the historical integration and v1-v9 evidence, not current launch settings.

The current [Team protocol](agent-team-design.md) uses fixed `worker`, `explorer`,
`analyst` and `verifier`
templates, direct peer mail, persistent contexts, Leader-only task authority and
a draining barrier before final submission.

The current catalog is `kramabench-team-v4`: Team defaults to a pure coordinator
with no domain tools, including readers. `--leader-mode full` is only an explicit
ablation. Explorer has shell with an
advisory no-write instruction. Every message can wake idle members with original
grants, and completed handoffs automatically unblock dependencies. Single and
Team use the same `pipeline_path` frozen-hash/selected-file export contract. Closing
lists file metadata and hashes; the Leader selects a path without reading/copying code.
Only that selected path is exported at submit, rejecting changes after freeze.
The Leader actively seeks useful multi-member specialist decomposition, not a
default end-to-end owner. Roles and parallelism follow deliverables/dependencies,
not a mandatory panel. A repeated indefinite wait after a confirmed no-progress
notice drains the team while preserving final submission.
Execution verification belongs to Workers before finish. Per-member defaults
inherit shared ceilings. Generic domain checks are in `PROJECT_CONTEXT` for Single
and Workers; the task-tuned archeology analysis contract remains inactive.
See [v4 stability verification](team-stability-v4-20261101.md); the historical sections below
must not be copied as current roles, prompts, flags or submission settings.

Run offline verification on the server:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/kramabench/offline.py --mode both --output outputs/team-fixture-NEW
```

The paid runner is `scripts/kramabench/pilot.py --mode team --execute-paid` with
explicit upstream, existing image and fresh output paths. Run-specific authorization
is still required. It creates only selected containers, freezes source/input/tool/
model settings, uses retries=0, retains failures, and invokes no paid judge. Current
diagnostic ceilings are 64 model calls, 120 domain calls, 1800 execution seconds,
120 audit seconds, 8 identities, 64 activations and 4 parallel Workers. Message
activations and their domain usage are reported separately from assigned tasks. Previous
archeology outputs and reference disagreement are diagnostic evidence, not held-out
scores or evidence of a Team improvement.

## Historical Scope

This adapter uses our Leader-Subagent runtime, not an upstream agent system.
Upstream: https://github.com/mitdbg/Kramabench
Pinned revision: `b2e0d77540263f8b6119f977fe79a8c4386b5a02`.
The six canonical workload files contain 104 questions: archeology 12,
astronomy 12, biomedical 9, environment 20, legal 30, wildfire 21.
Tiny/quick-start workload files are not additional evaluation tasks.

The implementation provides public task loading, a fixed role catalog, a native
System API bridge, immutable attempt records, and native response export.
Full pinned input deployment and real-container format/tool smoke are recorded below.
Scalar numeric answer scoring is available without a judge; the upstream paid
pipeline evaluator is not invoked. Real-model results are run-specific and do not
establish quality/cache gains. This document does not authorize new paid runs.
Scripted fixtures are not KramaBench scores.

## Fixed Capabilities

| Role | Tools | Local ceiling | Responsibility |
|---|---|---|---|
| Leader | All domain tools + delegate | 40 calls, 80 tools | Plan, work directly, select templates, integrate answer |
| data_scout | list_files, inspect_file, read_file, read_output | 8 calls, 16 tools | Discover relevant sources, schemas, units, join keys |
| pipeline_analyst | Reader tools + write_file, terminal | 12 calls, 28 tools | Build/run transformations and save reproducible evidence |
| data_preparer | Reader tools + write_file, terminal | 10 calls, 20 tools | Produce reusable extracted/aligned data, code, schema and provenance |
| calculation_worker | Reader tools + write_file, terminal | 10 calls, 20 tools | Implement an assigned quantity/component and save computed results |
| result_reviewer | Reader tools only | 8 calls, 16 tools | Inspect assigned code-logic or result/evidence risks without execution |
| requirement_analyst | Reader tools only | 6 calls, 8 tools | Clarify local estimand, constraints, ambiguity and acceptance checks |
| data_auditor | Reader tools + write_file, terminal | 8 calls, 16 tools | Check assigned source-quality or cross-source alignment risks |
| reproduction_checker | Reader tools + write_file, terminal | 10 calls, 20 tools | Check numerical methods, independently recompute or label a same-method rerun |

Default shared session ceilings remain 40 model calls, 80 budgeted tool calls,
900 seconds, 8 children, 16 delegations, and at most 4 concurrent children.
One model call is reserved for the Leader, plus one report call for each admitted
delegation/resume within the shared ceiling. The remaining role ceilings are not reservations;
they cannot all be spent simultaneously. Resume preserves context and lifetime
tool consumption. The Leader assigns disjoint output paths before parallel writes.

Eight templates are a capability catalog, not eight required children. The unchanged
eight-child limit is intentional: choose useful roles and reuse existing children,
not every role on every task. Templates may also have several instances for disjoint
data partitions. More templates do not authorize more calls, tools or spending.

The read-only reviewers cannot re-execute code. For a computational recheck, use
`reproduction_checker` or a scoped execution-capable auditor. Neither a child report
nor the runtime's `done` status is a benchmark verdict.
There is no forced role sequence, fixed team size, generated permissions, fork,
or nested delegation. Children receive only the Leader's brief and selected context.

## Production And Verification

V9 consolidates six review templates into three: `data_quality_auditor` and
`join_auditor` become `data_auditor`; `code_reviewer` merges into `result_reviewer`;
`statistical_auditor` merges into `reproduction_checker`. Read-only code/result
inspection stays separate from executable checks. These are capability unions,
not mandatory full checklists: each brief selects a concrete risk or partition.
Multiple instances of one template may run independently and resume by agent ID.
No local ceilings are added together, and shared session limits are unchanged.
The five production/exploration templates are unchanged. Retired names are not
aliases in new sessions; historical manifests/traces remain untouched.

The objective remains solving the supplied task reliably, not maximizing the number
of alleged defects. Production and discovery roles return deliverables, evidence,
actual validation, assumptions and unfinished work; they do not use the defect-report
contract. Auditors separate confirmed issues, suspected issues, no issue
found within their checked scope, and not checked. Findings include affected claims,
source/code locations, evidence, answer impact and a minimal next check/correction.
The Leader resolves conflicting evidence rather than taking a majority vote.

V8 corrects the review-heavy allocation tendency. The leader considers production
ownership before doing the whole calculation. `pipeline_analyst` can own a complete
bounded pipeline from discovery through execution; `data_preparer` and
`calculation_worker` offer more focused ownership where useful. These are alternatives
or distinct work packages, not mandatory stages. Workers self-check their outputs;
auditors are selected for specific residual risks. Integration consumes saved code
and results and validates their interfaces, rather than duplicating every pipeline.

Examples of optional batches (not a mandatory workflow):

| Available inputs | Parallel work | Dependency boundary |
|---|---|---|
| Independent source partitions with known local objectives | Multiple pipeline_analyst owners, each producing runnable code and results | Disjoint output paths; no leader implementation of the same branches |
| Raw source needing extraction and an independent numerical question on another source | data_preparer + calculation_worker | Specify output schemas/units; a calculation dependent on preparation must wait |
| Completed preparation artifacts and a defined quantity | calculation_worker, or pipeline_analyst for a multi-step pipeline | Reuse the ready artifacts; do not recreate the preparation stage |
| Unknown sources and a source-independent semantic question | requirement_analyst for semantics + data_scout for one inventory, or scouts on disjoint partitions | Do not give both roles a full-file discovery task; wait when semantics depends on missing source evidence |
| Existing source inventory with unresolved semantics | requirement_analyst with known paths, schemas and coverage | Inspect only source slices needed to resolve the ambiguity; supplied assumptions remain unverified |
| Identified sources and join specification | Scoped data_auditor instances on source quality and join cardinality where both are needed | Separate briefs/output paths; wait when paths/keys are unknown |
| Completed artifact with a concrete residual risk | result_reviewer for read-only inspection or reproduction_checker for numerical/execution checks | No automatic review panel or full rerun; freeze files under review |
| Demonstrated defect | Resume its production owner for a targeted fix, then validate the affected result | Do not restart unrelated discovery or require an extra reviewer by default |

Each brief supplies a local objective, acceptance criteria, known source locations and checked ranges,
unverified assumptions, missing result, exclusions, input constraints, deliverable,
dependencies, and an exclusive output directory for execution, such as
`/workspace/production/source-a` or `/workspace/checks/join-a`. Source artifacts are identified by path/hash and left
unchanged until the batch returns. Checkers must not patch the author's files.
For an independent computation, avoid giving the candidate answer upfront; compare
the returned value in the Leader. Missing prerequisites should be reported, not
guessed. Keep space in the shared budget for integration and the final answer.

These are prompt-level coordination rules, **not** new file locks, automatic DAG
scheduling, per-directory ACLs, or automatic context sharing. Shell-capable roles can
write; even audit roles must not be described as read-only. Runtime parallelism,
budget enforcement and resume remain in the existing generic harness. Benchmark
decomposition guidance is added only to the delegated Leader prompt, not the solo
control. A scripted test checks four instances across three review templates actually
overlap, use separate fixture outputs, preserve the reviewed artifact and resume
the correct child even when two instances share the same template.

The v4 allocation guidance gives source inventory one owner by default and separates
source-quality checks, code checks, estimand challenges and numerical reproduction.
It does not eliminate independent verification: checkers may read the same raw data
and recompute without seeing the candidate answer. After a demonstrated defect, the
leader may repair and rerun affected checks. Source-independent questions may run
in parallel with discovery; dependent questions wait for evidence. No role sequence
is mandatory. V8 retains these safeguards while adding production capabilities;
existing tool grants and local/shared budgets are unchanged.

## Cache Design

`roles.py` is versioned as `kramabench-data-v9`. The same role systems and tool
schemas serve every domain/task. Dataset paths are always `/data` and `/workspace`;
task questions, IDs, host paths and timestamps are not inserted into the system
prefix. Each template's independent context can resume without rewriting history.
Different roles intentionally have different prefixes and tool sets; permissions
are not widened just to obtain cross-role cache reuse.
The larger catalog increases the Leader's static prompt and may spread calls over
more prefixes. Prompt/catalog revisions invalidate old prefix comparisons; compare catalog
hashes and measured token-weighted reuse, not role count alone.

V6 uses the harness's final-message summary baseline: a concise natural-language
reply authored by the child in its normal final turn and returned verbatim, without
the V5 four-section format or 150-250-word target. Routine successful checks remain
grouped rather than enumerated. Execution-capable roles save full tables/code/results
in their assigned directory and cite them; read-only roles reference existing
evidence without new write permissions. There is no truncation, history rewrite or
extra compression call. This does not shorten the root's required final JSON
submission or remove its self-contained pipeline code. See the harness design's
[baseline provenance and alternatives](leader-subagent.md#baseline-provenance-and-alternatives);
this is not an exact Claude Code, Codex or AutoGen system reproduction.

Manifests freeze templates, schemas, catalog SHA-256, Leader system text/length,
prefix hash, model, source digest and budgets. Traces contain the exact child system
messages and prompt lengths. `report.json` uses `analysis.cache.summarize` for
token-weighted cache reuse by role and first/later call. A stable prefix makes reuse
possible; it does not prove a higher cache-hit rate. Scripted usage is not a cache
measurement. Costs are zero for fixtures; real estimated costs require an explicit
pricing table and actual attributable costs remain unknown unless measured.

## Single Versus MAS

`make_session`, `run_task` and `KramaBenchSystem` accept `mode="single"` or
`mode="mas"` (default). The older `delegated=False` flag remains an alias for single.
Conflicting selectors fail before a run starts.

| Setting | Single | MAS |
|---|---|---|
| Runtime | Generic SingleAgent, same underlying Agent loop | Generic LeaderSubagent, same underlying Agent loop |
| Domain tools | All six approved tools | Same six for Leader; fixed subsets for children |
| Task/history | Full public task and own complete append-only history | Leader sees full task; children see local briefs and own histories |
| Delegation | None, no active templates or delegate tool | Eight selectable templates, bounded parallel delegation and resume |
| Default total budget | 40 model calls, 80 domain tools, 900 seconds | Same total, shared by Leader and all children |
| Final-answer reserve | One call inside the total | One call inside the total, protected from children |
| Workspace/evaluation | Fresh workspace, same input lake and response format | Separate fresh workspace, same input lake and response format |

Both root prompts include the same requirements/data/join/statistics/code/reproduction
checklist. Only MAS adds delegation guidance and the capability catalog. Single does
not receive conflicting child permission instructions. Role-specific child prompts
are still part of the MAS treatment, not an isolated context-only intervention.
Neither arm sees gold answers or the other arm's transcript/files. Full context is
not a promise of unlimited provider context or of automatically reading all files.

New manifests label conditions `single`/`mas`, with `context_mode`, `domain_tools`
and `active_templates`; the single active list and effective child limits are empty/zero.
The full catalog remains recorded as provenance, not injected into the single prompt.
Historical `leader_only`/`delegated` manifests are preserved unchanged. Both arms now
have before/after session workspace audits in addition to MAS delegation audits.

For a real pair, run the same public Task with two separately prepared workspaces
and explicit clients; pass identical model/config/pricing/input provenance. Do not
reuse the workspace returned by one run for the other. The adapter does not
automatically launch a second paid run or call a judge. Match request/tool ceilings,
then report actual token usage, per-role cache reuse, cost, latency, failures and
independent evaluation. Equal call ceilings alone do not equalize token cost or FLOPs.

The offline pair entry point is strictly scripted:

```sh
.venv/bin/python scripts/kramabench/offline.py --mode both \
  --output outputs/kramabench-single-mas-NEW
```

It writes separate `single/` and `mas/` attempts and a `comparison.json` checking
identical fixture task/data, model, domain catalog, source and budgets. It records
each arm's usage, cache fields, runtime, costs and lifecycle, not a benchmark score.
`--mode single` or `--mode mas` runs only the requested fixture arm. The fixed
single-then-MAS fixture order is not a real-model order-control protocol.

## Ownership

- `harness/data_tools.py`: reusable bounded directory/text/XLSX/PDF inspection.
- `harness/catalog.py`: generic serializable capability manifest and hashes.
- `harness/container_contract.py`: preflight for existing data containers; never provisions.
- Existing `harness/subagents.py`, `agent.py`, `execution.py`: orchestration,
  budgets, tool enforcement, resume, transport and workspace audit, unchanged here.
- `benchmarks/kramabench/tasks.py`: upstream pin and allowlisted public questions.
- `benchmarks/kramabench/roles.py`: benchmark-specific capabilities and answer contract.
- `benchmarks/kramabench/adapter.py`: native System bridge, attempts and response export.
- `benchmarks/kramabench/evaluation.py`: host-only deterministic scalar numeric scoring;
  never exposed to model containers or imported from the upstream paid evaluator.

## Data And Evaluation Boundaries

Only `id`, `domain`, and `query` are public Task fields; only `query` enters the
Leader's task message. Gold answers, answer types, reference subtasks/steps, runtime
and `data_sources` stay outside model contexts and containers. Each task sees the
complete corresponding domain input lake. Nonempty native `subset_files` is
rejected because it is an oracle condition, not normal discovery.

The upstream `Evaluator` constructs a GPT judge, and some metrics call models.
The upstream list scorer also contains an `eval` fallback. We neither import nor
execute that stack. `native_response.json` matches the executor's response shape
for a separately authorized evaluator. Execution reports retain `evaluation=not_run`.
A separate `grade.json` can apply the reviewed pinned scalar `numeric_exact` Success
branch without a judge. It binds submission and metric-source hashes, reports strict
target equality alongside the upstream tolerance, and does not verify the pipeline.
Unsupported types are rejected, not silently assigned zero. Any grade must name its evaluator revision,
authorized judge configuration and exact submission hash. Native pipeline scoring
must be treated as a separate paid action.

V7 replaces the V3 root-wide JSON mode with the same root-only `submit` tool in
Single and MAS. Its schema requires `answer`, `pipeline_code`, `evidence` and
`unfinished`; code is a self-contained script string, not a path. Intermediate
requests have no response-format constraint. Children cannot submit the root answer.
Invalid submissions produce visible tool errors and may be corrected within the
existing budget; a successful submit terminates without a follow-up model call.
Plain text, including JSON-looking text, is not automatically extracted as a
submission. On a text-only turn the root receives a visible submit reminder, not a
hidden summarizer or repair call. The final reserved call advertises only submit;
DeepSeek Chat Completions explicitly disallows forced named tools in thinking mode,
so the final request uses automatic selection without switching thinking off.
Failure to submit then is recorded, not retried beyond the budget. Mixed submit
and other-tool batches are rejected without executing any call in that batch.

The adapter strictly validates and exports the accepted argument object as JSON;
this checks transport shape, not code correctness or answer truth. Manifests freeze
the schema and final-tool policy. Reports include `termination_reason`, `failure_stage`,
`submission_status` and encountered `budget.limit_events`. Historical attempts remain
immutable. The new provider combination has not been tested with a paid model.

XLSX inspection supports zero-based row `offset`, `limit` (default 10, maximum
100), and column windows using `column_offset`/`column_limit` (default/maximum 50).
Returned row/column offsets and dimensions permit read-only roles to inspect beyond
the first preview. Oversized previews are explicit tool errors, not silent success.

## Runtime Contract

Run on the project server only. Supply an already provisioned, trusted disposable
container, with no embedded credentials or reference solutions. Preflight requires:

- Network mode `none`, nonprivileged, no host PID/IPC namespace or added devices/capabilities.
- Exactly two bind mounts: the selected input directory at `/data` read-only,
  and a separate writable `/workspace` containing only a fresh, history-free `.git`.
- Python 3, Git, shell, `timeout`, and the task's analysis dependencies in the image.
  XLSX preview requires openpyxl; PDF preview requires pypdf. Other binary/geospatial
  formats require analyst code and appropriate preinstalled libraries. No package is
  silently installed. No image, environment or dataset is provisioned by the adapter.
- A host-side `archive_dir` for paged outputs, outside the two mounts. Traces,
  workload metadata, evaluator code and `.env` must never be mounted into the container.

Preflight records image identity and dataset file hashes. The provisioner must also
freeze resource limits, dependency versions and dataset acquisition manifest before
real runs. Do not mount the upstream repository wholesale. A shell grant can access
all contents available in its container; tool permissions are not hard isolation.
Read-only reader operations are not a hostile-filesystem security sandbox. Workspace
audits show shared intervals, not exclusive attribution under concurrent writes.

`KramaBenchSystem` implements `process_dataset` and `serve_query` without importing
upstream. It takes an explicit client and workspace factory; the factory returns a
fresh existing `ContainerWorkspace` per task. Direct `run_task` additionally accepts
provenance from `load_tasks` and an optional pricing table. Custom query calls are
labelled unverified unless provenance is supplied. Neither API creates an evaluator.

```python
tasks, provenance = load_tasks(upstream)
task = next(t for t in tasks if t.id == selected_id)
# Run only after explicit model/run authorization and container preparation.
workspace = ContainerWorkspace(container_name, archive_dir=retained_output_path)
response = run_task(task, client=client, workspace=workspace,
                    dataset=domain_input_path, output=new_attempt_path,
                    provenance=provenance, pricing=frozen_pricing)
```

For source-only preparation, fetch the pinned upstream Git checkout separately and
use sparse checkout for `workload` and `benchmark`. Full environment preparation
also includes the pinned `data` tree. Do not fetch/mount solutions.
Source sync excludes `upstream/`, assets, environments and outputs. On the server:

```sh
.venv/bin/python scripts/kramabench/catalog.py \
  --upstream benchmarks/kramabench/upstream --output outputs/kramabench-catalog-NEW
.venv/bin/python -m pytest -q
.venv/bin/python scripts/kramabench/offline.py --output outputs/kramabench-offline-NEW
```

The offline script computes an average from a synthetic CSV using a fixed trusted
fixture operation, exercises parallel selection, permissions, continuation and
trace/export paths, and never executes arbitrary model commands or calls a model.

## Prepared Environment

Preparation evidence: `outputs/kramabench-prepare-20261101-02` on the server.
All 1,742 input files in the pinned Git tree were checked against Git blob IDs and
SHA-256, totaling 666,850,039 bytes. Counts by domain: archeology 5, astronomy 1,538,
biomedical 8, environment 37, legal 132, wildfire 22. These are the exact pinned
repository counts, not the README's rounded historical data-size summary.

Dedicated image: `mas-information/kramabench:20261101-v1`, ID
`sha256:e853321226dc4653164fff8f7e723a86df1a9e2aca282e649dfe2a9a1b144f6c`.
The base was pulled from `docker.1ms.run`, with its digest recorded; Python packages
used the Tsinghua mirror. `packages.txt`, Dockerfile/build log, full input manifest
and format-smoke receipts are retained. Tests read all inputs and opened all XLSX,
GPKG, CDF and NPZ files with the installed libraries; this is not a proof that every
one of the 104 scientific pipelines will execute correctly. No reference solution
or provider credential was built into the image. Historical images were untouched.

The first build attempt (`...prepare-20261101-01`) failed before package installation
because BuildKit rejected `--network bridge`; it is retained rather than overwritten.
The successful build used BuildKit's default network. Runtime containers use network
mode `none`, 2 CPUs, 4 GiB RAM, 128 PIDs, dropped capabilities, the host user's UID,
read-only domain input and a fresh independent Git workspace per arm.

`scripts/kramabench/pilot.py` requires `--execute-paid` and explicit run authorization.
It validates both environments and their matched contract before dispatch, persists
failures, stops after fatal provider errors and removes only its own containers.
No monetary ceiling is imposed for the specifically authorized pilot; finite
request/tool/time limits remain, and retries are zero. A preflight-rejected arm has
not made a model attempt and must not be scored as a model failure. Continuation of
an entirely unstarted MAS arm requires the original evidence and a one-time claim;
it never replays the Single arm and records source revision changes explicitly.

## Verified Evidence

Initial v1 server verification on 2026-11-01 (single-threaded numerical libraries):

- Full repository tests: `103 passed`.
- Pinned public workload export: `outputs/kramabench-catalog-20261101-01`, 104 tasks.
- Scripted adapter smoke: `outputs/kramabench-offline-20261101-01/attempt`.
  It made 15 scripted completions and 5 delegations including one resume;
  status `done`, `infra_affected=false`, trace integrity errors `[]`, actual cost $0.
- No real model, native judge, data-container deployment or full benchmark run.

V2 server verification on 2026-11-01:

- Full repository tests: `114 passed`, including all nine role permission/prefix
  cases and a barrier-synchronized four-role parallel check with same-child resume.
- Scripted adapter smoke: `outputs/kramabench-roles-v2-20261101-01/attempt`;
  catalog `kramabench-data-v2`, nine templates, status `done`, no trace integrity
  errors, `infra_affected=false`, actual cost $0.
- These fixtures verify dispatch and permission mechanics, not whether a real
  Leader selects better subtasks or whether specialists find more genuine errors.

Single/MAS server verification on 2026-11-01:

- Full repository tests: `127 passed`. New coverage checks full single-context
  reasoning/observation retention, forbidden delegation, final-call budgeting,
  provider-failure audits, explicit mode compatibility and independent paired workspaces.
- Paired scripted evidence: `outputs/kramabench-single-mas-20261101-01/comparison.json`.
  Single used 4 scripted completions/3 domain actions; MAS used 15/5. Both reported
  `done`, with empty trace-integrity errors and no infrastructure impact. Matched
  task/data/config budgets were checked, and both fixture answers were 4.
- Costs were $0, with no real-model token/cache measurement or official evaluation.
  The fixture call counts and answers are wiring checks, not an efficiency result.

Comparison review fixes, server verification on 2026-11-01:

- Full repository tests: `148 passed`. Coverage includes artifact/input/workspace
  overlap rejection before trace creation, terminal failure reports, failed-request
  accounting, audit-only deadline exclusion and concurrent execution accounting,
  matched real-container contracts, scalar numeric scoring and canonical mount order.
- Docker mount arrays are sorted by destination before comparing environments;
  inspect output order alone is not environment drift. Real changes still reject
  before a request, with the differing fields named in the error.
- Failures with missing provider usage retain an unknown full cost rather than a
  misleading zero; known-receipt subtotals remain separately available.

## Paid Engineering Pilot

On 2026-11-01, the authorized `deepseek-flash` pilot ran `archeology-hard-1` once
per mode. Both arms used 64 shared model calls, 120 domain-tool calls, 1,800 seconds
of execution time, a separate 120-second audit allowance, and no monetary cap.
MAS allowed four concurrent children, eight identities and sixteen delegations.
Provider retries and paid judge calls were zero. No attempt was rerun.

| Measurement | Single | MAS |
|---|---|---|
| Model attempts / provider errors | 11 / 0 | 42 / 0 |
| Domain-tool calls | 14 | 51 |
| Prompt / completion tokens | 96,486 / 6,756 | 508,449 / 66,154 |
| Largest prompt | 14,800 | 33,191 |
| Token-weighted cache reuse | 89.68% | 79.30% |
| Receipt-based estimated USD | 0.005806884 | 0.056689350 |
| Execution seconds (excluding audit-only intervals) | 64.71 | 370.58 |
| Valid submission | Yes | No: prose and fenced JSON instead of strict JSON |
| Scalar numeric score | 0 | Not graded; no valid submission |

Single predicted 8347.1887 against the pinned target 8577.5298. MAS ended with
`JSONDecodeError`; its runtime lifecycle was `done`, but that is not submission
validity or correctness. The original text is retained in the trace, with no
post-hoc extraction, repair request or regenerated answer. Neither submitted
pipeline was independently re-executed. No upstream paid pipeline scoring was run.

MAS selected four children and reached two overlapping delegations; no real-model
resume occurred, so resume evidence remains scripted. Per-role call count, maximum
prompt and token-weighted cache reuse were:

| Role | Calls | Maximum prompt | Cache reuse |
|---|---|---|---|
| leader | 12 | 33,191 | 90.94% |
| requirement_analyst | 5 | 8,657 | 73.60% |
| data_scout | 7 | 21,051 | 77.95% |
| reproduction_checker | 10 | 15,297 | 74.03% |
| data_quality_auditor | 8 | 25,736 | 59.04% |

Evidence and interpretation boundaries:

- Single: `outputs/kramabench-paid-single-mas-20261101-01/single`.
- MAS: `outputs/kramabench-paid-mas-continuation-20261101-01/mas`.
- Combined verification: `outputs/kramabench-paid-mas-continuation-20261101-01/verification.json`.
- The first MAS launch was rejected by environment preflight with zero requests.
  Its original summary incorrectly included a missing-submission zero; the combined
  verification explicitly treats that arm as unstarted/unscored and preserves the
  original evidence. Mount-order-sensitive comparison was fixed before continuing
  only the unstarted MAS arm. The original rejected snapshot was not retained, so
  mount order cannot be established as the sole historical cause of that rejection.
- Source digests differ (`a4097e702d1e8e56` versus `47c8d97933f7dae0`). Task, model,
  tools, prompts, budgets, image and data matched, but this is an engineering pilot,
  not a strict frozen-source comparison or evidence of a MAS/cache advantage.
- All 53 provider calls have usage receipts; total estimated cost is $0.062496234.
  Account-wide balance deltas were CNY 0.00 and 0.14 respectively, not attributable
  per-run actual costs. Pricing is frozen in each launch manifest; invoice-level
  attributable costs remain unknown.
- Both traces pass integrity checks and record `infra_affected=false`. All four
  owned containers were removed and independently checked absent. Inputs, image,
  workspaces and immutable traces remain on the server. Final server tests again
  passed: `148 passed in 2.26s`.

Post-pilot offline analysis and v3 fixes: [failure analysis](kramabench-pilot-analysis.md).
The reference script did not reproduce its gold answer in the pinned environment;
do not use this task for acceptance claims until that reference ambiguity is resolved.
Server verification after the fixes: `167 passed in 2.50s`, plus real-XLSX paging
smoke in the existing image. No new paid requests; historical scores are unchanged.

V4 scoped-delegation prompt verification on 2026-11-01: `169 passed in 2.57s` on
the server. New scripted coverage checks generic/MAS-only policy placement, stable
child prefixes, local briefs without the root-only answer, parallel code review and
raw-data recomputation, then an allowed leader repair and same-child targeted
recheck. The fixture does not restart file discovery, but deliberately re-reads raw
data for independent verification. This checks prompt delivery and workflow
compatibility, not real-model compliance or measured cost savings. No paid calls.

V5 compact-report server regression on 2026-11-01: `174 passed`. Coverage includes
unchanged overlong reports in leader context and trace, full reasoning/tool history
on resume, detail-file references without automatic loading, read-only permissions,
forced-final reminders, partial output and no additional compression/repair calls.
JUnit receipts are in `outputs/kramabench-summary-v5-20261101-01/regression.xml`
and the final verification directory `outputs/kramabench-summary-v5-20261101-02`.
These are scripted checks only; no paid requests or measured cost-saving claim.

V6 final-message summary baseline verification on 2026-11-01: `175 passed in 2.65s`
on the server. Added coverage rejects the old required section schema and numeric
word target; natural-language report fixtures preserve the same verbatim transport,
resume history, permission boundaries and call counts. Receipt:
`outputs/kramabench-summary-v6-20261101-01/regression.xml`. No paid requests;
summary quality, information loss and real-model cost changes remain unmeasured.

V7 review fixes verified on 2026-11-01: `191 passed in 2.70s` on the server.
Receipt: `outputs/kramabench-review-v7-20261101-04/regression.xml`. Coverage includes
atomic per-delegation report reservations, exhausted shared budgets with child and
leader reports, early/error release, resume usage deltas, single-count child errors,
mixed parallel groups with serial barriers, actual final-limit turn counts, and
root-only submission validation/correction without extra calls. Non-finite values,
duplicate argument keys, mixed submissions and unsupported forced thinking-mode
tool choices are rejected. Generic schema/termination/permissions remain in the
harness; KramaBench owns the submit fields and exported payload.

Paired scripted smoke: `outputs/kramabench-review-v7-paired-20261101-01/comparison.json`.
Both independent workspaces exported valid fixture answers (4), matched input/config
contracts, had empty trace-integrity errors and `infra_affected=false`. Single used
4 model calls / 3 domain actions; MAS used 15 / 5. Submission is an unbudgeted control
tool, not a domain action. No paid model or judge was called, and no real-model
submission reliability, token/cache savings or efficacy claim follows from this smoke.

V8 production-delegation verification on 2026-11-01: `209 passed in 2.85s`
on the server. Receipt:
`outputs/kramabench-production-v8-20261101-03/regression.xml`.
New coverage exercises early `data_preparer` / `calculation_worker` dispatch before
root implementation, overlapping tool execution with disjoint output directories,
then a `pipeline_analyst` consuming ready artifacts and root-only read/integrate/submit.
It checks local contexts, fixed grants/prefixes for all eleven templates, exact shared
call accounting, valid traces and continued direct execution in both Single and MAS.
Existing independent-check, repair/resume, report-reservation and submission tests
remain passing. Scripted policies establish workflow compatibility, not spontaneous
model allocation, correct real-task calculations or a measured speedup.

The existing paired transport smoke also passes:
`outputs/kramabench-production-v8-paired-20261101-01/comparison.json`.
Both arms are `done`, `infra_affected=false`, with empty trace-integrity errors and
zero cost. This legacy fixture deliberately exercises review/resume as an allowed
path, not the new default allocation recommendation. No paid model/judge, new
environment or container was used. Root domain tools, common task/analysis/submit
contracts, shared budgets and workspace isolation are unchanged; the V8 catalog
and delegation prompts are a new MAS treatment and invalidate direct prefix/cache
comparisons with V7 without a newly frozen paired experiment.

V9 consolidated-role verification on 2026-11-01: `207 passed in 2.77s` on the
server, receipt `outputs/kramabench-roles-v9-20261101-01/regression.xml`.
The count reflects three fewer parameterized catalog entries and one new regression.
Coverage checks the three merged capability contracts, unchanged read-only/execution
grants, rejection of retired names without model calls or budget consumption, and
four concurrent instances including two data auditors with separate scopes and
identity-specific resume. Existing production, Single/MAS, budget and submit tests
pass. No paid calls; no measured latency, accuracy or cache improvement is claimed.

These paths are relative to `/home/zhoujunye/MAS-information` on the server.
