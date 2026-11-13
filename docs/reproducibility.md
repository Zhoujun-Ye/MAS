# Reproducibility

## One Effective Inference Policy

`harness/runtime_support/inference.py` owns the defaults and request checks.
Current solver defaults are `--effort none`: DeepSeek thinking disabled,
fixed temperature 0.7, effective reasoning effort null/not applicable. This replaces
the erroneous max default; high remains the user's requested setting if thinking
is explicitly re-enabled. Historical actual high/max, T=0 and T=1.0 runs are not rewritten.
On November 12 the user removed the loop detector entirely, including observation
counts, warnings, worker stops and loop-triggered host termination. Native event
recording, strict-Single permissions and mandatory delegation remain. The temporary
temperature pilot and sampling overrides have been removed. The twelve completed
T=0.7 pilot attempts did not reproduce the screened pattern; that is not a guarantee
against loops or of identical repeated answers.

The pinned Claude CLI receives `MAX_THINKING_TOKENS=0`,
`CLAUDE_CODE_EFFORT_LEVEL=auto` and `CLAUDE_CODE_EXTRA_BODY` containing explicit
`thinking.type=disabled` and `temperature=0.7`. Auto here suppresses the native
effort field; it does not enable provider thinking. A free native experiment
confirmed that merely unsetting effort still sent high, so omission alone is
not sufficient. Do not use the unrelated display-only thinking toggle.

The host gateway validates model-message parameters before upstream dispatch and
rejects drift locally. It never rewrites the native body. Host receipts record
model, thinking, temperature, top-p presence, requested max_tokens and effort,
without message payloads. A thinking-off run needs native proof of the exact
sampling policy, not an old effort-only proof. Main and worker requests are
covered by the same guard. The semantic judge also sends temperature zero and
thinking disabled, once per eligible submission, with no retries.

Native output limits remain native defaults, observed per request rather than
silently capped. The free pinned-CLI probe observed max_tokens=32000 in its main
and worker requests; that is not a universal provider output-limit guarantee.

References, checked November 11:
[DeepSeek Anthropic parameters](https://api-docs.deepseek.com/guides/anthropic_api/),
[thinking and effort](https://api-docs.deepseek.com/guides/thinking_mode/),
[native environment controls](https://code.claude.com/docs/en/env-vars).
DeepSeek temperature takes effect in non-thinking mode; it is ignored/fixed in
thinking mode. Flash fixes top-p at one in non-thinking mode, so no fake top-p or
unsupported seed control is claimed.

## Stable Inputs And Runtime

Keep the same twenty public task IDs/fingerprints, sampling seed, condition order,
frozen organization prompts, shared task rules and scoring contract. Record exact
source, image ID, native CLI version/binary hash, data inventory, arguments and
effective inference/environment settings. Independent workspaces prevent answer
sharing between conditions; input data are read-only. Native settings/profiles
stay isolated, updates/nonessential traffic disabled, retries zero.

Every container explicitly receives CPU8/thread4, numerical thread environment
variables, `OMP_DYNAMIC=FALSE`, `MKL_DYNAMIC=FALSE`, `PYTHONHASHSEED=0` and `TZ=UTC`.
The Python hash seed fixes hash randomization, not NumPy/sklearn/model random
seeds. Do not claim all solver-produced stochastic algorithms are seeded, inject
site hooks or rewrite submitted pipelines after solving. Record and inspect the
actual generated pipeline instead.
Offline Krama replay receives the same hash seed, timezone and numerical-thread
environment, so it does not silently reintroduce Python hash randomization.

## CPU Verification

`scripts/probes/cpu_compute.py` uses the existing no-network image and no model
calls. Serial one/two/four/eight-thread BLAS checks record actual pools, CPU time
and wall time. A separate pair of concurrent four-thread numerical processes
checks the real eight-CPU Docker quota and records cgroup utilization/pressure.
Results establish numerical capability, not end-to-end benchmark acceleration.
The November 11 free run measured median one/four-thread times of 0.4067/0.1205
seconds (about 3.4x for this kernel). Two four-thread processes in an inspected
eight-CPU container averaged 5.81 cores. Receipt:
`/home/zhoujunye/mas-data/receipts/reproducibility-20261111-01/cpu/summary.json`.

Do not fill idle cores with artificial work, impose a new worker schedule or
rewrite queries to make utilization look high. Pure Python, sequential SQL and
model/network waits do not become parallel simply because a container has eight
CPUs. Concurrent native workers share the same quota and can contend for it.

## Limits

Temperature zero reduces sampling variation; it does not promise bitwise-identical
responses. Provider model aliases/weights, routing, kernels, batching and shared
cache/load can change outside this repository. Native background completion order
can change a lead's context, even with the same seed and sixteen solver slots.
Multithreaded numerical reductions may differ at floating-point precision.

Record concurrency and complete native/gateway/resource evidence. Keep failed,
cancelled and unknown-usage calls; do not relabel unknown charges as zero or pick
the best repeated answer. Multiple repeats would need separate paid authorization.
Current work is configuration hardening and free verification; paid dispatch stays
on hold for the requested configuration review.
