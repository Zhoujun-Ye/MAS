# Retained Results

FULL/OBS and their prompt-only ablations were retired on 2026-11-10. Results
below are historical evidence, not active launch choices. Current conditions
default to strict Single and frozen Structured.

The frozen Krama Random20 questions have two thinking-off/T=0 batches in
Single/Native/Structured ([T=0 record](studies/krama-random20-20261111.md)) and one
thinking-off/T=1.0 batch ([T=1.0 record](studies/krama-random20-temperature1-20261112.md)).
The T=1.0 answer means are 53.33%/80.00%/71.67%; its
[audit-filtered paired view](studies/krama-anomaly-audit-20261112.md#paired-native-audit-view) on the same
eighteen tasks gives 53.70%/77.78%/79.63%. These are repeated diagnostic runs, not
independent tests or causal organization effects. The
[three-repeat batch](studies/krama-three-repeats.md),
`krama-random20-three-repeats-20261112-01`, was stopped at the user's request:
59 first-round attempts completed and one was interrupted; rounds two/three
were not dispatched. Its partial evidence/costs remain retained, not three-round
results. Its Native/Structured payloads were subsequently deleted at the user's
request; Single and incurred accounting remain. The newly authorized
`krama-random20-forced-repeats-20261112-01` reuses both complete T=1.0 Single rounds
and runs the missing Single round plus three new Native/Structured rounds:
140 new solvers and 14 judges, now completed without retries. The three-round
raw means are Single 60.56%, Native 72.22%, Structured 61.11%. Nine MAS attempts
encountered the subsequently fixed asynchronous delegation gate race; these
results cannot be presented as free of harness effects. Read-only corrected
lifecycle diagnostics leave one unaudited task (`wildfire-easy-3`), excluded from
all nine cells in the additional nineteen-task paired view. Raw scores and paid
source remain unchanged; this is not a rerun of the corrected harness.

Paid batches and their exact source/accounting are listed in [retention](archive.md).
The November 11 shared-image check completed twelve Single/Structured solvers
across DataClaw/HDR/Krama, with 12/12 native audits, no retries or paid judges,
CPU8/thread4, zero quota throttling/OOM and verified container cleanup. One slot
was first dispatched separately after a zero-call TLS readiness failure; three
native-cancelled streams retain unknown final usage. See the
[current infra results and limits](studies/threebench-infra-20261111.md).

The [FDABench matched rerun](studies/fdabench-cpu8-rerun-20261110.md) kept both
conditions at 4/4, but only 6/8 lifecycle audits passed. Overall mean CLI time
rose 10.7%, so there is no overall infra speedup claim. Its
[original diagnostic](studies/fdabench-smoke4-20261110.md) used CPU2/thread1,
not the corrected CPU8/thread4; exact times, common-rate costs and caveats have
one owner in the matched report rather than duplicate ledgers here.

[Krama history](studies/krama-history.md) consolidates the twenty-task CPU8 pair,
its authorized 503 recovery, trajectory diagnosis and two four-task speed checks.
The main pair has identical taskwise scores (mean 0.7453846154, 14/20 full score),
with no FULL advantage. The four-task speed checks are small stochastic samples,
not universal gains. All raw paid batches, failures, incurred costs and frozen
sources remain retained; historical v3/v4 settings are not current launch options.

## Later Engineering Checks

These are repeatedly used validation tasks, not independent final tests or
controlled mechanism ablations. Do not aggregate scores across benchmarks as one
accuracy or attribute shared-account deltas as per-condition invoices.

| Batch | Scope | Result And Limitation |
| --- | --- | --- |
| `threebench2-engineering-20261107-01` | 12 Structured/FULL attempts | Two HDR timeouts; DataClaw 1.0 and Krama 0.953846 in both conditions |
| `hdr2-network-20261107-01` | Four Structured/FULL HDR attempts | Both conditions 0/2; old textual-format rejection later diagnosed |
| `threebench2-20261109-01` | 18 Single/Structured/FULL attempts | DataClaw 1/1/0.75, HDR all 0, Krama all 0.953846; VPN disruption and separate deterministic SQL regrade |
| `full-infra-paid4-20261110-01` | Four FULL attempts, two paid grades | Both DataClaw tasks and Krama score 1, HDR SQL 0; eight overflow captures verified; later DNS/read repairs were free validation only |
| `threebench-infra-20261111-01` plus `-unstarted-01` | Twelve Single/Structured attempts, no paid judge | All CLI/native audits passed; HDR SQL 0, Krama 0.953846 mean in both conditions; text answers ungraded and three stream costs unknown |

## Native/Single Mechanism Studies

The six-arm T=1.0 study `native-single-causal30-20261112-01` completed 540 solvers,
90 independent recon sessions and 72 one-call judges. The fresh T=0.7 study
`native-single-causal30-e4-t07-20261112-01` completed 810 sessions, including
90 E4 worker-role replays and 90 paired lead continuations, plus 72 one-call
judges. Neither study includes Structured or permits retries. The
[study documentation](../scripts/studies/causal_experiments/README.md) owns the
interventions and limits; completion is not evidence of a causal mechanism.

Raw evidence is server-side. Local `outputs/` keeps final causal reports/audits,
the bound E4 semantic review pack, coding, analysis and validation, as well as
retained CPU8/smoke reports. The E4 semantic overlay does not replace raw grades;
its single unblinded coding and post-hoc contrasts remain limitations. Superseded
progress exports are disposable. All frozen paid stages and original failures
remain protected. No new paid run follows from an offline cleanup or proof.

- [Retained Krama configuration, accounting and trajectory diagnosis](studies/krama-history.md)
- [Active infra](studies/evidence-infra.md)
- [Full-scale offline readiness](studies/fullscale-infra.md)
- [Three-condition smoke](studies/threebench2-20261109.md)
- [Latest FULL/DNS audit](studies/full-infra-20261110.md)
- [Retention policy](archive.md)
