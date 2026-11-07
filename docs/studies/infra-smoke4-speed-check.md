# Paid Speed Check (2026-11-07)

The user authorized the same four tasks, Structured and FULL once each: eight
solvers total, up to eight scoring calls, no reruns. All eight solvers and grades
completed, process exit zero. Scoring was deterministic for these tasks, so paid
judge calls were zero. No source changes were made during execution.

Source: `/home/zhoujunye/mas-stages/20261107-krama-infra-smoke4-02`.
Output: `/home/zhoujunye/mas/outputs/krama-infra-smoke4-20261107-02`.
Exports, comparison JSON and report directory share that prefix. The comparison
is against `krama-infra-smoke4-20261107-01`, not the original 20-task batch.
Both paid source stages and original results are retained unchanged.

## Scope And Comparability

Same frozen manifest slice 0:4, question hashes, image/CLI, high effort, timeouts,
CPU8/container, four numerical threads/process, eight GiB/container, eight solver
jobs combined and two grading jobs. Structured's prompt is unchanged. FULL has
the explicitly authorized compact sharing, candidate-local read receipts, better
diagnostics, answer-format/wait guidance and conservative completed-worker wait guard.
First native observer timestamps span 08:51:12.599-08:51:13.335 UTC, confirming
parallel starts. The account interval including grading was 222.47 seconds (3.71
minutes), versus 356.43 seconds (5.94 minutes); offline preflights are excluded.

## Same-Task Results

| Metric | Structured before -> after | FULL before -> after |
| --- | --- | --- |
| Mean CLI seconds | 162.30 -> 150.79 (-7.10%) | 232.87 -> 173.55 (-25.47%) |
| Mean score | 0.976923 -> 0.976923 | 0.976923 -> 0.976923 |
| Full-score tasks | 3/4 -> 3/4 | 3/4 -> 3/4 |
| Average cores/container, time-weighted | 0.243 -> 0.249 | 0.311 -> 0.370 |
| Eight-core quota utilization | 3.03% -> 3.11% | 3.89% -> 4.62% |
| CPU quota throttled seconds | 0 -> 0 | 0 -> 0 |
| Model requests | 111 -> 122 | 178 -> 137 |
| Model output tokens | 112,653 -> 109,797 | 174,123 -> 135,831 |
| USD at same historical price scenario | 0.114558 -> 0.117581 | 0.187402 -> 0.140372 |

FULL output tokens fell 21.99% and scenario cost fell 25.10%. Its runtime overhead
relative to the contemporaneous Structured run fell from 43.48% to 15.10%.
Actual observed account balance delta was CNY 0.47, versus CNY 2.36 previously.
Account intervals are not authenticated per-run invoices. The USD estimate uses
the same historical token-price scenario, not an assertion about current tariffs;
do not infer an 80% attributable cost saving from account deltas.

| Task | Structured seconds before -> after | FULL seconds before -> after |
| --- | --- | --- |
| wildfire-easy-9 | 142.77 -> 149.15 | 96.36 -> 161.40 |
| astronomy-easy-1 | 116.60 -> 153.36 | 273.64 -> 168.77 |
| archeology-easy-11 | 146.87 -> 139.70 | 214.36 -> 150.17 |
| legal-hard-15 | 242.97 -> 160.93 | 347.14 -> 213.84 |

FULL improved on three tasks, but wildfire regressed 67.51%: model requests rose
24 -> 38 and output tokens 15,222 -> 41,192. Thus this is not uniform speedup.
All eight individual scores matched the prior run exactly; the wildfire partial
score remains unchanged, not silently counted as a fully correct answer.

## Mechanism And Engineering Checks

- All 259 model requests completed with HTTP 200 and observed usage. No automatic
  reruns, upstream 5xx, terminal crashes or degraded observation stores occurred.
- Eight native lifecycle audits passed, all gateway reconciliations matched, all
  CPU captures were complete, eight replayed pipelines matched their submissions,
  and owned containers were removed after completion.
- FULL placeholder sleeps fell from seven commands totaling 286.31 task-seconds
  to zero. Broader lexical inspection found no Bash commands containing `sleep`
  in any current attempt. The new wait guard was not invoked: the model did not
  request these waits. The paid run therefore supports changed behavior, not a
  measured saving attributable specifically to guard denials.
- FULL shared context fell 250,183 -> 103,834 emitted characters (-58.50%). This
  combines more compact messages with a different execution path (241 -> 169
  observation references); the controlled same-event offline reduction was 44.0%.
- FULL workspace tool errors fell one -> zero. All four consistency gates passed,
  but all four pools were nonconflicting. Candidate-local stale-read repair was
  therefore not exercised by a conflicting selection in this paid sample; its
  correctness evidence remains the offline tests and native fake-provider checks.
- There were twelve solver-produced Bash failures across the eight attempts,
  recovered within the original attempts. These are not twelve infrastructure
  crashes or additional benchmark reruns. Successful pipeline replay does not
  imply all intermediate commands succeeded.

## Conclusion And Limits

The repaired FULL was observably faster and cheaper on average in this paid
sample, without a score decrease. Unnecessary sleeping disappeared and generation
volume fell. Aggregate FULL output tokens per summed request-second were nearly
unchanged (143.21 -> 142.52), so a broad provider throughput improvement alone
does not explain the observed change. This ratio includes network/request overhead
and is not a direct model decoding benchmark.

This is still one stochastic attempt per task, not a statistically established
whole-benchmark speedup. Structured itself varied, and all modifications were
tested together. CPU remains lightly utilized; further improvements should focus
on redundant model work rather than simply raising CPU quotas. No further paid
experiments or solver changes were performed after this run.
