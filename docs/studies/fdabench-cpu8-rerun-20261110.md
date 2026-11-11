# FDABench CPU8 Matched Rerun

## Authorization And Frozen Scope

The user explicitly authorized another eight solver attempts: the same four
FDABench questions, once each with strict Single and frozen Structured, no retries
and no paid judge. No other benchmark or replacement attempt is authorized.

Reuse the exact task IDs, hashes and order from
[the preceding diagnostic](fdabench-smoke4-20261110.md): FDA0699, FDA1543, FDA0867,
FDA1948. Do not select questions based on earlier scores. Both conditions retain
the same organization prompts, task rules, model, max effort, 1800-second timeout,
20 successful web-call limit and offline exact-set choice scoring.

## Runtime

Every solver has 8 CPUs, four numerical threads, 8 GiB memory and resource capture.
Total solver concurrency remains four, grading concurrency two, matching the
preceding batch. The new shared PDF-capable image is
`mas/research-benchmarks:20261111-pdf-v1`, ID
`sha256:57a1e27dcdcb49b28d7a0c0e38ec4bde624d3baf32ff9bb006184b3521ff1489`.
Claude Code remains 2.1.286. Solvers have network disabled; real keys stay on the
host, and web GET/DNS use the private Mac/Clash route without fallback.

Use the existing runtime-bound CPU8 native proofs, revalidate image/binary/effort
and web readiness, and run all eight task/container preflights before dispatch.
Freeze source, task manifest, proof hashes, input hashes and settings in a fresh
namespace. CNY 25 estimated cost, 1.5 safety factor and CNY 5 reserve are balance
admission values, not a hard billing cap. The maximum paid scope is eight solvers,
zero paid judges and zero retry/recovery calls.

Output: `/home/zhoujunye/mas/outputs/fdabench-single-structured-smoke4-20261110-02`.
Receipts: `/home/zhoujunye/mas-data/receipts/fdabench-single-structured-smoke4-20261110-02/`.
Frozen source: `/home/zhoujunye/mas-stages/20261110-fdabench-single-structured-smoke4-02`.

## Comparison Contract

Compare each exact task/condition pair and condition aggregates: native CLI time,
host window and model-request union, input/cache-hit/uncached/output tokens,
leader/member breakdown, model/web request counts, native condition audits,
offline score, CPU/throttling/memory and observed tool failures. Preserve failures
and missing usage as unknown, not zero. Include preparation/controller wall time
separately when available; do not add overlapping parallel model calls as wall time.

Cost reporting separates the shared-account CNY interval delta from host-ledger
usage-based estimates. Price both batches with the same explicit rate scenario;
neither is a per-request invoice. Do not treat cached input as fully uncached.

This is one stochastic observation per task/condition before and after a bundle
of changes (CPU/thread quota, PDF dependencies and compact SQL errors). It can
describe observed improvement or regression, but cannot isolate CPU causality,
exclude provider/cache/order effects or establish a general benchmark-wide gain.
No additional run is implied by an unfavorable or inconclusive result.

## Completed Results

Exactly eight new attempts and eight offline grades finished, with zero paid
judges and no retry/recovery attempt. All native CLI processes exited zero and
all raw choice scores were 1. However, only six native condition audits passed:
Single/FDA1543 and Structured/FDA0867 lack SessionEnd records. Both retain
`native_condition_unverified`; the batch controller exited 1, not 0. No raw
artifact or audit was rewritten to make the batch pass.

The following includes all four attempts per condition, including audit exceptions.
Each cell is before (2 CPUs/thread1) / after (8 CPUs/thread4).

| Condition | Mean CLI Minutes | Uncached Input Tokens | Output Tokens | Common-Rate CNY Estimate |
| --- | ---: | ---: | ---: | ---: |
| Single | 4.186 / 3.494 (-16.5%) | 133,353 / 129,510 (-2.9%) | 141,548 / 105,972 (-25.1%) | 0.7905 / 0.6231 (-21.2%) |
| Structured | 3.667 / 5.197 (+41.7%) | 261,235 / 288,391 (+10.4%) | 206,408 / 192,698 (-6.6%) | 1.1494 / 1.1510 (+0.1%) |

Across both conditions, mean CLI time increased 10.7%, output tokens fell 14.2%,
uncached inputs increased 5.9%, and common-rate estimated API cost fell 8.5%
(CNY 1.9399 / 1.7741). Thus this sample does not establish an overall speedup or
a general improvement in Structured efficiency. Raw scores remain 4/4 in both
conditions, but organization-audit coverage fell from 8/8 to 6/8.

## Exact Pairs

Time is native CLI seconds; tokens are host-gateway usage with complete model
request reconciliation. CNY values are the same off-peak scenario for both phases,
not provider invoices. All cells use before / after; all raw scores are 1 / 1.

