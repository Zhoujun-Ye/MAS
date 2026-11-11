# Retained KramaBench History

These are retained historical measurements, not active launch protocols. FULL,
OBS and their prompt-only ablations were retired on November 10. Their frozen
sources, original failures, submissions and accounting stay unchanged. Current
conditions and the prepared new sample are in [random20](krama-random20-20261111.md);
the authoritative raw-output/source inventory is [retention](../archive.md).

## Twenty-Task CPU8 Pair

The November 6 comparison used Structured and FULL decision-v3 on the same twenty
Validation20 questions. Claude Code 2.1.286, DeepSeek Flash, high effort, CPU8,
one numerical thread per process, eight GiB memory, eight solver slots in total,
3600-second timeout, network-disabled containers and a host credential gateway.
These historical thread/effort settings are not current defaults.

Output prefix: `/home/zhoujunye/mas/outputs/krama-cpu8-paired-20261106-03`.
The once-only recovery adds `-upstream-recovery-01`; the bound primary export
adds `-effective-export.json`, with the matching `-effective-report/` directory.
The main source is `20261106-krama-cpu8-paired-repaired-03` under `mas-stages`;
the recovery source is `20261106-krama-upstream-recovery-01`.

Exactly three terminal upstream-503 failures were explicitly rerun once. Those
artifacts replace the same primary slots regardless of score: twenty effective
questions per condition, 43 physical attempts (22 Structured, 21 FULL), no
wrong-answer or lifecycle-only retry. All three replacements scored one. Original
failed artifacts and all incurred usage remain, not a best-of selection.

| Metric | Structured | FULL decision-v3 |
| --- | ---: | ---: |
| Mean score | 0.7453846154 | 0.7453846154 |
| Full-score tasks | 14/20 | 14/20 |
| Mean / median CLI minutes | 7.3662 / 5.3824 | 7.7321 / 5.8022 |
| Maximum CLI minutes | 34.9461 | 32.8132 |
| Time-weighted average cores | 0.4901 | 0.5357 |
| Eight-CPU quota utilization | 6.1257% | 6.6966% |
| Sample-window P95 cores | 1.5038 | 2.0047 |
| Sampled time above two cores | 3.0546% | 5.9278% |
| Kernel quota throttled seconds | 0 | 0 |
| Effective model dispatches | 1004 | 1330 |
| All incurred model dispatches | 1011 | 1343 |
| Observed complete-request USD scenario subtotal | 1.561336 | 2.051078 |
| Requests with unobserved charges | 7 | 2 |
| Native lifecycle audits passed | 18/20 | 19/20 |
| Lead / worker token-weighted cache reuse | 97.49% / 93.50% | 97.68% / 95.60% |

Every paired task score matched, not just the mean. FULL was about 4.97% slower
on average. Three lifecycle exceptions remain unverified. Nine upstream 503
responses lack usage; scenario subtotals are neither complete totals nor invoices.
Shared-account interval deltas total CNY25.62, not attributable billing.
First-pass wall time was 58.56 minutes; recovery 7.56 minutes, excluding the
intervening preparation. All-incurred CLI time was 147.56 / 155.92 task-minutes.
Lead prompts were 3773-4369 / 3647-4243 characters. Complete CPU captures covered
all effective tasks. Forty effective grades were bound to exact submission hashes.
Offline verification passed 606 tests before recovery and report generation;
these historical checks do not admit present-day execution.

## Trajectory Diagnosis

Read-only receipts:
`/home/zhoujunye/mas-data/receipts/cpu8-trajectory-audit-20261106-01/`.
`audit-final.json` binds per-task observations/timing/input hashes; no paid call,
grading change, environment installation or answer rewrite was made by the audit.

All twenty FULL stores were available. The lead recorded 32 `decision.view`,
23 `decision.check`, seven `decision.read`, seven `obs.list` and four successful
`decision.select` calls; five native selection attempts include one failure.
No `obs.read`, `obs.search` or `workspace.trace` calls were recorded. List previews
exposed 33 worker observations across five tasks; decision reads accessed worker
representatives three times across two tasks. One task had worker-side API use.
These counts establish access, not comprehension or causal incorporation.

Thirteen explicit intermediate measurements appeared in two already-correct
tasks, none in the five zero-score tasks. Sixteen final pools were singletons;
four conflicted. Three conflicting pools contained and selected a correct answer,
but Structured already solved all three. The fourth lacked a correct candidate.
All five zero-score pools lacked a reference-correct final candidate; consistency
cannot manufacture missing evidence or detect shared interpretation errors.
Three checks flagged pending execution before later consistency. No incremental
semantic error rescue or causal benefit was established.

| Zero-Score Task | Observed Discrepancy |
| --- | --- |
| `environment-hard-7` | Fraction versus percentage-point scale and rounding order |
| `astronomy-hard-12` | Epoch/field definitions; sensitivity output remained weak hints, not justified final candidates |
| `archeology-easy-8` | Citation canonicalization missed uncertainty suffixes and table-specific variants |
| `archeology-hard-5` | Scope, chronology and climate-column interpretation differed from reference substeps |
| `astronomy-hard-11` | Requested physical model unavailable; substitute regression/climatology used |

