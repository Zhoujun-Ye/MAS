# Retained Results

FULL/OBS and their prompt-only ablations were retired on 2026-11-10. Results
below are historical evidence, not active launch choices. Current conditions
default to strict Single and frozen Structured. The [prepared Krama Native
comparison](studies/krama-random20-20261111.md) has no paid results yet.

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

Later raw evidence is server-side; local `outputs/` contains only the small
retained CPU8/smoke reports. All listed frozen paid stages and original failures
remain protected. No new paid run follows from an offline cleanup or proof.

- [Retained Krama configuration, accounting and trajectory diagnosis](studies/krama-history.md)
- [Active infra](studies/evidence-infra.md)
- [Full-scale offline readiness](studies/fullscale-infra.md)
- [Three-condition smoke](studies/threebench2-20261109.md)
- [Latest FULL/DNS audit](studies/full-infra-20261110.md)
- [Retention policy](archive.md)
