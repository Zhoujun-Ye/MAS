# Three-Benchmark Infra Check

## Authorized Scope

The user authorized DataClaw, HybridDeepResearch and KramaBench: two existing
Validation20 questions per benchmark, once each with Single and Structured.
Maximum twelve new solver attempts, zero retries and zero paid judges. Use the
first two entries in the frozen manifest, without selecting by prior outcomes:

- DataClaw: `task_487_risk_assessment_medium_medium006`,
  `task_440_international_comparison_hard_hard011`.
- HybridDeepResearch: `parallel_016`, `s2sql_024`.
- KramaBench: `wildfire-easy-9`, `astronomy-easy-1`.

Both conditions use 8 CPUs, four numerical threads, 8 GiB memory, the unchanged
organization prompts, Claude Code 2.1.286 and current max effort. Keep benchmark
timeouts and web limits unchanged. Planned solver concurrency is four, subject
to fresh host-capacity and provider admission checks; offline grading concurrency
is two. Text answers requiring a semantic judge remain ungraded, not incorrect.
This is a diagnostic sample, not a full benchmark or twelve paired before/after
experiments. No further FDABench solver call is authorized.

Receipts: `/home/zhoujunye/mas-data/receipts/threebench-infra-20261111-01/`.
Freeze the final source/image/proofs/settings before paid dispatch. The user
separately approved the SQLite upgrade and, after validation, removal of unused
old MAS images. Historical image IDs, source snapshots and paid evidence remain.
Balance admission uses a CNY 40 estimate, 1.5 safety factor and CNY 5 reserve;
these are admission values, not a provider-enforced spending cap.

## Diagnosis Before Dispatch

The retained FDABench rerun's long 120-second Bash calls explicitly returned a
background task ID and `timedOutAfterMs=120000`. These are native handoffs, not
proof of successful query completion. Both missing-SessionEnd attempts had a
running shell in their last Stop hook. A synthetic-provider native probe
reproduced missing SessionEnd with a running background shell in both conditions,
before our container cleanup. Normal no-background native proofs passed. The
historical audit exceptions remain unverified; neither Stop nor CLI exit is
silently promoted to SessionEnd.

In the current solver image, Python uses SQLite 3.40.1. The actual slow correlated
subqueries inspected from FDA0867 and FDA1948 have repeated table scans in their
query plans. Host SQLite 3.53.1 optimizes the inspected FDA1948 EXISTS query with
an automatic index, but still scans the FDA0867 NOT EXISTS query. This identifies
a runtime-version opportunity, not a claim that upgrading fixes every SQL path.
Never add task-specific persistent indexes or rewrite the solver's SQL, change
questions, inject answers, or mutate the pinned source databases to improve a
timing result. Any upgrade must preserve compile features and validate results.

An isolated, serial BLAS probe in the existing image measured median matrix
multiplication times of 0.405 seconds with one thread and 0.108 seconds with four
threads, approximately 3.8x faster. The four-thread setting is effective for
parallel numerical kernels; it does not parallelize arbitrary Python or SQL.
These are free synthetic measurements, not end-to-end model speedups.

Resource capture now additionally records cgroup CPU/I/O/memory pressure totals
and maximum sampled-interval core use. Missing/reset counters remain unknown.
Native audits expose background handoffs and running shells at the last Stop,
without changing pass/fail rules or scheduling. These are observability repairs,
not speedup claims. Keep preparation, model inflight, tools, background lifetime,
cleanup and unknown intervals distinct in the final report.

## Validated Repairs

The accepted shared image is `mas/research-benchmarks:20261111-sqlite-v2`, ID
`sha256:feef15526fd3f6e35e55573ac991aa6b6c2e381d7b95ef92557a98cf1e88eec4`.
SQLite 3.54.1 is built from its hash-verified official full source with the prior
compile features, including generated UPDATE/DELETE LIMIT parser support.
An earlier amalgamation candidate advertised the flag but failed actual syntax
checks; it was rejected before paid use. The accepted build passed 727 targeted
upstream tests and seven executable feature checks, while retaining Poppler.