Reference mismatch alone does not resolve scientific correctness or task ambiguity.
The historical image lacked `pymsis` and `nrlmsise00`; CPU quota cannot supply model
coefficients. The audit added explicit capability/thread evidence, not silent installs.

Unioned model-inflight time covered 80.80% / 80.64% of attempt windows; Bash
35.15% / 49.12%, overlapping model intervals by 17.02% / 31.07%. Do not add these
percentages or equate inflight with pure network latency and Bash with CPU work.
Sleep-bearing commands numbered 10 / 25; Bash calls 1090 / 1320 and Agent calls
47 / 43. Different prompts and native worker trajectories confound a causal comparison.

The free, serial CPU8 BLAS probe used seeded 2304-square multiplication, warmup
and five measurements. Median seconds at one/two/four/eight threads were
0.4039 / 0.2099 / 0.1082 / 0.0741, with matching checksums and observed pools.
This is numerical-kernel capability, not end-to-end solver acceleration.
Thread limits are per process; simultaneous workers can oversubscribe the quota.
The shared active default is now CPU8/thread4, documented separately in
[active infrastructure](evidence-infra.md).

## Paired Four-Task Speed Checks

Retain both `krama-infra-smoke4-20261107-01` and `-02` under the server outputs
directory, and source stages `20261107-krama-infra-smoke4` and `-02` respectively.
Each run used the same first four Validation20 tasks, Structured/FULL once each,
eight solvers total, high effort, CPU8/thread4, eight GiB, eight solver slots and
two grading slots. All grades were deterministic; no paid judge or rerun occurred.
FULL used the separately authorized decision-v4 repairs, not the twenty-task v3.

| Metric | Structured Before -> After | FULL Before -> After |
| --- | --- | --- |
| Mean CLI seconds | 162.30 -> 150.79 (-7.10%) | 232.87 -> 173.55 (-25.47%) |
| Mean score | 0.976923 -> 0.976923 | 0.976923 -> 0.976923 |
| Full-score tasks | 3/4 -> 3/4 | 3/4 -> 3/4 |
| Time-weighted average cores | 0.243 -> 0.249 | 0.311 -> 0.370 |
| Quota throttled seconds | 0 -> 0 | 0 -> 0 |
| Model requests | 111 -> 122 | 178 -> 137 |
| Output tokens | 112653 -> 109797 | 174123 -> 135831 |
| Same-rate USD scenario | 0.114558 -> 0.117581 | 0.187402 -> 0.140372 |

| Task | Structured Seconds Before -> After | FULL Seconds Before -> After |
| --- | --- | --- |
| `wildfire-easy-9` | 142.77 -> 149.15 | 96.36 -> 161.40 |
| `astronomy-easy-1` | 116.60 -> 153.36 | 273.64 -> 168.77 |
| `archeology-easy-11` | 146.87 -> 139.70 | 214.36 -> 150.17 |
| `legal-hard-15` | 242.97 -> 160.93 | 347.14 -> 213.84 |

Batch wall time excluding preflights fell 356.43 -> 222.47 seconds. Shared-account
deltas CNY2.36 / 0.47 are not attributable per-condition savings. FULL scenario
cost fell 25.10%, output tokens 21.99%, but wildfire slowed 67.51% and its requests
rose 24 -> 38, output tokens 15222 -> 41192. The unchanged partial score was not
counted as a full success. This is a small stochastic sample, not uniform speedup.

The second run had 259 HTTP200 model responses with usage, eight passing native
audits/reconciliations and eight matching pipeline replays; owned containers were
removed. Twelve solver Bash failures were intermediate command failures, not
twelve retries or harness crashes. FULL sleep-plus-echo waits fell seven -> zero;
the first run spent 286.31 task-seconds waiting, 114.72 without an observed worker.
The repaired wait guard was never invoked in the second run, so a guard-caused
saving is not established. Emitted context fell 250183 -> 103834 characters with
241 -> 169 references; controlled same-event replay alone reduced characters
44.0% while retaining all 241 references. All four decision gates passed on
nonconflicting pools, not a test of conflicting-candidate stale-read repair.
Token output per summed request-second was 143.21 -> 142.52, not a pure decoding
benchmark. The first run's 289 responses and the twenty-task effective subset
are retained separately; subset comparisons omit unknown/replaced failed costs.

## Recorded Formats

Historical FULL/OBS stores contain recorded observations, typed intermediate
targets, final candidates, access receipts, hook deltas and decision-view/read/
select/check records. Version-v3 and v4 evidence must not be relabeled or migrated.
Pointer/truncated outputs are not complete executions; a native persisted-output
snapshot is not reconstructed stdout. Repeated execution is not voting, and access
or a consistent selection is not semantic correctness. Missing coverage remains
unknown. These are read-only interpretation rules, not active tools or launch APIs.

`analysis.historical_workspace` reads stored snapshots without reconstructing a
retired decision engine. `python -m analysis.evidence_usage --report EXPORT
--output FRESH_JSON` exports payload-free trajectory measurements; active generic
timing/request analysis has separate owners. No report generation calls a judge
implicitly. Original paid sources retain the full historical contracts.
