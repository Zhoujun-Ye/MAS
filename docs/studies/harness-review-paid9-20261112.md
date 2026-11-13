# Harness Review And Nine-Solver Regression

## Findings And Boundaries

- Krama replay previously ignored the return code of an unbounded `docker rm`.
  Cleanup failure could leave a replay running while reporting a model/runtime
  error or a matched pipeline. Removal is now bounded and verifies structured
  container absence. A cleanup failure is a harness error, preserves the execution
  diagnostic and raw answer grade, blocks a paid judge and stops matrix dispatch.
- The T=1.0 round exposed a telemetry boundary: a final Docker OOM flag could
  coexist with zero OOM events in the last available cgroup samples. Future
  resource summaries retain positive Docker OOM evidence, the original sampled
  flag and unchanged event counts separately. This repair is free-validated;
  neither paid source nor either round's raw resource records is rewritten.
- Tests had sub-second real-time bounds, fixed sleeps for monitor observations,
  and a real-clock assumption in digest-cache tests. Replace these with typed
  timeout assertions, finite slow responses, controlled clock/timer cases and
  explicit observation boundaries. Real deadline/process tests remain. Exact
  raw-log preservation, frozen prompts and whole-output credential-leak checks
  remain intentional contracts, not assertions to remove indiscriminately.

The earlier background-wait ceiling and asynchronous delegation-race fixes stay
in place. Model-generated wrong sheet names, mismatched pipeline/submission
answers, bad reasoning, unhelpful workers and wrong final answers remain model
evidence. Do not repair their submissions, change organization prompts, relabel
unknown execution as model error or alter historical scores.

## Authorized Paid Scope

The user approved nine new solvers, budget CNY20 and at most three one-call
semantic judges, zero retries. Three existing diagnostic tasks are selected for
their recorded failure mechanisms, not a fresh independent quality test:

| Task | Historical Mechanism | Scoring Type |
| --- | --- | --- |
| `astronomy-easy-5` | Native delegation instruction not followed before enforcement | numeric exact |
| `biomedical-hard-7` | Model-generated missing worksheet; useful replay stderr previously masked | numeric exact |
| `biomedical-hard-8` | Native print background-wait ceiling killed an active worker | list exact |

Each task receives Single, Native and frozen Structured once. These types need
zero semantic judges, so the three-call authorization remains unused. Keep
thinking disabled/T=0.7, effort none, CPU8/thread4, unchanged 3600-second Krama
deadline, no loop detector and no retries. Solver concurrency is three; up to two
offline graders share those same CPU reservations. Preserve all failures and costs.

Use fresh free native admission, asynchronous-delegation, background-wait and
Docker replay checks plus the complete offline suite before dispatch. Freeze the
task ID/hash manifest, source, proofs, runtime and protocol settings. Stop at
CNY18 observed shared-account spend to leave CNY2 in-flight margin; this is an
operational stop-loss, not a provider hard cap or exclusive cost attribution.
No replacement, extra task, model retry or historical regrading is authorized.

Frozen source: `/home/zhoujunye/mas-stages/20261112-harness-review-paid9-01`.
Free receipts: `/home/zhoujunye/mas-data/receipts/harness-review-paid9-20261112-01/`.
New output: `/home/zhoujunye/mas/outputs/krama-harness-review9-20261112-01`.
This run tests engineering mechanics on reused tasks, not a causal quality gain.

## T=0.7 Completion

All nine solver slots and nine offline grades finished without retry or judge.
Eight sessions exited normally; Native `astronomy-easy-5` exhausted the unchanged
3600-second deadline (recorded native-process interval about 3600.56s), with no
submission. Its timeout score remains zero and its lifecycle audit does not pass.
It did start a native worker. Manual trace checks show successful ordinary Bash
execution and repeated requests to recheck the same kind of NumPy slice result,
not a missing-delegation denial or the former 600-second background-wait ceiling.
The host ledger records 1,712 model requests for this attempt; no runtime loop
detector or post-session repetition classifier was executed.

The eight submitted pipelines all matched their submissions and all eight replay
containers were verified removed. All nine solver containers were stopped and
removed; no owned socket remained. No upstream 5xx/transport degradation or new
replay infrastructure failure was observed. Wrong answer contents/shapes under
the frozen metric remain untouched; replay agreement is not semantic correctness.

| Condition | Raw Mean Over Three Tasks | Passed Native Audits |
| --- | ---: | ---: |
| Single | 0.6667 | 3/3 |
| Native | 0.3333 | 2/3 |
| Structured | 0.3333 | 3/3 |

