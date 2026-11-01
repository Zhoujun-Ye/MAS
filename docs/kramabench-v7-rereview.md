# V7 Review And Same-Task Paid Rerun

2026-11-01. Review plus one authorized `archeology-hard-1` attempt per arm.
No harness source was changed during this review or between the paid arms.
No model retry, paid judge, added sample or independent submitted-pipeline replay.

## Review Finding

**P2: the shared-budget final notice is appended after input-capacity preflight.**
`harness/agent.py:358` checks the existing messages; `:371` subsequently appends the
reserved-final notice and final prompt. The capacity estimate therefore does not
cover the complete dispatched request on that path. This can matter near a context
boundary, particularly for a long root history; reserving a request does not itself
reserve context space. Account for the possible final notice before admission, or
validate the exact final request with correct local-rejection budget accounting.

A server-only scripted probe demonstrated the accounting gap: preflight estimated
502 input tokens with a 503-token configured window and one reserved output token;
the dispatched messages estimated 741 using the same method. This is a synthetic
zero-margin estimator boundary, not a measured provider overflow. Current paid
settings use a 1M window plus an 8192-token margin. Neither paid arm used the
shared-budget final-call path, so this finding did not affect these attempts.
It was left unfixed during that review to preserve the frozen paid comparison.
The subsequent authorized offline-only repair is recorded below.

No other new blocking defect was found in the reviewed reservation, submit or
concurrent scheduling paths. This is not a claim of exhaustive correctness.

## Offline Verification

Evidence root, relative to `/home/zhoujunye/MAS-information`:
`outputs/kramabench-v7-rereview-20261101-01`.

- Full server suite: `191 passed in 2.71s`, `regression.xml`.
- Extra stress: 60 combinations of shared ceilings 2..21 and parallelism 1/2/4.
  Every accepted child returned its reserved report; the root completed; attempts
  equalled charged calls and never exceeded the ceiling; no reservation remained.
  `reservation-stress.json` contains each case. All clients were scripted.
- `capacity-notice-probe.json` and its trace document the P2 finding above.
- Local/server checksums of the reviewed core/adapter/runner files matched.
  The server was idle and had no running Docker containers before launch.

## Frozen Paid Scope

Evidence root:
`outputs/kramabench-paid-v7-rerun-20261101-01`.

- Model: `deepseek-flash`, thinking enabled, high effort, output cap 16,384,
  retries 0, request timeout 180 seconds. Returned model name was `deepseek-flash`.
- Each arm: 64 shared model requests, 120 domain actions, 1800 execution seconds,
  120 audit seconds. MAS: up to four parallel children, eight identities, sixteen
  delegations. No monetary ceiling, as authorized.
- Common source digest: `190eac9f05b168b7`; verified before/after and in both manifests.
- Existing image ID:
  `sha256:e853321226dc4653164fff8f7e723a86df1a9e2aca282e649dfe2a9a1b144f6c`.
- Matched data/image/resource/output contracts, independent initially empty workspaces,
  read-only domain inputs, no network in either container. No answer/reference mounts.
- Fixed execution order Single then MAS, not cache-order-balanced or held-out.
  This inspected task has already informed prompt development.

## Results

| Measure | Single | MAS |
|---|---:|---:|
| Valid submit calls | 1 | 1 |
| Submitted answer | 8347.1887 | 8477.8648 |
| Pinned scalar score | 0 | 0 |
| Model calls | 14 | 31 |
| Domain actions | 14 | 34 |
| Prompt tokens | 113800 | 338764 |
| Completion tokens, including reasoning | 8265 | 29233 |
| Token-weighted prompt-cache reuse | 91.44% | 80.67% |
| Maximum prompt tokens | 14992 | 26121 |
| Runtime seconds | 74.04 | 170.90 |
| Estimated USD | 0.006731592 | 0.028182240 |

Both attempts ended `completed`, `submission_status=valid`, `infra_affected=false`,
with no provider errors or trace-integrity errors. Each had one recoverable inspection
tool error. No submission correction or mixed-submit rejection occurred. Both root
submissions were normal calls, not forced final calls.

