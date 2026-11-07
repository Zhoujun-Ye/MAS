# Three-Benchmark Engineering Smoke

Authorized on 2026-11-07 after the boundary audit: first two frozen Validation20
tasks per benchmark, Structured and FULL once each. Twelve solver attempts,
at most twelve model grades, no automatic recovery/retries. Current selection
requires at most ten model grades; two HDR SQL grades are deterministic.

Protocol: `cpu8-infra-protocol.json`, eight CPUs/four compute threads per solver,
eight solver slots in total and two judge slots, DeepSeek Flash/high. Existing
timeout/prompt/scoring policies and task order stay unchanged. Estimated admission
cost is CNY10, safety factor 1.5, reserve CNY5; this is not a hard invoice cap.

Stage: `/home/zhoujunye/mas-stages/20261107-threebench2-engineering-01`.
Run: `/home/zhoujunye/mas/outputs/threebench2-engineering-20261107-01`.
Offline receipts: `/home/zhoujunye/mas-data/receipts/matrix-deep-audit-20261107/`.

## Boundary Audit

Before paid launch, 687 offline server tests passed in 26.75 seconds. The native
DataClaw/HDR Structured/FULL synthetic workflows also passed (four real-container
cases, no real keys or provider calls). The first regression caught a misplaced
cross-benchmark finalization helper; it was moved into the study driver layer,
without weakening the layout test.

Additional repairs:

- Malformed, unavailable, nonfinite, duplicate-currency or mismatched balance
  observations produce unknown accounting, not a finalization crash or zero cost.
  Initial paid admission remains fail-closed and strict balance arithmetic remains
  available separately.
- Quiescence checks include orphan graders' `--output` and `--run` arguments, not
  only solver output paths. Replay containers now also have host ownership receipts.
- A crash between terminal solver report and summary/prediction export is repaired
  offline into a fresh child-run namespace. Old raw artifacts remain unchanged;
  frozen inputs are rechecked. Existing paid grading claims block automatic repair.
  No solver is repeated and no answer is chosen or rewritten semantically.

The added tests cover orphan child processes, before/after accounting gaps,
changed-input rejection, all three benchmark terminal exports, stale predictions
and a hard process crash after the solver report. Prior tests cover multi-generation
continuation, unknown paid dispatch, one-time explicit judge recovery and operator
interruption. These are engineering checks, not proof of real-model efficacy.

## Paid Scope

Task IDs, exact source/config/image/proofs and concurrency are frozen in the launch
plan and run authorization. Preserve this paid run, failed calls, accounting and its
source stage. Do not recover failed attempts without another run-specific approval.
Scores, durations, resource observations and cost coverage will be reported from
completed artifacts, not inferred from CLI lifecycle alone. Six reused validation
questions cannot establish benchmark-wide quality or absence of every possible bug.

## Completed Run

The driver finished at 2026-11-07 12:33:02 UTC (07:33:02 America/New_York), exit 1
because two authorized attempts timed out. No attempt was repeated. All twelve
solver and twelve grading journal phases have terminal records; ten solvers exited
normally. Five model judges were dispatched, below the authorized maximum. The
batch took 30.33 minutes from authorization persistence through final summary.

The first eight solvers started within 0.12 seconds. Grading overlapped remaining
solvers. Sum of individual solver times was 152.81 minutes, not serial batch wall time.

| Benchmark | Structured Mean CLI Min | FULL Mean CLI Min | Outcome |
| --- | ---: | ---: | --- |
| DataClaw | 5.78 | 9.50 | Both conditions: 2/2 completed, mean score 1.00 |
| HDR | 28.11 | 26.78 | Each condition: one completion and one 30-minute timeout |
| Krama | 3.27 | 2.97 | Both conditions: 2/2 completed, mean score 0.953846 |

HDR completed Structured SQL and FULL text answers both scored zero. The timed-out
FULL SQL attempt received an extraction-failed deterministic verdict on its empty
prediction; the timed-out Structured text prediction has no model verdict. Preserve
that distinction rather than turning unknown grading into a successful completion.
The table includes timeout duration. FULL gate acceptance with coverage unknown is
not semantic correctness or evidence of successful completion.

HDR request P95 latency ranged from 75 to 146 seconds, with maximum 222 seconds.
For each HDR attempt, the union of intervals with at least one upstream model
request in flight covered 98.4-99.0% of its solver wall time. This includes provider
generation/streaming and may overlap tools; it is not pure network latency or proof
of provider fault. Average HDR container usage was only 0.056-0.118 cores. All twelve
attempts recorded zero CPU throttled seconds and no observed OOM. More CPU slots
cannot by themselves shorten these four model-bound task trajectories.

No upstream model HTTP 5xx, fatal-provider stop, balance pause, monitor failure,
grading crash or duplicate dispatch was observed. Four web fetch responses were
HTTP 404; these were retained external-page failures, not model API failures.
All owned containers were removed. Timeouts still constitute incomplete work.

Shared-account balance snapshots changed from CNY67.19 to CNY54.48, a CNY12.71
interval delta including solver/judge/web activity, not an attributable invoice.
Per-condition token-cost totals remain unknown where interrupted streams lack
complete usage; reported known subtotals must not omit those incurred calls silently.

After the run, each benchmark's real terminal artifacts were used for an offline
export-crash drill. All three recovered the same answer/grade (and Krama replay
result), without model calls or changing original reports. Temporary crash copies
were deleted; `real-artifact-finalization.json` retains the verification receipt.
Public score/operational export: `matrix-deep-audit-20261107/paid-report.json` and
`matrix-deep-audit-20261107/report/`, outside the immutable raw run. The frozen paid
source stage was not edited after launch.
