# November 11 Infrastructure Review Fixes

## Authorization And Scope

The user requested correction of the supplied eleven-point infrastructure review,
then authorized isolated server verification and launch of the already specified
fresh Krama Random20 after the fixes. Inspection found no running MAS solver,
matrix process or Docker container and no Random20 paid output namespace.
No existing experiment needed interruption. Paid evidence is not edited or rerun.
The original Structured and Native organization strings, selected IDs, seed,
zero-retry policy and CPU8/thread4 allocations remain unchanged.

## Disposition

1. **Tool surface:** both adapters use explicit tools and disable slash commands.
   Single has twelve base tools; Native/Structured add native delegation and peer
   communication only. The pinned CLI exposes Task as the Agent alias, so actual
   init contains fifteen tools, no skills and no slash commands. Proofs retain
   these lists and bind the environment/options digest; stale proofs fail admission.
2. **Aliases:** FABLE and HAIKU now use `deepseek-flash[1m]`, like OPUS/SONNET.
   The fake-provider probe accepts an explicit worker alias for native validation.
3. **Upstream 5xx:** per-attempt reports and read-only aggregate exports carry
   `infra_degraded`, request IDs/statuses, and unknown-evidence counts. Status and
   scores remain separate; no automatic retry, exclusion or historical replacement.
4. **Single audit:** a missing SessionEnd no longer replaces `timed_out` or
   `cli_error`. Successful-but-unverified runs use `native_condition_unverified`,
   just like Subagents, preserving the same semantic-judge eligibility. Confirmed
   delegation still blocks Single admission and is separately recorded.
5. **Krama shutdown:** stop the owned solver container immediately after the CLI
   returns, before audits or snapshots. `docker exec` termination alone is not
   treated as container quiescence. Cleanup failures remain failures.
6. **Web readiness:** up to three free, bounded TLS checks precede dispatch.
   A historical proxy failure no longer permanently trips the balance pause for
   unrelated jobs. Each future web launch still fails closed on current readiness;
   no direct fallback and no automatic replay of started work. A failed web fetch
   does not prove the attempt had no earlier paid model calls.
7. **SQL:** remove the hidden ten-million-operation default. Read-only protection,
   output truncation and the outer solver deadline remain. Optional `--operations`
   gives an explicit cap with an actionable error instead of bare `interrupted`.
8. **Bash:** set the same native default/max timeout to ten minutes in all
   conditions. This mitigates automatic two-minute handoffs but cannot prevent
   explicitly backgrounded commands or model-selected shorter timeouts. Preserve
   background-shell observations and do not fabricate lifecycle success.
9. **Scheduling:** matrix Krama runs defer offline evaluation to the grading pool.
   Replays and solvers share a bounded CPU reservation semaphore, so this does not
   overcommit CPU8 allocations. Matrix-managed children omit redundant balance
   requests. Optional `--schedule-estimates` enables stable, condition-neutral
   longest-first order from an explicitly frozen complete per-task seconds list.
   The current Random20 retains its authorized manifest order; do not estimate
   its durations from its own outcomes or silently reorder the frozen study.
10. **Small fixed overheads:** retain the existing TLS transport and record-only
    hook coverage. The review reports a 1-3% contribution, not a correctness
    defect. A keep-alive rewrite under zero retries risks stale-connection failures;
    removing hooks loses audit evidence. Neither speculative change is required
    to correct the measured comparison. No latency improvement is claimed here.
11. **Scoring:** accept an entire JSON code fence as well as plain JSON for the
    one-call semantic judge, still requiring exactly one boolean `equivalent`.
    Do not salvage arbitrary prose or retry malformed answers. New Krama timeout
    outcomes receive zero and no semantic judge; retain the submission and raw
    diagnostic artifact grade. Historical metrics/results remain read-only.

## Verification

Source stage: `/home/zhoujunye/mas-stages/20261111-review-fixes-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/review-fixes-20261111-01/`.
Tests run only on the server using the existing evaluation environment. Native
probes use synthetic host credentials, a fake provider and network-disabled
containers. Free native proofs do not establish task accuracy, real-provider
latency, absence of every possible runtime failure or a comparative gain.

