# Retained KramaBench CPU8 Comparison

Completed on 2026-11-06 with exactly 20 fixed questions each for Structured and
FULL decision-v3, eight CPUs per container and eight concurrent solver tasks
combined. Claude Code 2.1.286, DeepSeek Flash, high effort, 3600-second timeout,
8 GiB memory, one numerical thread per process, zero requested native retries,
network-disabled containers and host credential gateway. The baseline prompt
and grading contract were unchanged. The current decision-v4 repair is separate;
it has not run paid benchmark questions.

The main batch is `/home/zhoujunye/mas/outputs/krama-cpu8-paired-20261106-03`;
its once-only authorized terminal-upstream-503 recovery is the same prefix plus
`-upstream-recovery-01`. Recovery replaces primary results, never best-of selects.
The original failures and all incurred costs are retained. Older and interrupted
batches were deleted at the user's request on 2026-11-07 and are not required
inputs for the retained effective report.

## Completed Primary Comparison

All three eligible HTTP 503 attempts were rerun once and scored 1. Their recovery
artifacts replace the matching primary rows by user policy, regardless of score.
There are still 20 effective questions per condition, with 43 physical attempts
in total: 22 Structured and 21 FULL. No wrong-answer or lifecycle-only reruns were
performed. The `-03` first-pass artifacts and all recovery evidence remain intact.
All 40 effective grades were independently verified against their submission-file
hashes and condition-specific artifact paths. Every task has the same score in
FULL and Structured, not merely the same aggregate mean.

| Metric | Structured | FULL decision-v3 |
| --- | ---: | ---: |
| Mean score | 0.7453846154 | 0.7453846154 |
| Full-score tasks | 14/20 | 14/20 |
| Mean effective CLI minutes/task | 7.3662 | 7.7321 |
| Median effective CLI minutes/task | 5.3824 | 5.8022 |
| Maximum effective CLI minutes/task | 34.9461 | 32.8132 |
| Time-weighted mean CPU cores/container | 0.4901 | 0.5357 |
| Mean utilization of 8-CPU quota | 6.1257% | 6.6966% |
| Kernel CPU quota throttled seconds | 0 | 0 |
| Sample-window P95 CPU cores | 1.5038 | 2.0047 |
| Sampled time above 2 CPU cores | 3.0546% | 5.9278% |
| Complete effective CPU captures | 20/20 | 20/20 |
| Effective-artifact model dispatches | 1004 | 1330 |
| All incurred model dispatches, including replaced failures | 1011 | 1343 |
| Observed complete-request USD scenario subtotal, including failures/recovery | 1.561336 | 2.051078 |
| Model requests with unobserved charges | 7 | 2 |
| Native lifecycle audits passed | 18/20 | 19/20 |

FULL was about 4.97% slower in mean effective CLI time, with no score advantage.
All FULL consistency checks passed, including wrong answers; consistency is not
correctness. Three lifecycle exceptions remain unverified and are not relabeled
as clean termination merely because owned containers were removed.

The USD subtotals use the same frozen off-peak price scenario for complete observed
gateway requests plus judge usage across all 43 attempts. They are not complete
totals or invoices: nine upstream HTTP 503 responses (7 Structured, 2 FULL) have
no usage metadata, and unknown charges are never assumed zero. Both observed
account-balance interval deltas sum to CNY 25.62, including failed calls and
recovery; this is not authenticated per-run/per-condition attributable billing.
Earlier interrupted experiments are excluded from these comparison costs. No new 5xx occurred during the three recovery attempts.

The first-pass batch wall time was 58.56 minutes; recovery wall time was 7.56
minutes. Those phases exclude the intervening offline preparation/user interaction.
The main table uses each task's effective artifact time, while the effective
report additionally retains all incurred CLI time: 147.56 Structured and 155.92
FULL minutes. Recovery contained only 3 jobs, under the same maximum concurrency
8; it did not provide an identical contemporaneous load to every first-pass task.

Lead prompt lengths were 3773-4369 characters for Structured and 3647-4243 for
FULL. Retained native token-weighted cache hits were 97.49%/93.50% for Structured
lead/workers and 97.68%/95.60% for FULL. Native role usage is not an invoice or
proof of semantic contribution; host request accounting remains authoritative.

### Artifacts And Verification

Recovery source: `/home/zhoujunye/mas-stages/20261106-krama-upstream-recovery-01`.
Recovery output: original `-03` prefix plus `-upstream-recovery-01`.
The selector/replacement workflow passed 606 server tests in 15.67 seconds before
paid recovery. Final report source at
`/home/zhoujunye/mas-stages/20261106-krama-cpu8-final-report` passed 606 tests in
15.90 seconds. Report generation made no grading/model calls.

Effective export/report: the `-03` prefix plus `-effective-export.json` and
`-effective-report/`. These retain current CPU summaries, request-cost coverage
and source/input hashes. The older cross-run comparison export was removed with
the older runs. Original exports are retained; their duplicate presentation folders
were removed during cleanup and can be rebuilt. The primary result
after the authorized substitutions. All owned containers are gone.
