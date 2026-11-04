# Current Results: Claude Single vs MAS, All High

Run: `claude-all-high-01-21a0cdb`. Solver source commit: `21a0cdb`. Completed 2026-11-04.

## Scope

- Claude Code 2.1.286, DeepSeek Flash; Single and native Subagents, six matched tasks each.
- Lead and worker effort: `high`; 311/311 host-observed model requests declare `high`.
- MAS lead prompt: `docs/studies/claude-focused-delegation-prompt.txt`; SHA-256 `f6fe3ff6271b7c5accf80cf74901ca405acd01de0fbc65d457f264c4c5f7044a`. Single receives no organization override.
- One attempt per condition, no automatic retries. Solver concurrency 12; judge concurrency 2.
- Solver timeouts: DataClaw 1,200 s, HDR 1,800 s, Krama 3,600 s.
- 12/12 solvers completed normally. Six paid judge calls completed successfully. SQL and numeric tasks use their respective deterministic evaluators.

## Task Results

Time is solver elapsed minutes; cost includes model, search/fetch and judge estimates in USD.

| Task | Single Score | MAS Score | Single Min | MAS Min | Single USD | MAS USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DataClaw easy001 | 1 | 1 | 2.69 | 2.59 | $0.016544 | $0.022519 |
| DataClaw easy002 | 1 | 1 | 2.60 | 1.96 | $0.018305 | $0.018941 |
| HDR s2sql_000 | 0 | 1 | 1.11 | 3.49 | $0.011250 | $0.041473 |
| HDR sql2s_001 | 1 | 1 | 1.53 | 10.06 | $0.017083 | $0.069718 |
| Krama archeology-easy-3 | 1 | 1 | 0.53 | 0.54 | $0.004695 | $0.008682 |
| Krama archeology-easy-4 | 0 | 1 | 7.02 | 9.60 | $0.045227 | $0.071553 |

## Aggregate Results

| Metric | Single | MAS |
| --- | ---: | ---: |
| Full-Score Tasks | 4/6 | 6/6 |
| Model Requests | 138 | 173 |
| Input Tokens (Including Cache) | 3739794 | 6184065 |
| Output Tokens | 117555 | 265070 |
| Model USD Estimate | $0.107458 | $0.226554 |
| Search/Fetch USD Estimate | $0.005250 | $0.006000 |
| Judge USD Estimate | $0.000397 | $0.000331 |
| Total USD Estimate | $0.113104 | $0.232885 |
| Solver Minutes, Summed | 15.49 | 28.23 |
| Token-Weighted Cache Hit Rate | 95.32% | 94.61% |

The shared-account balance decreased by CNY 2.07 over the run interval. This is not a per-condition invoice. Total observed-usage estimate: USD 0.345989. Pricing: [DeepSeek rate card](https://api-docs.deepseek.com/quick_start/pricing/); successful HTTP web responses are estimated billing units, not independently verified nonempty billable responses.

## Native Evidence

All 12 native-mode audits and gateway reconciliations passed; no unmatched response IDs or unknown response IDs were reported. Seven MAS subagent starts and seven stops were observed. Krama pipelines replayed successfully and matched the submitted answers, including the Single answer that scored zero.

| Condition / Role | Input Tokens | Output Tokens | Cache-Hit Tokens | Token-Weighted Cache Hit Rate |
| --- | ---: | ---: | ---: | ---: |
| Single / leader | 3739794 | 117555 | 3564928 | 95.32% |
| MAS / leader | 4922381 | 155472 | 4713984 | 95.77% |
| MAS / member | 1261684 | 109598 | 1137024 | 90.12% |

Per-task prompt lengths, role accounting, audit flags and exact server evidence paths are recorded in `comparison.json`. Benchmark questions, gold SQL and answers are not reproduced in this summary.

## Interpretation And Limits

In this six-task pilot, MAS scored fully on 6/6 tasks versus Single's 4/6, at approximately 2.06 times the estimated total cost. MAS was not uniformly faster.

Each condition has only one attempt per task. These heterogeneous task scores do not establish general superiority, significance, or a causal effect of organization or effort. Native lifecycle evidence does not establish semantic contribution, non-duplication, or the timing of worker-result incorporation. Some lead agents made 14-16 tool calls before first delegation; some first-result receipt timings remain unverified.

## Retention

This is the only retained paid experiment batch. Earlier batches and their result summaries were explicitly deleted, not silently merged or treated as additional trials. The server retains this batch's frozen plans/source snapshots, submissions, native transcripts, gateway ledgers, evaluation results and balance receipts. Supporting offline proof `claude-all-high-offline-01` is retained. Source, datasets, environments, credentials and historical engineering/source snapshots are outside result cleanup scope.

Server evidence root: `/home/zhoujunye/MAS-information/outputs/current/claude-all-high-01-21a0cdb`.