The paid plan remains twenty fixed questions times three conditions, sixty
solvers, sixteen solver slots, zero retries and at most six one-call semantic
grades. No extra paid smoke is added. Fresh source-bound preflights and admission
proofs are required before launch. Validation results and launch state are added
after observation, not inferred from code inspection.

Observed free verification:
- `pytest-final.xml`: 921 tests passed, two skipped; server evaluation Python.
- `native-proofs-02/`: both pinned native adapters passed observed surface,
  inference policy, credential isolation, shell and delegation-policy checks.
- `alias-fable/` and `alias-haiku/`: native workers launched successfully; every
  captured model request selected `deepseek-flash`, with the CLI aliases configured
  for the one-million-token window. Both adapters passed in each probe.
- `three-conditions-final/`: Single/Native/Structured all passed exact prompts,
  native audits, real input mounts, deferred offline replay and CPU8/thread4 capture.
- `external-six/`: DataClaw, HDR and FDABench, each in Single/Structured, passed
  native input/tool/submission workflows. These are synthetic answers, not accuracy tests.
- `503-conditions-final/`: exactly one request per condition, no retry,
  `cli_error` preserved and `infra_degraded=true` recorded in all three.

The first surface proof correctly rejected the unexpected Task/Agent alias
representation; validation now handles the observed native alias without allowing
extra tools. An intermediate workflow exposed lost final cgroup sampling after
shutdown; the final version closes the resource sampler before stopping the
container, still before any native audit, and all nine workflows captured resources
without sample errors. These failed intermediate checks remain diagnostic evidence.

Paid source was frozen at
`/home/zhoujunye/mas-stages/20261111-krama-random20-fixed-01` and output at
`/home/zhoujunye/mas/outputs/krama-random20-20261111-01`. Starting that source must
not modify it during the run. The driver performs all sixty free task preflights
before its first paid dispatch. No additional paid diagnostic is planned.

The authorized driver was started with PID `1744295`. All sixty task preflights
passed and balance admission succeeded before dispatch. The first observation
found seventeen attempt reports (two `cli_exited`, fifteen `running`) and no
controller failure. This is startup evidence, not a final result. The adjacent
`.launcher.json` records the exact six eligible semantic-judge pairs; no additional
solver or judge retry is authorized. Source remains frozen during execution.

## Follow-up Review Corrections

A subsequent review identified three remaining paths; the user requested their
correction. These patches are separate from the already running frozen paid source.

- External Single finalization now checks positive violation evidence before
  downgrading missing lifecycle evidence. Worker starts, executed/exposed delegation,
  member transcripts, Teams evidence and member accounting mark
  `single_agent_condition_violated`. Such answers are not exported for evaluation.
  Original timeout/error lifecycle statuses remain intact with a separate condition
  flag; a missing SessionEnd alone remains `native_condition_unverified`.
- Standalone and matrix Krama semantic judges now use one eligibility predicate.
  CLI errors, timeouts, launch errors and confirmed Single violations cannot consume
  a semantic judge call merely because a retained artifact is `pending_judge`.
- On timeout, CLI error or interruption, both solver workflows stop the container
  before resource closure. Normal successful exits retain final resource sampling.
  Stopped-container capture omits the unavailable final sample and reports incomplete
  coverage instead of querying a destroyed cgroup or fabricating completeness.
  Sampler join is bounded to one second; Docker state reads occur only after stopping
  on failure paths, so they cannot prolong solver execution past that cleanup point.

Verification source: `/home/zhoujunye/mas-stages/20261111-review-followup-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/review-followup-20261111-01/`.
The full server suite passed **966 tests, two skipped** (`pytest-final.xml`).
Regression coverage includes positive violations versus missing evidence, standalone
judge admission, resource-recorded timeout/error/interrupt ordering in both workflows,
and a stalled sampler. No real provider calls were used.

