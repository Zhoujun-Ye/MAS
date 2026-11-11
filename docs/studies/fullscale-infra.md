# Full-Benchmark Infrastructure

Canonical batch admission, recovery and telemetry. The Structured organization
prompt, model and task ordering remain unchanged. Current shared web transport
and task limits are in [web-infra.md](web-infra.md); HDR remains 1800 seconds.

## Frozen Full Manifests

`scripts/studies/freeze_manifest.py` creates `benchmark-full-v1`: public task IDs,
task fingerprints and frozen protocol settings, never questions or gold fields.
Each selected benchmark must contain every current task exactly once, in upstream
order. Missing, duplicate, changed or reordered tasks fail validation. Validation20
remains supported with its original exact twenty-task contract.

Use `--all-tasks --task-manifest FILE` in the matrix. Different benchmark sizes
are supported; no hardcoded 104/492/380 limit is used. Task/condition pairs remain
adjacent. Non-full sampling still uses the existing seeded selection policy.

Example, planning only on the server:

```bash
python -m scripts.studies.freeze_manifest \
  --root /home/zhoujunye/mas-data --benchmarks kramabench \
  --protocol-settings docs/studies/cpu8-infra-protocol.json \
  --output /absolute/fresh/krama-full-manifest.json
```

Then pass that manifest and the same protocol settings to the existing matrix
with `--all-tasks`, explicit benchmark/conditions and matching resource flags.
Omitting `--execute` remains a nonexecuting plan. A manifest is not authorization.

Generate a fresh manifest/profile from current source. The November 7 manifest
under `infra-review-closure-20261107/` is historical web-v4 provenance, not current
web-v5 admission. Do not change Validation20 IDs or hashes to refresh settings.
Current maintenance proofs/manifests are under `receipts/maintenance-20261110/`;
all mode/configuration, effort, image and CLI bindings still require validation.

## Crash Recovery And Scoring

DataClaw/HDR use the same CPU/thread/module/probe/resource admission options as
Krama. Every task passes a real network-disabled container preflight before paid
dispatch. Source, inputs, evaluator, prompt, image, CLI/proof and resource settings
are frozen; `--execute --from-plan` rejects drift before loading credentials.
Web-enabled runs additionally require the local-network tunnel's TLS admission
check. Standalone execution also performs these checks and holds a durable claim.

The host-only file digest cache keys device/inode/size/mtime/ctime; recent files
are rehashed to avoid timestamp ambiguity. Full hashing remains available without
`--asset-cache`. It is not a dataframe/answer cache or adversarial integrity boundary.
The retained `dc-hdr-infra-20261107/hash-timing.json` measured warm DataClaw planning
at 0.121 versus 0.468 seconds for full hashing; HDR gain was small. This sub-second
preparation saving does not establish end-to-end benchmark acceleration.

The November 7 Krama inventory check covered 1,742 files / 666,850,039 bytes.
Full hashing versus warm cache took 1.89/0.82 seconds in one process and
2.02/0.98 seconds across eight independent processes; cold cache took 2.48 seconds.
An eight-thread microbenchmark was slower with caching (14.10 versus 7.42 seconds),
so no thread-throughput or solver-speed gain is inferred. Inventory fingerprints
matched. Historical timing receipts remain in `infra-final-audit-20261107/`.

Every new executed batch has a SQLite `journal.sqlite` with synchronous FULL
transactions. Solver and grading claims commit before their possible paid side
effects; completion records bind task, source/settings and exact scoring artifacts.
A controller flock prevents live ownership conflicts. Continuation creates a
single durable claim in the prior batch so two continuation batches cannot both
dispatch its remaining tasks. After another crash, continue from the latest child
batch named by that claim, not the old parent again.

`--retain-started-from` can reconstruct a crashed batch without `summary.json`.
It checks the exact frozen task/settings/source scope and prior process/container
quiescence. Live children or owned containers cause rejection, not automatic killing
or duplicate solving. Reconcile only this run's owned resources before continuing.
Multi-generation continuations inherit claims even when a controller died before
copying retained rows into its own journal.

