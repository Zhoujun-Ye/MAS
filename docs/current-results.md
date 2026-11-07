# Retained Results

The completed CPU8 KramaBench Structured/FULL comparison and two subsequently
authorized four-task engineering checks are retained.
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

- [Retained run configuration and accounting](studies/krama-cpu8-paired.md)
- [Trajectory diagnosis](studies/cpu8-trajectory-analysis.md)
- [Active infra](studies/evidence-infra.md)
- [Latest paid speed check](studies/infra-smoke4-speed-check.md)
- [Full-scale offline readiness](studies/fullscale-infra.md)
- [Retention policy](archive.md)