| Task | Condition | CLI Seconds | Uncached Input | Output Tokens | CNY Estimate |
| --- | --- | ---: | ---: | ---: | ---: |
| FDA0699 | Single | 180.4 / 128.5 | 34,393 / 24,343 | 24,623 / 16,678 | 0.1526 / 0.1042 |
| FDA0867 | Single | 246.0 / 86.3 | 17,913 / 11,463 | 33,967 / 10,658 | 0.1649 / 0.0586 |
| FDA1543 | Single | 307.5 / 419.3 | 40,921 / 56,613 | 44,254 / 46,631 | 0.2560 / 0.2717 |
| FDA1948 | Single | 270.8 / 204.5 | 40,126 / 37,091 | 38,704 / 32,005 | 0.2169 / 0.1886 |
| FDA0699 | Structured | 161.8 / 309.4 | 80,305 / 95,522 | 43,562 / 65,945 | 0.2688 / 0.4121 |
| FDA0867 | Structured | 154.8 / 406.1 | 41,639 / 46,616 | 31,268 / 37,260 | 0.1796 / 0.2078 |
| FDA1543 | Structured | 314.8 / 238.1 | 65,359 / 76,273 | 62,921 / 58,060 | 0.3321 / 0.3224 |
| FDA1948 | Structured | 248.6 / 293.6 | 73,932 / 69,980 | 68,657 / 31,433 | 0.3689 / 0.2087 |

## What Changed In The Traces

- Actual quotas are `800000 100000` for all eight new containers, with four-thread
  numerical-library environment settings. No OOM was observed. All model request
  efforts remained max, and request/prompt/input checks matched the preceding run.
- Missing-pdftoppm errors fell from six to zero. Explicit reported tool errors
  fell from 28 to nine. These are confirmed observations, not isolated causal
  measurements of the dependency or compact-error changes.
- Structured Bash union time, summed over four separate attempts, grew from
  87.7 to 452.0 seconds. The slower trajectories include two approximately
  120-second SQL/Bash calls plus 84.5- and 60.3-second SQL analyses. Single/FDA1543
  also performed an approximately 120-second recursive PDF text scan. These are
  observed call durations; a 120-second return does not prove computation ended.
- Structured model-request union time grew only from 845.6 to 869.1 seconds,
  while its observed CPU consumption rose from 179.1 to 805.5 CPU-seconds.
  Model-inflight coverage of its host windows fell from 95.0% to 69.1%. Heavier
  local computation, not just more model tokens or CPU quota waiting, matters here.
- The old Structured containers accumulated only 0.88 seconds of quota throttling
  across all four attempts; the new containers recorded zero. This cannot explain
  a 91.8-second increase in mean CLI time. It does not establish that more CPUs
  caused the slower trajectories either: executed computations were not fixed.
- Structured lead output grew from 83,901 to 120,365 tokens while member output
  fell from 122,507 to 72,333. Its decomposition/communication trajectory changed
  despite identical prompts. This is not an identical-computation CPU microbenchmark.
- Host model ledgers reconcile to retained native messages for all eight runs;
  no native retry event was observed in actual stdout logs. One private-route
  webpage fetch returned 502; it was not a model API failure or a paid retry.

Single cache reuse was 96.38% / 96.15%; Structured reuse was 92.29% / 93.02%,
weighted by input tokens. Higher cache percentage did not prevent Structured's
uncached input total from rising because total context traffic also grew.

The global union of retained attempt host windows grew from 588.0 to 638.1 seconds.
The new controller ran 672.8 seconds, including 34.7 seconds outside these windows.
The old transient unit no longer retains process timestamps, so its full controller
duration and preparation-only overhead are unknown, not zero. CLI means above
must not be relabeled as complete batch wall time.

## Cost And Pricing Confound

Shared-account interval decreases were CNY 4.29 / 1.66. They are not attributable
per-condition invoices and exclude no failed or audit-unverified attempt.
The first model spans were November 10 at 22:01-22:11 America/New_York; the rerun
was 23:16-23:26, corresponding to November 11 at 03:01-03:11 and 04:16-04:26 UTC.
These cross the documented weekday peak/off-peak boundary. Therefore the roughly
61% balance-delta reduction cannot be claimed as an infra saving.

For comparable estimates, both batches use the same published off-peak Flash
rates: CNY 1/M uncached input, 0.02/M cache-hit input and 4/M output; successful
provider search requests are CNY 0.005 each, while direct host webpage GETs cost
zero in this estimate. [Official pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/).
The receipt also records the corresponding USD scenario. These estimates do not
include server CPU/electricity cost and are not exact provider settlement records.

## Residual Audit Gaps And Conclusion

Single/FDA1543 has policy enforcement, SessionStart, no exposed/executed delegation
tools and no member transcripts, but no SessionEnd. Structured/FDA0867 has one
subagent start and stop and no active subagent ID, but likewise no SessionEnd.
Normal native exit and correct answers do not fill these historical event gaps.
They remain unverified, not proven delegation violations or fully compliant runs.
All owned solver containers were removed after completion; this establishes current
cleanup, not retroactive session-end evidence. No additional paid run was made.

The confirmed positive is repaired PDF capability and fewer reported tool errors.
Single used less time/output/API cost in this sample; Structured was slower with
essentially unchanged common-rate cost. Longer SQL/PDF work and incomplete terminal
observations remain important issues. Do not present this as an overall infra
speedup, isolate CPU causality or promise the observed token savings will generalize.

Read-only comparison code is `scripts/studies/compare_infra.py`. Thirty targeted
server tests and the final 822-test full server suite passed. Its report includes
complete/unknown accounting checks,
weighted cache reuse, all matched slots and input/source hashes, without task,
answer or tool-response payload exports. Receipts include `comparison.json`,
`pairing-preflight.json`, `pricing.json`, `paid-audit.json`, `tests-release.xml`
and `timing-diagnostics.json` under the
receipt root above. Raw attempts, audit exceptions and frozen paid sources remain
protected alongside the preceding batch.