Shared-account balance decreased CNY14.17, below the CNY18 stop-loss. All 1,844
model requests have observed terminal usage; unknown-usage count is zero. This
is not an exclusive invoice or evidence that a specific temperature caused the
behavior. `final-verification.json` preserves complete per-attempt status and
accounting. Read-only export left 674 new-run files unchanged; 149,597 entries in
the pre-existing paid-source/evidence/credential manifest also rehashed unchanged.
The paid source remained frozen. The final pre-dispatch server suite passed
1,244 tests; ten fake-provider native checks and six real Docker replay-origin
cases passed. Preserve preliminary failed free-check logs as development evidence.

## Subsequent T=1.0 Authorization

After observing sustained successful but repetitive model-directed debugging in
the T=0.7 Native astronomy attempt, the user selected thinking off/T=1.0 as the
future default and separately approved a new nine-solver round with an independent
CNY20 budget (CNY18 account stop-loss), zero judges and zero retries. Same tasks,
conditions, prompts, CPU8/thread4, concurrency three plus two offline graders and
3600-second task limits. Do not hot-change or replay the T=0.7 source/results.
The motivation prioritizes repetition risk over sampling variability; one
trajectory does not isolate a causal temperature effect or guarantee recovery.
No loop detector or automated answer correction is introduced.

New frozen source: `/home/zhoujunye/mas-stages/20261112-harness-review-t1-paid9-01`.
New receipts: `/home/zhoujunye/mas-data/receipts/harness-review-t1-paid9-20261112-01/`.
New output: `/home/zhoujunye/mas/outputs/krama-harness-review9-t1-20261112-01`.
The second budget and accounting interval start independently after the first
round ends. This does not expand either round beyond nine solvers.

## T=1.0 Completion

All nine new solver slots and offline grades finished without retry or judge.
Eight sessions exited normally. Native `astronomy-easy-5` now finished in about
130.91s with score 1; its T=0.7 attempt's timeout and 1,712 requests remain a
separate retained observation, not replaced by this result. This single round
does not establish that temperature caused or eliminates repeated behavior.

Native `biomedical-hard-8` exited with CLI code 137 after about 896.39s. The
solver container's recorded Docker state has `oom_killed=true`; sampled memory
peaked at 8,588,152,832 bytes under the unchanged 8-GiB limit. The generated
pipeline also independently exited 137 in offline replay, with structured
Docker state `OOMKilled=true`. This reproduces resource exhaustion of the
submitted program under the frozen limit, not a Docker launch failure. Its
raw score is zero and native lifecycle audit does not pass. Do not enlarge the
limit, rewrite/optimize its pipeline, normalize its answer or retry it.

The original sampler recorded zero observed `oom`/`oom_kill` deltas and
`oom_observed=false` despite the Docker terminal flag. Preserve that contradictory
raw observation and the paid source; the future telemetry fix above prevents
the summary from discarding positive terminal evidence without inventing counts.
The other eight pipelines matched their submissions. All nine replay containers,
all solver containers and all owned sockets were removed, including the OOM case.

| Condition | Raw Mean Over Three Tasks | Passed Native Audits |
| --- | ---: | ---: |
| Single | 0.6667 | 3/3 |
| Native | 0.3333 | 2/3 |
| Structured | 0.6667 | 3/3 |

The independent shared-account interval decreased CNY1.30, with 228 model
requests and zero unknown-usage requests. Both rounds are retained, costed and
reported, never best-of selection. The read-only export left 684 new-run files
and the same 149,597 pre-existing protected entries unchanged. Source stayed
frozen. The T=1.0 pre-dispatch suite passed 1,244 tests with ten fake-provider
native checks and six real Docker replay-origin checks. These test engineering
mechanics, not broad answer-quality gains or a guarantee against repetition.

## Post-Run Free Release Validation

The OOM-summary correction was added only after both paid sources were frozen
and both rounds had finished. It changes observation reporting, not model
requests, memory limits, prompts, scoring or submitted programs. Its release
source is `20261112-harness-review-release-01`; receipts are under
`/home/zhoujunye/mas-data/receipts/harness-review-release-20261112-01/`.
The full server suite passed **1,253 tests, no skips**, including nine controlled
Docker-flag/cgroup-sample combinations. The existing free 64-MiB Docker OOM
probe also passed and removed its owned container. There was no paid rerun of
this reporting-only change. Future default remains thinking off/T=1.0.