MAS selected `requirement_analyst` and `reproduction_checker`, with overlapping
delegation intervals (peak two). Both hit their respective local 6/10-call ceilings
and returned nonempty final reports, 5373/3125 characters. There was no resume in this
paid run. Neither arm exhausted the shared model/tool/time ceiling. Shared-boundary
reservation behavior is supported by scripted tests, not exercised by this paid case.
Both arms ended with zero outstanding report reservations.

### Per-Role Accounting

| Role | Calls | First / max prompt tokens | Weighted cache reuse | Estimated USD |
|---|---:|---:|---:|---:|
| Single | 14 | 1665 / 14992 | 91.44% | 0.006731592 |
| MAS leader | 15 | 2870 / 26121 | 92.72% | 0.012422496 |
| Requirement analyst | 6 | 2462 / 16260 | 41.70% | 0.008539692 |
| Reproduction checker | 10 | 2454 / 13868 | 75.61% | 0.007220052 |

MAS cost was 4.19 times Single. Its root still used 15 calls and 15 domain actions,
versus Single's 14/14, while children added 16 calls and 19 domain actions. Delegation
therefore supplemented rather than replaced the root's workload in this attempt.
The old pilot's cost ratio was about 9.76, but changed prompts, roles selected and
stochastic trajectories prevent attributing this decrease to a particular fix.
Provider pricing was checked against the official pricing page at run time.
Recorded account-wide CNY balance changes (0.00 and 0.06) are not attributable
per-run costs and may reflect rounding, timing or other account activity.

## Interpretation And Remaining Controls

Single again selected the mean of two interpolated endpoint values. MAS selected
the time-weighted interval mean with interior knots retained. Both numbers match
the corresponding previously independent diagnostic calculations. The pinned gold
is 8577.5298, and its reference replay ambiguity remains as documented in
`kramabench-pilot-analysis.md`. Neither score is revised; neither proves an arithmetic
failure or a general MAS advantage/disadvantage.

The MAS brief withheld the candidate numeric answer from the reproducer, but
prescribed the time-weighted estimator and called it a task-fixed constraint.
The reproducer explicitly labelled its result same-method reproduction, not
independent validation of the estimand. Thus independent arithmetic checks occurred,
but the leader's interpretation was not independently established by agreement.
This is observed delegation behavior, not a new runtime permission or transport bug.

Equal request ceilings are still not equal token/compute/cost budgets. Per-delegation
remaining-budget fields are concurrent snapshots, not guaranteed future allocations.
Call reservations do not guarantee reports after timeouts, context overflow or fatal
provider errors. Natural-language summaries can still omit or misstate details.

`verification.json` binds hashes of each manifest, trace, report, outcome, submission
and grade, records usage/cost/lifecycle checks and confirms cleanup. Both owned
containers were removed successfully and checked absent; all evidence/workspaces
were retained. Submitted pipeline syntax was checked, but code was not independently
re-executed and the upstream paid pipeline evaluator was not called.

## Subsequent P2 Repair

The follow-up repair moves final-notice construction and capacity checking into
atomic model-call admission, before charging calls or consuming report reservations.
It leaves original histories and reasoning intact, introduces no summary/repair
completion, and does not change the paid artifacts above. Single and MAS share the
same implementation. The token estimator remains conservative, not an exact tokenizer.

Server-only verification on 2026-11-01: 13 new targeted tests passed; the full suite
passed `204 tests in 2.75s`. Receipts are under
`outputs/kramabench-capacity-p2-20261101-01/{targeted,regression}.xml`.
Coverage includes over-capacity and exact-fit final notices for roots, children and
submit; Single/MAS local-rejection accounting; receipt-anchored histories; concurrent
siblings; preflight deadlines; and charging real attempts that fail after admission.
Scripted paired smoke at `outputs/kramabench-capacity-p2-paired-20261101-01` completed
with 4 Single / 15 MAS calls, no trace-integrity errors and no infrastructure impact.
No paid model, judge, balance request or new container was used for this repair.