- Deterministically unclaimed solver slots may be launched.
- A claimed slot without a trustworthy terminal report is checked against its
  host gateway write-ahead ledger. Missing/empty ledgers or exclusively local
  records mean `not_started`; any upstream-attempted record (including an unfinished
  dispatch) or malformed/unreadable ledger remains `dispatch_unknown`, without replay.
  Failed reports such as `launcher_error` or `interrupted` also undergo this check;
  the report's original status alone does not prove upstream dispatch. A batch with
  any `not_started` solver rows is marked interrupted so it can continue.
- Completed scoring is reused with exact artifact/evaluator bindings and zero new
  judge dispatches. Original receipts and incurred usage remain in prior batches.
- Claimed scoring without a result becomes `grading_outcome_unknown`, never an
  automatic paid retry or a fabricated zero score. Explicitly deterministic scoring
  can be redone; a scorer that never launched is `not_started`, not a completed failure.
  Standalone Krama `judge_once` also
  locks/binds its output, reuses completed results and preserves uncertain outcomes.
- Changed submissions, questions or evaluator source invalidate reuse. An uncertain
  external call cannot be made exactly-once merely by local bookkeeping.

Continue using the same frozen source stage. `source_manifest` is intentionally
strict, including documentation/source drift; moving to newly edited source is not
an identical-config continuation. Batches without a journal are read-only evidence,
not continuation inputs; the unsafe pre-journal continuation fallback was retired
during cleanup. Solver 5xx recovery follows validated continuation ancestors to
the original attempt, checking ancestor scope and earlier recovery claims.

`--recover-judge-5xx --retain-started-from BATCH` is a separate opt-in for a newly
authorized judge-only recovery, including a sealed batch whose solvers finished.
It requires explicit judge authorization, no new solver slots and exact artifact
bindings. Only a completed single-call judge error with retained HTTP 5xx evidence
can be replaced, once. Unknown completion, timeouts without confirmed HTTP status,
wrong verdicts and parsing errors are not eligible. Original grading/accounting
artifacts remain; report both batches' incurred costs and replacement counts.
The option itself does not grant paid authorization. Default continuation never
automatically repeats paid grading.
Planning lists the eligible task/condition set and receipt hashes in `judge_recovery`.
Execution requires `--authorized-attempts 0` and `--authorized-judges` equal to that
eligible count, not the full batch maximum; it rechecks the evidence before dispatch.
No additional, unlisted judge is launched by this recovery mode.

Grading exceptions are isolated from running solvers. Deterministic failures remain
re-gradable on continuation; a possible paid dispatch retains its unknown journal
claim and is not silently retried. Binding mismatches still reject grading rather
than bypassing validation. Operator SIGINT/SIGTERM stops queued grading, including
free scoring; a provider-fatal stop may still allow independent free scoring.

## Balance And Fatal Errors

Matrix execution now requires an explicit `--estimated-cost AMOUNT`, including remaining
solver and possible grading expense. `--budget-currency CNY|USD`,
`--budget-safety-factor` (default 1.5) and `--balance-reserve` (default 1 in that
currency) are recorded in authorization. Required initial funds are
`estimated-cost * safety-factor + reserve`; no currency conversion or historical
per-attempt price is inferred. The operator supplies the estimate after recharge.

Balance is checked before paid dispatch and periodically (at most once per thirty
seconds). Initial admission still fails closed. After verified admission, up to
two consecutive lookup failures are tolerated; the third pauses new paid dispatch.
Reaching reserve pauses immediately. Malformed responses are lookup failures,
not controller crashes. Only work actually requiring a judge checks the balance;
free deterministic grading proceeds even while paid work is paused or stopped.
Krama child snapshots are informational under matrix-owned admission. Pausing
new dispatch preserves in-flight work. Missing or malformed balance snapshots
produce unknown deltas, not a crash that prevents evaluation/summary persistence.
This is an estimate/reserve admission
policy, not a provider-enforced spending cap, nor attributable billing. Concurrent
account use, delayed accounting and in-flight calls can exceed an estimate.

