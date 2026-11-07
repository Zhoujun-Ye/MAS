# CPU8 FULL / Structured trajectory audit

## Scope and evidence

Read-only audit of the 40 effective attempts in
`krama-cpu8-paired-20261106-03-effective-export.json`, including the three
authorized upstream replacements. Original failures and all incurred requests
from this paired batch remain retained. No paid experiment, judge, retry or environment installation was
performed for this audit. These are repeatedly used validation questions, not an
independent final test.

Server receipts: `/home/zhoujunye/mas-data/receipts/cpu8-trajectory-audit-20261106-01/`.
`audit-final.json` records per-task counts, timing unions and input hashes;
`compute-threads/summary.json` records the offline numerical probe.
Reproduce the read-only audit with `python -m analysis.evidence_usage --report
<effective-export> --output <new-output>`. It exports no task or answer payloads.

## Outcome and mechanism use

Both conditions score 0.7453846154 with 14/20 fully correct. All 20 paired task
scores are identical. FULL averages 7.732 minutes versus Structured's 7.366
(about 5% slower). This does not establish a general tie or causal mechanism
effect: prompts and worker composition differ, the sample is small and the
provider/runtime is stochastic.

- All 20 FULL stores are available. Lead calls include 32 `decision.view`,
  23 `decision.check`, seven `decision.read`, seven `obs.list` and four
  successfully recorded `decision.select` calls. Five native select attempts
  include one unsuccessful attempt; successful store records are not an error log.
- No `obs.read`, `obs.search` or `workspace.trace` calls were recorded. Lead
  list previews exposed 33 worker observations across five tasks. Decision reads
  accessed worker-representative candidates three times across two tasks. Only
  one task recorded worker-side workspace API use. Previews and reads do not
  establish comprehension or causal reliance.
- Explicit typed intermediates: 13 records in only two tasks, both already
  correct; none in the five zero-score tasks. Thousands of weak numeric hints
  are not declared, comparable estimands or selectable answers.
- Sixteen final candidate pools are singletons; four contain conflicts. Three
  conflicts contain a correct candidate and select it, but Structured already
  succeeds on all three. The fourth selects an incorrect candidate from a pool
  with no correct candidate. There is no observed incremental error rescue.
- All five zero-score pools lack a reference-correct final candidate. Consistency
  gates cannot manufacture missing evidence or detect shared semantic mistakes.
  Three checks reported execution pending before subsequent consistency. Thus
  gates were not inert, but their benefit here is execution/submission hygiene,
  not demonstrated semantic correction. Host final checks are not evidence that
  the model deliberately compared alternatives.

The failure is upstream of final selection: insufficient target-aware candidate
construction, sparse intermediate contracts and sparse cross-worker evidence
inspection. Collection succeeded; meaningful use was limited. This audit cannot
show what would happen without the mechanism on exactly the same trajectory.

## Five Zero-Score Cases

Private source data and reference values remain server-side; categories below
describe the discrepancies without publishing those values.

| Task | Observed failure | Why consistency was insufficient |
| --- | --- | --- |
| environment-hard-7 | Fraction versus percentage-point scale and rounding order | Workers shared the same unit interpretation; singleton agreement was wrong |
| astronomy-hard-12 | Epoch filtering and field-definition discrepancies; sensitivity output not promoted into target-aware candidates | Correct-reference numeric occurrence exists only among weak hints, not a justified final candidate |
| archeology-easy-8 | Citation canonicalization misses uncertainty suffixes and table-specific variants | Independent recomputation repeats the same normalization assumptions |
| archeology-hard-5 | Scope, chronology and climate-column interpretation differ from reference substeps | Task/reference ambiguity requires adjudication, not a claim that majority agreement is correctness |
| astronomy-hard-11 | Requested physical model unavailable; substitute regression/climatology used instead | Completeness and agreement do not validate model identity or capability |

For the astronomy and chronology discrepancies, a reference mismatch alone does
not settle scientific correctness or whether the task is adequately specified.
No answers, grading policy or reference data were changed.

