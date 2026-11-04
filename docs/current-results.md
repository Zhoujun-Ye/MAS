# Current Results: Matched-10 Single vs Subagents

Completed 2026-11-04. Run: `claude-matched10-v4-high-01-443a5f0`.
Solver source commit: `443a5f0`; grading-only recovery: `bee2337`.

## Frozen Scope

- Claude Code 2.1.286, DeepSeek Flash, all lead/worker requests at `high`.
- Each benchmark has 10 matched questions, one attempt per condition: 60 solvers.
- Deterministic SHA-256 ordering with seed 42, round-robin public strata:
  DataClaw categories, HDR categories and Krama domains. Selection never uses scores.
- Subagents uses the adopted v4 default, with no study prompt override.
- Solver concurrency 6; judge concurrency 2; no retries or replacement attempts.
- Timeouts: DataClaw 1200 s, HDR 1800 s, Krama 3600 s. Web tasks allow four
  search/fetch requests shared across all agents in the attempt.
- All 60 answers were evaluated. 36 paid judge calls; other judgments use the
  existing deterministic evaluators. No new solver calls during recovery.

## Results

Full-score counts are not binary accuracy for partial-credit tasks. DataClaw uses
the adapted upstream per-part rubric; Krama includes its native partial-credit
metrics. Benchmark means below average those existing task scores. Do not pool
heterogeneous scores into a new universal accuracy metric.

| Benchmark | Single Mean | Subagents Mean | Single Full Score | Subagents Full Score |
| --- | ---: | ---: | ---: | ---: |
| DataClawBench | 0.8000 | 0.7500 | 8/10 | 7/10 |
| HybridDeepResearch | 0.5000 | 0.4000 | 5/10 | 4/10 |
| KramaBench | 0.6908 | 0.7908 | 6/10 | 7/10* |

*The Subagents attempt on `biomedical-hard-4` scored 1, but started no subagent;
its status is `native_condition_unverified`. The raw assigned-condition results
retain it rather than silently excluding or retrying it. It is not evidence of
successful Subagents use. On the nine matched Krama questions excluding this
pair, full-score counts are Single 5/9 and Subagents 6/9. Single's paired answer
also scored 1. All remaining 59 native-condition audits passed.

| Benchmark | Single Mean Min | Subagents Mean Min | Single USD Estimate | Subagents USD Estimate |
| --- | ---: | ---: | ---: | ---: |
| DataClawBench | 4.44 | 4.25 | 0.337386 | 0.414675 |
| HybridDeepResearch | 9.07 | 12.27 | 0.646312 | 1.133685 |
| KramaBench | 2.27 | 2.23 | 0.163993 | 0.231523 |
| All 30 Attempts | 5.26 | 6.25 | 1.147691 | 1.779882 |

Costs include model, web and judge estimates. Model/judge costs use observed token
usage and off-peak prices; successful-HTTP web responses are estimated billing
units, not independently verified billable nonempty responses. Rates were checked
against the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/).
The observed shared-account balance decrease was CNY 19.71, not a per-condition
invoice. Estimated combined USD cost is 2.927573. Missing accounting is not zero.

Subagents cost about 1.55 times as much in this sample and had higher mean solver
time overall. It improved the sampled Krama scores but not DataClaw or HDR.
Across the raw assigned conditions, full-score counts were 19/30 versus 18/30;
this is descriptive, not a heterogeneous-benchmark accuracy claim.

## Native Evidence

- 1901/1901 host-observed dispatched model requests declared `high`:
  Single 920, Subagents 981.
- All 60 gateway/transcript reconciliations matched. This is anomaly checking,
  not authenticated process attribution or an adversarial-isolation guarantee.
- Subagents: 35 worker starts and 35 stops, across 29/30 attempts with delegation.
  Lifecycle completion does not prove substantive contribution or non-duplication.

| Condition / Role | Input Tokens Including Cache | Output Tokens | Cache-Hit Tokens | Token-Weighted Cache Hit |
| --- | ---: | ---: | ---: | ---: |
| Single / leader | 46035674 | 1365832 | 44895616 | 97.52% |
| Subagents / leader | 44089288 | 1404599 | 42750464 | 96.96% |
| Subagents / member | 6032057 | 782289 | 5369600 | 89.02% |

Per-task scores, elapsed time, cost components, prompt lengths/hashes where available,
role usage, audit status and evidence paths are in `comparison-safe.json` on the
server. It excludes questions, candidate/reference answers, SQL and evaluation logs.

## Recovery And Retention

The original SSH connection closed. A subsequent stdout write raised
`BrokenPipeError`; the main process retained only 50 progress rows and did not
enter grading. Inspection found terminal reports and summaries for all 60
solvers, with no live run processes or containers. No solver was restarted.
The grading-only recovery reconstructed rows from those exact retained reports,
graded into a fresh namespace, and wrote the final summary. The original
`failure.json` remains alongside the recovered summary.

Server root:
`/home/zhoujunye/MAS-information/outputs/current/claude-matched10-v4-high-01-443a5f0`.
Frozen plans/source snapshots, submissions, native evidence, gateway ledgers and
private evaluation artifacts remain there. The previous six-task batch is also
retained; its [historical report](studies/claude-all-high-01-results.md) is separate.
No historical runs were deleted or merged into this comparison.

Offline verification before solver launch: 344 server tests passed. Grading-only
recovery additionally passed three focused server tests. Fake/offline tests are
not solver-quality evidence. The final full server suite passed 347 tests.
There is only one attempt per selected task; these
results establish neither general superiority nor statistical significance.