`timeout-quiescence/proof.json` additionally exercises a real network-disabled Docker
writer with a synthetic adapter: the writer survived termination of its `docker exec`
client, but was stopped before deliberately delayed resource closure and did not write
through that delay. Container shutdown took approximately 0.21 seconds in this probe.
This establishes the tested Docker shutdown ordering, not native provider behavior
or a universal shutdown latency bound.

Deployment is scoped to the ordinary server source and this independent verification
stage. `predeployment-source.tgz` preserves seven overlapping production source files.
The paid stage `20261111-krama-random20-fixed-01`, its output artifacts and incurred
accounting remain unchanged. This patch does not retroactively validate that batch's
timeout cleanup and does not authorize paid replacements or another experiment.

## Single Compliance Export Correction

The next review found that a confirmed Single violation with a deterministic answer
score could still receive positive `compliant_score`. The user authorized correcting
this derived reporting bug. Raw answer grading remains diagnostic and is not rerun.

The report exporter now recognizes explicit violation status/condition flags and
positive native audit or member-accounting evidence across the attempt, matrix and
finalized summary. Confirmed Single violations receive `compliant_score=0` and
`protocol_accepted=false`, without removing tasks from the denominator. Original
`score`/`raw_score`, raw mean/full-score counts, costs and source evidence are retained.
Missing SessionEnd or a failed audit without positive violation evidence alone does
not receive this penalty; unknown protocol acceptance remains unknown. This does
not add a new Native/Structured admission rule or change a solver prompt.

Raw-run collection, old-export re-export (`--from-report`), direct aggregation and
JSON/CSV/Markdown output use the same compliance rule. The human-readable table
explicitly separates raw and compliant mean scores. Re-export writes only fresh
derived files; old exports and paid run artifacts are not overwritten. An older
export that discarded positive evidence should be recollected from its raw run,
not inferred to be a violation merely from `native_audit_passed=false`.

Verification stage: `/home/zhoujunye/mas-stages/20261111-compliance-report-fix-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/compliance-report-fix-20261111-01/`.
The final server suite passed **980 tests, two skipped** (`pytest-final.xml`).
Regression tests cover numeric/partial/unknown raw scores, late summary evidence,
contradictory cached audit records, legacy read-only results, missing lifecycle
evidence, unchanged costs, immutable inputs and all export/aggregation entry points.
No real provider call, paid regrade, solver retry or historical result rewrite is
part of this correction. Deployment is limited to ordinary server source; the
current paid source remains frozen.

## Final Review And Repository Cleanup

The user requested a full final review, repository cleanup and a commit only if
no further issue was found. Review covered the complete working-tree diff, the
native tool/environment proof binding, audit and grading eligibility, failure
shutdown, deferred replay/scheduling, derived compliance exports and retention.
No new actionable defect was identified within that scope.

Fresh verification source: `/home/zhoujunye/mas-stages/20261111-final-review-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/final-review-20261111-01/`.
The server suite again passed **980 tests, two skipped**. Both native adapter
admission probes, all nine synthetic benchmark workflows and all three 503
injections passed. Injections each sent exactly one fake request, performed zero
retries and recorded infrastructure degradation. This verification made no paid
provider calls and does not establish comparative model quality or every possible
native/provider failure behavior.

The retained Random20 summary was checked read-only: sixty finished solver slots
(fifty `cli_exited`, three `native_condition_unverified`, seven `timed_out`),
five semantic judge calls and no controller/grading exception. These outcomes are
retained failures/exceptions, not grounds for replacements or claims that all
attempts were correct. Its frozen source still matches its launch manifest.

Repository cleanup updated obsolete launch-state documentation. A source-tree
inventory found no disposable bytecode, editor backup, patch-reject or temporary
files to delete. Useful probes/tests and all paid evidence were retained. Ignored
`.env` (mode 0600), `.vscode/` and `outputs/` were intentionally preserved; none
is part of the commit. Frozen prompts, question manifests and protocol JSON were
unchanged. No server dataset, environment, image, tunnel resource, paid source or
paid result was cleaned or rewritten as part of this final repository cleanup.