The existing image has neither `pymsis` nor `nrlmsise00`. More CPUs cannot supply
missing model coefficients. Preflight now records those capabilities rather than
silently installing packages or claiming the task is solvable. A future repair
needs explicit dependency/environment authorization and a frozen image.

## CPU Diagnosis and Implemented Infra Change

Time-weighted CPU use is about 0.490 / 0.536 cores (Structured / FULL), or
6.13% / 6.70% of each eight-core quota; measured throttling is zero. Eight-core
quotas are ceilings, not CPU reservations or proof of parallel work.

Within CLI windows, unioned model-inflight time covers 80.80% / 80.64%; Bash
intervals cover 35.15% / 49.12%, overlapping model intervals by 17.02% / 31.07%.
These intervals must not be added. Inflight includes provider computation,
queueing and transport, not measured pure idle time; Bash includes sleeps and IO,
not CPU work. Sleep-bearing commands occur 10 / 25 times. FULL has more Bash
calls (1320 versus 1090) but fewer Agent calls (43 versus 47). Frozen Structured
instructions discourage polling; this is a prompt confound, not solely infra.

The numerical libraries were forced to one thread. Added an explicit
`--compute-threads` setting through the Krama launcher, matrix driver, frozen plan
and container environment. Default remains one; non-default values must not
exceed container CPUs. Preflight records actual numerical thread pools and model
package presence. Historical plans and baseline prompts are unchanged.

Offline, network-disabled Docker probe: seeded 2304-square matrix multiplication,
warmup plus five measurements, serial settings in the same existing eight-core
image, no credentials/task data/agents. Median seconds: 1 thread 0.4039;
2 threads 0.2099; 4 threads 0.1082; 8 threads 0.0741. Actual pools match settings;
checksums match for this probe. This demonstrates approximately 1.92x/3.73x/5.45x
BLAS speedup, not an end-to-end benchmark improvement.

Thread limits are per process: simultaneous native workers can oversubscribe the
same quota. Prefer a measured two/four-thread setting for future authorized
compute-heavy trials, not eight threads for every worker by default. Pure Python,
SQL/IO and sequential model/tool dependencies do not become parallel from BLAS
settings. Higher task concurrency also needs provider-rate and memory admission;
this audit does not authorize more paid attempts or a custom scheduler.

## Priorities Before Any New Paid Run

1. Resolve capability gaps and task/reference ambiguity with explicit frozen
   environment and benchmark decisions; do not tune answers against this set.
2. Improve generic observability of candidate provenance, target/unit contracts,
   failed workspace calls and actual evidence consumption. Any solver-prompt or
   selection-policy change requires separate authorization; none was made here.
3. Measure representative offline computation at bounded thread/process counts.
   Do not optimize CPU percentage by adding redundant work or hidden retries.
4. Evaluate mechanism efficacy with a matched prompt/control design, not a causal
   conclusion from this FULL-versus-Structured comparison.

Raw evidence, original failures, frozen stages and billing
records from the current paired batch remain protected. Only regenerable caches are cleanup candidates; see
`docs/archive.md` for retention boundaries.

## Verification

Active server source passed 612 offline tests in 16.18 seconds. The test receipt
is `pytest.txt` in the audit receipt directory. These fake-CLI/unit tests do not
establish paid-provider behavior or end-to-end benchmark gains. The Docker
numerical probe supplies the separate live-container capability check. Baseline
prompt checks pass, no judge/evaluator change was made, and no paid experiment
was launched. Local `git diff --check` also passes.

Server cleanup removed 45 disposable parsed-output directories (2,769 files,
7,803,830 bytes) and 17 active-source bytecode files (141,250 bytes). All 89,290
remaining regular, non-symlink output files have the same aggregate content/path
hash before and after cleanup. Exact manifests are in `cleanup.json` and
`source-cache-cleanup.json`. Local source directories had no such bytecode caches.
This describes the initial conservative cleanup only. On 2026-11-07 the user
subsequently authorized deleting all older results and retired compatibility
source; the current retention policy is in `docs/archive.md`.
