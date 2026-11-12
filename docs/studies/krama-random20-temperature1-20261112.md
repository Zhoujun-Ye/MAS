# Krama Random20 Temperature 1.0 Rerun

## Authorization

The November 12 user request authorizes source deployment and one new attempt
on each frozen Random20 question for Single, Native and Structured: exactly
60 solver slots, zero retries/replacements, and at most six one-call semantic
judges with zero retries. No monetary cap was requested; the user instead asked
for active progress/error/cost monitoring and prompt investigation of problems.
Estimate-based balance admission and fatal-key/balance checks remain enabled;
they are not a provider hard spending cap.

Thinking disabled, temperature 1.0, effort not applicable, no loop detector or
loop interventions. Native recording and strict-Single permissions remain.
Use the exact existing organization prompts, fixed twenty task IDs/fingerprints
and task order. The original T=0 manifest/protocol and all historical paid
results remain unchanged. The new explicit protocol differs from that historical
protocol only in temperature; this is a new protocol, not a replacement result.

## Runtime

- Source base: commit `3975b70`; freeze full source hashes before dispatch.
- Frozen source: `/home/zhoujunye/mas-stages/20261112-krama-random20-t1-01`.
- Output: `/home/zhoujunye/mas/outputs/krama-random20-20261112-01`.
- Receipts: `/home/zhoujunye/mas-data/receipts/krama-random20-20261112-01`.
- Solver concurrency 16; independent grading concurrency 2, overlapping solving.
- Each solver CPU8/thread4, 8 GiB, network=none; existing pinned image/CLI.
- Krama limit 3600 seconds; replay 180 seconds; no shorter study-specific cap.
- Model/judge APIs remain server-direct; no local-Mac web dependency for Krama.

Only `legal-easy-25` and `wildfire-hard-18` require semantic grading: at most
two eligible IDs times three conditions, six one-call judge pairs. The generic
matrix's conservative `--authorized-judges 60` grading-enable switch is not
permission for sixty judge calls; freeze and verify the six eligible pairs and
host scoring types before dispatch. No additional paid smoke is authorized.

Preflight all sixty task/condition slots before model dispatch. Fresh native
proofs must verify main/worker thinking disabled, T=1.0, no loop state/feedback,
and exact image/binary/tool/environment bindings. Launch detached from SSH and
record the controller's terminal exit status. Keep failures, partial usage and
account-wide balance deltas; unknown accounting is not zero. Do not alter the
paid source or replay failed solvers/judges while fixing issues.

This repeats a previously inspected diagnostic set, not an independent held-out
test. Lifecycle/delegation audit and final-answer correctness remain separate.

## Completed Results

Completed all 60 solver slots and all six authorized one-call judges, zero
retries. Detached wrapper PID 2555735, matrix PID 2555736. Execution ran
November 12, 00:59:43-01:18:54 America/New_York (19m11s including preflights).
Both processes exited and all owned containers were removed. All sixty free
task preflights passed before paid dispatch. No source change occurred during
execution. Verification and exit-status receipts are outside the frozen source.

| Condition | Original Answer Mean | Full Score | Native Audit | Replay Exited Zero And Matched |
| --- | ---: | ---: | ---: | ---: |
| Single | 53.33% | 10/20 | 20/20 | 20/20 |
| Native | 80.00% | 16/20 | 19/20 | 18/20 |
| Structured | 71.67% | 13/20 | 20/20 | 18/20 |

These are original answer metrics over all twenty selected tasks, including
partial list F1, not a claim that all artifacts or native conditions succeeded.
The generic report's compliant-score columns apply the existing Single-only
violation rule; they do not certify Native/Structured compliance. In particular,
Native's 80% includes a correct answer without delegation. Do not silently drop
that question from one condition or describe the run as fully compliant.

Recorded exceptions, with no repair, replacement or paid replay:
- Native astronomy-easy-5 answered correctly but started zero subagents: native
  condition unverified. Hooks and native statistics agree, not an audit-ID bug.
- Structured biomedical-hard-8 produced neither submission nor pipeline. Lead
  text said it was waiting; native statistics recorded its worker killed by
  system. Answer score remains zero. Aggregate termination accounting passes
  structural audit but is not proof of completed worker work or quiescence.
- Native biomedical-hard-7's submitted answer scored one, but replay failed
  because the generated script named a nonexistent Excel worksheet.
- Native legal-hard-24 and Structured wildfire-hard-18 replay exited zero but
  their printed answers did not exactly match the respective submissions.

The controller returned 1 because not every solver passed native condition
audit, not because dispatch crashed or slots were missing. Summary interruption
is false; no controller/monitor failure occurred. All model HTTP statuses were
200; no outer solver deadline expired. There were 1391 host-dispatched solver
requests, all thinking disabled/T=1/effort absent, with no loop fields/state in
hooks. 1390 streams completed and one was cancelled when the Native legal-easy-25
lead used native TaskStop on its worker; partial usage remains unknown.
Finite completion is not proof that every repeated investigation disappeared.

Immediate account-wide balance decrease was CNY9.07; follow-ups at 01:22:18 and
01:25:21 America/New_York observed **CNY9.35**. This is not an attributable final
invoice, and complete cancelled-request billing is unknown. No per-condition
invoice or causal cost gain is inferred. Retained-message token-weighted cache
reuse was Single 96.59%; Native lead/worker 89.11%/90.99%; Structured lead/worker
92.78%/92.95%. Mean initial prompt UTF-8 sizes were 1472.3/1500.3/3853.3 bytes
for Single/Native/Structured. These usage observations are not billing coverage.

Receipts include `verification.json`, `operational-metrics.json`,
`billing-followup-final.json`, `exit-status.json`, and sanitized report/CSV
exports in `report/`. Raw submissions, native traces, ledgers and the frozen
paid source remain protected. This completed scope does not authorize a rerun.

## Subsequent Audit

The [anomaly investigation](krama-anomaly-audit-20261112.md) identified the native
ten-minute background-wait ceiling as a harness configuration omission in the
Structured missing-submission case. The corrected read-only audit marks that
attempt unverified, yielding Structured 19/20 rather than the originally
recorded 20/20 lifecycle passes. The original table above and paid raw audit are
retained as historical observations; original answer scores do not change.
Future code removes the hidden ceiling, improves pipeline diagnostics and
clarifies report labels. Server tests and synthetic controls are free; no paid
attempt was resumed or replaced and no performance recovery is claimed.