Twenty-two literal read-only SQL queries from the retained FDA1948 trace were
replayed without model calls, Python-shell replay, query rewriting or database
mutation. All 22 row-multiset hashes matched. Total query time fell from
142.316703 to 66.804194 seconds (53.1%); the database SHA-256 stayed unchanged.
The synthetic NOT EXISTS query still scanned, so this is not a universal SQL
speedup. Receipts are `sqlite-retained-readonly/summary.json` and
`sqlite-synthetic-final/summary.json`; literal queries remain server-side.

Shared containers now use Docker's init to forward stop signals and reap children.
Bare PID-1 sleep ignored SIGTERM and reached the two-second forced-kill deadline.
Interleaved free checks measured 2.1829/2.1541 seconds without init versus
0.1220/0.1214 with init, with exit 137 versus 143. This removes real cleanup
overhead, not model thinking time or the native background-shell lifecycle gap.

The frozen source passed all 827 checks (825 in its isolated stage and the two
pinned Krama integration checks with the explicit upstream path). Six free native
workflow checks covered DataClaw/HDR/FDABench and both conditions. Native injected
503 probes made one request per condition, with no adapter retry. The final
init-bound native proofs and all twelve paid task/container preflights passed.
The later active source, including stale-control cleanup, the remaining Krama
image-default correction and Docker quiescence repair, passed 838 server tests.
Paid frozen source is unchanged.

The six obsolete MAS tags, representing four old/candidate image IDs, were removed
after checking that no container referenced them. The new image, shared layers,
other projects, historical image metadata and paid evidence remain. See
`old-image-retirement.json`. All active default image references now use the
shared constant; paid entry points that require explicit image/proof still do so.

## Dispatch And Recovery Boundaries

The original batch finished with eleven `cli_exited` solvers and one
`not_started` HDR `parallel_016` Structured slot. Its execution readiness TLS
handshake failed before an attempt folder, gateway ledger or model call existed.
The original unit therefore exited 1; its failure remains in the raw evidence.

Quiescence inspection exposed a separate controller bug: Docker returned lowercase
`error: no such object`, while continuation matched uppercase `No such`. Current
source uses a successful exact-name container listing to establish absence, then
checks running state for existing containers; daemon failures and malformed state
still fail closed. Six regression cases and the 838-test suite passed.
The real-Docker `quiescence-runtime/` probe also rejected a running owned
container and accepted it only after stop/removal, with no model calls.

The paid frozen source was not patched or its source-binding check bypassed.
Instead, an explicit frozen-manifest slice launches only that never-dispatched
task/condition under `threebench-infra-20261111-01-unstarted-01`, using the identical
frozen source/image/model/prompt/limits. `unstarted-launch-argv.json` binds the
original summary and records eleven already-started slots plus exactly one
remaining authorized solver, no replay or judge. Configured concurrency remains
four, but this final one-slot batch can only have one solver active.

The Mac runner's refused stale control socket was repaired between batches, after
the original batch finished and no MAS solver containers remained. The installed
source hash matches current source and the acknowledged SSH master is live.
Clash node, subscription, DNS and routes were not changed. The user declined a
node-switch comparison; intermittent downstream TLS EOF remains an explicit
external risk, not a solved image defect. Further broad cleanup is deferred under
the user's subsequent instruction to resolve infra issues first.

## Completed Results

All twelve authorized solver slots finished `cli_exited`, with 12/12 native audits
passing, zero solver retries and zero paid judges. The original unit exited 1
because of its zero-call readiness failure; the final one-slot unit exited 0.
`effective-infra-analysis.json` assembles exactly one first dispatch per slot and
binds input hashes. Both paid batches have identical source manifests. No further
FDABench paid run was made: its repair checks were synthetic workflows and the
22 retained read-only queries, not an end-to-end post-SQLite efficacy experiment.