The host gateway ledger's actual upstream model HTTP 401/402/403 triggers global
stopping, independent of native CLI error wording. The Krama child monitor also
reads only these ledger records: transcript text (tool output, data, model text)
is never a fatal signal. Local synthetic rejections and
upstream 5xx are not misclassified as fatal credential/balance errors. Monitor
failures pause new paid dispatch without terminating other work, while fatal
401/402/403 still stop in-flight paid processes. Child watchdogs use each benchmark's
timeout plus 600 seconds of teardown allowance; an overrun terminates only that child
and pauses new dispatch. Already
committed requests may still be charged. No adapter/workflow retries are added;
native internal retry behavior remains a separate pinned-CLI verification boundary.

## Resource Evidence And Concurrency

All four benchmarks use the same shared default: 8 CPUs and 4 numerical threads
per solver, for both Single and Structured. Child commands always pass these
settings explicitly; plans record both even when using defaults. Explicit study
overrides must be frozen, never inferred from a benchmark or applied mid-run.

With `--record-resources`, all four benchmark runners capture CPU plus memory
usage, sampled maximum, available cgroup lifetime peak, `memory.events` deltas and
OOM counters. Missing kernel counters are unknown, not zero. This server lacks
`memory.peak`; its sampled maximum is not advertised as the true peak. Container
`OOMKilled` and init exit code are captured before removal, separately from the
solver's `docker exec` exit code and intentional adapter shutdown.

Solver concurrency is explicit 1..256 (default 8), grading 1..64 (default 2).
Separate bounded pools grade each solver artifact as it finishes; they no longer
wait for every solver. Total possible simultaneous paid processes are the sum of
solver and judge concurrency, which must be considered in provider capacity planning.
Runtime admission rejects CPU reservations above host CPU capacity and
conservatively checks eight GiB per solver against 90% of host
available memory and records capacity. These are configuration bounds, not validated
provider throughput recommendations. No automatic concurrency ramp, quota reduction,
sorting, environment provisioning or native worker scheduling is introduced.

## Verification

Latest regression, tunnel and cleanup receipts live under
`/home/zhoujunye/mas-data/receipts/maintenance-20261110/`.
Superseded offline stages/test logs are disposable; paid runs and their frozen
sources remain protected by `docs/archive.md`.

The following November 7 checks remain historical verification of that source,
not a current-source admission proof:

- Actual manifest generation verified Krama 104, DataClaw 492 and HDR 380 tasks,
  with upstream order and fingerprints preserved.
- A three-benchmark nonexecuting readiness plan validated 1,952 solver slots and
  a conservative 1,836 maximum grading calls, solver concurrency 8 and judge
  concurrency 2 with the current CPU8/thread4 profile and web-v4 manifest.
  Image/CLI/condition proofs passed. No solver output namespace
  was created and no credentials were loaded. This is not a full benchmark run.
- Linux fork tests abruptly exited the controller after solver claim and during
  scoring, then continued without `summary.json`. Unknown attempts were not rerun;
  completed grading was reused and uncertain grading stayed unknown. Tests also
  cover inherited claims, changed source, reserve pauses and an opaque host HTTP
  402 stopping queued solver dispatch without relying on CLI text.
- The bounded OOM probe used the existing image, network none, synthetic credentials,
  CPU1 and a temporary 64-MiB limit. A 128-MiB allocation exited 137; cgroup counters
  showed `oom=1`, `oom_kill=1`, and the owned container was removed. No packages,
  dataset mounts, paid calls or lasting environment changes were involved.

Grading overlaps solving. The implementation does not infer task costs, retry
unknown outcomes, install physical models or claim native-runtime correctness
from offline fixtures. The actual paired smoke is recorded separately in
[threebench2-engineering.md](threebench2-engineering.md).
