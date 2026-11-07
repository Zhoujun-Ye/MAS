# Paid Infrastructure Smoke Test (2026-11-07)

Authorized: four fixed Validation20 questions, Structured and FULL once each,
eight solvers total, at most eight scoring calls, no reruns. Frozen manifest slice
0:4 preserves task order: wildfire-easy-9, astronomy-easy-1, archeology-easy-11,
legal-hard-15. No selection by score. This is an engineering smoke sample, not a
representative whole-benchmark speed study or an independent quality test.

Source: `/home/zhoujunye/mas-stages/20261107-krama-infra-smoke4`.
Output: `/home/zhoujunye/mas/outputs/krama-infra-smoke4-20261107-01`.
Export, comparison JSON and report directory use the same prefix. Previous
comparison is the retained CPU8 effective export, with authorized replacement
artifacts used for both legal-hard-15 rows. Original artifacts were not changed.

## Execution And Results

Eight solvers ran concurrently: their first native observer timestamps span
08:29:40.839 to 08:29:41.125 UTC. CPU8/container, four numerical threads/process,
eight GiB/container, high effort, pinned CLI/image, host gateway, network none.
Structured prompt unchanged. FULL uses the repaired decision-v4 implementation.
Process exit was zero. Eight attempts and eight grades completed; all eight tasks
used deterministic scoring, so paid judge calls were zero. No reruns occurred.
The account measurement interval including grading was 356.43 seconds (5.94 min),
excluding offline preflight. This is not comparable to the old 20-question wall time.

| Same four questions | Structured previous -> current | FULL previous -> current |
| --- | --- | --- |
| Mean CLI seconds | 205.06 -> 162.30 (-20.85%) | 262.66 -> 232.87 (-11.34%) |
| Mean score | 0.976923 -> 0.976923 | 0.976923 -> 0.976923 |
| Full-score tasks | 3/4 -> 3/4 | 3/4 -> 3/4 |
| Time-weighted cores/container | 0.184 -> 0.243 | 0.265 -> 0.311 |
| Utilization of eight-core quota | 2.30% -> 3.03% | 3.31% -> 3.89% |
| CPU quota throttled seconds | 0 -> 0 | 0 -> 0 |
| Model dispatches | 138 -> 111 | 192 -> 178 |
| Known USD at same historical price scenario | 0.160860 -> 0.114558 | 0.203670 -> 0.187402 |
| Requests with unknown charges | 2 -> 0 | 1 -> 0 |

Current account balance decreased CNY 2.36 over the shared-account interval; this
is not authenticated per-run billing. USD numbers use the same historical
off-peak token-price scenario, not verified current tariffs or invoices. Historical
subtotals exclude unknown charges and replaced failed attempts, because this table
compares the eight effective artifacts, not all incurred historical experiment cost.

## Engineering Findings

- All eight native lifecycle audits passed, CPU captures were complete, gateway
  reconciliation matched, pipeline replay matched submissions, and owned containers
  were removed. All 289 model responses completed with HTTP 200 and observed usage.
  No terminal infrastructure failure, degraded evidence store or upstream 5xx occurred.
- FULL sharing emitted 117 updates with 241 observation references. Lead explicit
  worker-evidence access occurred on three of four tasks. Emission/access is not
  proof of understanding or score contribution. All four final consistency gates passed.
- Astronomy FULL took 273.64 seconds versus 130.77 previously (+109.24%). A worker
  declared an entire analysis dictionary as an answer, while another candidate was
  the scalar answer. Both therefore correctly entered the current explicit-answer
  pool, creating a representation conflict rather than two different scalar answers.
  Do not automatically flatten dictionaries or choose a semantic answer. Better
  declaration/schema feedback is a follow-up design issue.
- One `decision_select` call was rejected for missing current-snapshot evidence
  reads. Previous reads were complete (`next_start=null`); new interpretations
  changed the snapshot. The generic unread/pagination error did not identify the
  stale candidate and led to unnecessary source pagination. The model recovered,
  reread the other candidate and selected successfully. This is a diagnostic/API
  usability defect, not a crash or a failed full-page read implementation.
- FULL sharing delivered approximately 250,183 characters across all native
  contexts, including 126,827 on legal alone. Per-hook bounding works, but cumulative
  context volume remains substantial. Relevance filtering is not solved.
- Ten Bash failures involved solver-produced parsing, encoding, indexing or
  syntax code; these were repaired within their original attempts.
  They are not ten harness crashes, nor ten extra benchmark retries.
- Follow-up correction: the initial narrow standalone-sleep detector missed seven
  `sleep N; echo waited/done` commands. FULL spent 286.31 seconds across these
  waits; 114.72 seconds overlapped intervals with no observed active workers.
  The old advisory was not exercised because it missed the wrapper syntax.
  These totals are summed task time, not additional batch wall time. See
  [speed repair](full-speed-repair.md) for diagnosis and offline validation.

Mean runtime improved, but improvement is not uniform: Structured astronomy and
archeology slowed by 14.54% and 7.34%. CPU seconds actually rose slightly in both
conditions while model dispatches fell. Neither low CPU utilization nor zero quota
throttling supports CPU capacity as the dominant bottleneck here. Provider timing,
generated execution paths, old upstream errors and recovery-phase concurrency
confound causal attribution. Current FULL remains 43.48% slower than Structured,
with equal scores and about 63.59% greater estimated token cost. No additional paid
tests or implementation changes were performed after inspecting these results.