| Benchmark | Condition | Mean CLI Minutes | Completed-Request Output Tokens | Common Off-Peak CNY |
| --- | --- | ---: | ---: | ---: |
| DataClaw | Single | 6.57 | 105,983 | 0.706 |
| DataClaw | Structured | 5.88 | 152,029 | 0.985 |
| HDR | Single | 26.40 | 492,517 | 2.799 |
| HDR | Structured | 21.82 | 570,334, partial coverage | 2.978, partial coverage |
| Krama | Single | 2.87 | 47,920 | 0.299 |
| Krama | Structured | 4.19 | 127,237 | 0.733 |

Each row contains two questions. HDR Structured has three interrupted streams,
excluded from those completed-request token/cost subtotals. Full incurred usage
and cost are unknown. Known-request estimates total CNY 8.500679 at common
off-peak rates or 16.731358 in the peak-rate scenario, including known search
charges. Shared-account deltas were 13.73 plus 3.27, totaling CNY 17.00; that is
not a per-request invoice or independently attributable cost. Rates and source
links are recorded in the analysis JSON, checked November 11.

All three interrupted streams ended `client_disconnected` 23-29 milliseconds
after observed native TaskStop calls. They occurred before container cleanup,
consistent with native cancellation of still-generating workers, not a host
cleanup timeout or API retry. The gateway stopped forwarding and retained partial
usage as unknown. Same-UID origin remains unverified. Avoiding the model's choice
to abandon worker generation would change native strategy, not merely fix infra;
the frozen prompt and scheduling were not altered. No upstream model HTTP errors
or native retry events were observed.

Token-weighted native cache reuse was 98.43% for Single, 98.29% for Structured
leaders and 92.44% for Structured workers. These are observed role totals, not a
complete billing ledger. More CPU does not reduce generated reasoning tokens.
The November 9 three-benchmark sample used high effort, concurrency eight and
web-v4, versus max, four and web-v5 here. Its times/costs are not a controlled
before/after comparator. The earlier FDABench pair remains the matched comparison.

Every live cgroup recorded `cpu.max=800000 100000`, with zero quota throttling and
no observed OOM. Average CPU use ranged from 0.052 to 0.324 cores; maximum total
CPU pressure per run was 0.394 seconds. Model-inflight unions covered 81.8%-99.2%
of CLI time, and 96.7%-99.2% for HDR. These include provider/network/streaming time,
not pure network latency. Measured container stop times were 0.147-0.310 seconds,
and final process/container quiescence checks passed for both batches.

A free host-Unix-gateway throughput probe forwarded identical 4.33-MiB synthetic
streams in 0.086 seconds singly, or 0.523-0.554 seconds per request at concurrency
four. This checks host forwarding/parsing headroom, not the external provider or
Mac proxy. Receipts are in `gateway-throughput/`; all five requests were synthetic.

Four paid-run fetch failures were one unsupported content type, one URL-policy
rejection and two target HTTP 404 responses, not observed TLS/DNS timeouts. Fourteen
explicit tool errors contained ordinary parsing/code exceptions or nonzero exits;
none reported a missing module/command/file or permission failure. Two nonzero
exits remain unclassified rather than silently called successes. Preserve the
payload-free `tool-error-classification.json` and original traces. Six subsequent
free TLS readiness checks passed on the unchanged node; intermittent failure risk
is not disproved by that short sample.

Both HDR SQL answers scored zero in deterministic evaluation; each condition's
Krama scores were 0.907692 and 1.0. DataClaw and HDR text answers remain pending
semantic grading because no paid judge was authorized. Successful lifecycle,
working infrastructure and correct answers are separate claims.

Final verification rehashed all 192 frozen source files without changes and
recorded 1,000 protected paid-output/source entries. The two retained FDABench
manifests also remained unchanged (633 and 670 entries). No current paid evidence,
dataset, environment or other project's resource was removed. Broad cleanup stays
deferred; the earlier image/build-cache retirement has its separate receipt.
