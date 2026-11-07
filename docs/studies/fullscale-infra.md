# Full-Benchmark Infrastructure

Implemented 2026-11-07 with offline server authorization only. No paid solver,
judge, retry or balance API call was made for this repair. Task ordering, prompts,
models, timeout policies, CPU defaults and automatic retry policy are unchanged.

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

## Crash Recovery And Scoring

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
- A claimed slot without a trustworthy terminal report is `dispatch_unknown` and
  is retained without another solver call, even if the claim preceded actual dispatch.
- Completed scoring is reused with exact artifact/evaluator bindings and zero new
  judge dispatches. Original receipts and incurred usage remain in prior batches.
- Claimed scoring without a result becomes `grading_outcome_unknown`, never an
  automatic retry or a fabricated zero score. Standalone Krama `judge_once` also
  locks/binds its output, reuses completed results and preserves uncertain outcomes.
- Changed submissions, questions or evaluator source invalidate reuse. An uncertain
  external call cannot be made exactly-once merely by local bookkeeping.

Continue using the same frozen source stage. `source_manifest` is intentionally
strict, including documentation/source drift; moving to newly edited source is not
an identical-config continuation. Batches without a journal are read-only evidence,
not continuation inputs; the unsafe pre-journal continuation fallback was retired
during cleanup. No 5xx recovery policy or paid authorization was broadened.

## Balance And Fatal Errors

Matrix execution now requires an explicit `--estimated-cost AMOUNT`, including remaining
solver and possible grading expense. `--budget-currency CNY|USD`,
`--budget-safety-factor` (default 1.5) and `--balance-reserve` (default 1 in that
currency) are recorded in authorization. Required initial funds are
`estimated-cost * safety-factor + reserve`; no currency conversion or historical
per-attempt price is inferred. The operator supplies the estimate after recharge.

Balance is checked before paid dispatch and periodically (at most once per thirty
seconds). Missing/unavailable balance or reaching reserve pauses new dispatch;
already running work is allowed to finish. This is an estimate/reserve admission
policy, not a provider-enforced spending cap, nor attributable billing. Concurrent
account use, delayed accounting and in-flight calls can exceed an estimate.

The host gateway ledger's actual upstream model HTTP 401/402/403 triggers global
stopping, independent of native CLI error wording. Local synthetic rejections and
upstream 5xx are not misclassified as fatal credential/balance errors. Monitor
failures also stop dispatch rather than silently disabling protection. Already
committed requests may still be charged. No adapter/workflow retries are added;
native internal retry behavior remains a separate pinned-CLI verification boundary.

## Resource Evidence And Concurrency

With `--record-resources`, all three benchmark runners capture CPU plus memory
usage, sampled maximum, available cgroup lifetime peak, `memory.events` deltas and
OOM counters. Missing kernel counters are unknown, not zero. This server lacks
`memory.peak`; its sampled maximum is not advertised as the true peak. Container
`OOMKilled` and init exit code are captured before removal, separately from the
solver's `docker exec` exit code and intentional adapter shutdown.

Solver concurrency is explicit 1..256 (default 8), grading 1..64 (default 2).
Runtime admission conservatively checks eight GiB per solver against 90% of host
available memory and records capacity. These are configuration bounds, not validated
provider throughput recommendations. No automatic concurrency ramp, quota reduction,
sorting, environment provisioning or native worker scheduling is introduced.

## Offline Server Evidence

Stage: `/home/zhoujunye/mas-stages/20261107-fullscale-infra`.
Receipts: `/home/zhoujunye/mas-data/receipts/fullscale-infra-20261107/`.

Active-server regression: **624 passed in 19.11 seconds**, no skipped tests
(`pytest-active.txt`). The code was deployed through scoped source sync. These
tests establish offline behavior, not full-benchmark provider capacity or speed.

- Actual manifest generation verified Krama 104, DataClaw 492 and HDR 380 tasks,
  with upstream order and fingerprints preserved.
- A three-benchmark nonexecuting readiness plan validated 1,952 solver slots and
  a conservative 1,836 maximum grading calls, solver concurrency 16 and judge
  concurrency 4. Image/CLI/condition proofs passed. No solver output namespace
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

Current implementation does not pipeline grading with solving, pool gateway TLS
connections, infer task costs, retry unknown outcomes or install missing physical
models. None is required to remove the full-manifest/crash/telemetry blockers.
