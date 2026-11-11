# Retained Results

FULL/OBS and their prompt-only ablations were retired on 2026-11-10. Results
below are historical evidence, not active launch choices. Current conditions
are only strict Single and frozen Structured.

Paid batches and their exact source/accounting are listed in [retention](archive.md).
The November 11 shared-image check completed twelve Single/Structured solvers
across DataClaw/HDR/Krama, with 12/12 native audits, no retries or paid judges,
CPU8/thread4, zero quota throttling/OOM and verified container cleanup. One slot
was first dispatched separately after a zero-call TLS readiness failure; three
native-cancelled streams retain unknown final usage. See the
[current infra results and limits](studies/threebench-infra-20261111.md).

The CPU8/thread4 FDABench rerun repeated the same eight authorized task/condition
slots without retries or paid judges. Both raw scores remain 4/4, but only 6/8
native organization audits passed because two SessionEnd records are absent.
Single mean CLI time changed 4.186 to 3.494 minutes (-16.5%); Structured changed
3.667 to 5.197 minutes (+41.7%). At common rates, estimated API cost changed
CNY 0.7905 to 0.6231 for Single and 1.1494 to 1.1510 for Structured. Overall mean
CLI time rose 10.7%, so this does not establish an overall infra speedup. Shared
account deltas of CNY 4.29/1.66 also cross peak/off-peak pricing and are not an
infra cost attribution. See [the matched comparison](studies/fdabench-cpu8-rerun-20261110.md).

The preceding FDABench diagnostic used four fixed public local choices, once per
Single/Structured condition. Both scored 4/4, all eight native audits passed,
offline judge calls and retries were zero. Mean CLI times were 4.19/3.67 minutes.
Its actual profile was mistakenly 2 CPUs/thread1, not CPU8/thread4, so it cannot
validate the corrected resource defaults. Shared-account interval delta was
CNY 4.29, not an attributable per-condition invoice. See
[the full scope and repairs](studies/fdabench-smoke4-20261110.md).

The main historical paired result remains the completed CPU8 KramaBench comparison.
Both conditions have 20 effective questions, mean score 0.7453846154 and 14 fully
correct answers. Scores match question by question. FULL averages 7.7321 CLI
minutes versus Structured's 7.3662. These are validation results, not a held-out
test or a causal mechanism ablation.

Server output prefix:
`/home/zhoujunye/mas/outputs/krama-cpu8-paired-20261106-03`.
The primary artifacts are `-effective-export.json` and `-effective-report/`.
Three once-only authorized upstream-503 replacements reside in
`-upstream-recovery-01/`. Keep original failures and all incurred costs, not only
the effective successful attempts. No score-based best-of selection is allowed.

Observed complete-request USD scenario subtotals including failures/recovery:
Structured 1.561336, FULL 2.051078. Nine HTTP 503 requests lack usage metadata
(seven Structured, two FULL), so full costs are unknown. These are not invoices.
Mean measured CPU cores are 0.4901 / 0.5357, with zero quota throttled seconds.

The twenty-question run used decision-v3. The two decision-v4 paid checks used
the same four frozen questions, CPU8, four numerical threads and eight concurrent
solvers total, without reruns. Each condition scored 0.976923 on both checks,
with three full-score tasks and one partial score. FULL mean CLI time fell
232.87 -> 173.55 seconds; Structured varied 162.30 -> 150.79 seconds. FULL's
estimated cost at the same historical pricing scenario fell 25.10%. These are
small-sample observations, not evidence of universal or causal speed gains.

The two smoke output prefixes are `krama-infra-smoke4-20261107-01` and `-02`
under the same server outputs directory. Keep both raw batches: the first is
the comparison baseline, not a disposable interrupted run.

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

- [Retained run configuration and accounting](studies/krama-cpu8-paired.md)
- [Trajectory diagnosis](studies/cpu8-trajectory-analysis.md)
- [Active infra](studies/evidence-infra.md)
- [Latest paid speed check](studies/infra-smoke4-speed-check.md)
- [Full-scale offline readiness](studies/fullscale-infra.md)
- [Three-condition smoke](studies/threebench2-20261109.md)
- [Latest FULL/DNS audit](studies/full-infra-20261110.md)
- [Retention policy](archive.md)
