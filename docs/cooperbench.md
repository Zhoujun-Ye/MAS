# CooperBench Integration

Selected source: https://github.com/cooperbench/CooperBench
Pinned revision: 63b9d44d9f39a02fccf5bf0052db48a917a011fd
Use the dataset bundled in that checkout, not an unpinned latest HF download.
prepare.py rejects a dirty or mismatched checkout and reports actual inventory.

## Adaptation

Two fixed identities (worker_a and worker_b), both using the same coder template, implement one feature each in independent
copies of the same base repository. A third, communication-only leader coordinates.
This is explicitly leader-led-adaptation, not the paper's two-peer condition or
the upstream framework's team mode. No paid planning call is required.

Initial team/task metadata is generic; feature.md goes only to its assigned
worker via member_inputs. The leader can learn details through messages, not
through privileged access. All worker tools route by identity to that worker's
container. Permissions are bound through the fixed capability catalogue. Feature
IDs map to worker_a/worker_b in ascending order, but no longer to unequal templates.
Hidden tests, feature.patch and combined.patch remain outside workers.

## Preparation and Offline Checks

On the server, using the project virtual environment:

```bash
.venv/bin/python scripts/cooperbench/prepare.py --fetch
.venv/bin/python -m pytest -q
.venv/bin/python scripts/cooperbench/offline.py --scheduler controlled --output outputs/cooperbench/NEW_CONTROLLED
.venv/bin/python scripts/cooperbench/offline.py --scheduler async --output outputs/cooperbench/NEW_ASYNC
```

These checks do not install upstream dependencies, create containers, execute
hidden tests or call a model. Scripted control-flow success is not task success.

## Execution and Evaluation

run.py requires --authorized-one-paid-pair plus explicit repo, task, two feature
IDs, two containers and a new output directory. It does not provision containers.
The two containers must use the same task image, no host mounts, no network, clean
repositories at the same base commit, and /workspace/repo. Provisioning must also
set memory/CPU/PID limits, drop unnecessary capabilities and exclude credentials.
Never mount the dataset, Docker socket or other agent's workspace inside workers.
Official task images contain future Git history: a clean detached HEAD is NOT
sufficient. pilot.py sanitizes each fresh worker with base-history-only-v1 before
any model call: remove all remotes/refs/tags, expire reflogs, remove lost-found and
special ref remnants, and prune unreachable objects. Base ancestors remain.
native_check.py and run.py independently reject retained refs, remotes, reflogs,
base-external commits, recoverable unreachable objects, external object stores,
or any file in /patches. run.py verifies rather than silently sanitizing a supplied
container. Gates without the isolation version are rejected by the pilot launcher.

Agent tool output is bounded to 30,000 bytes; snapshot export uses a separate
2,000,000-byte workspace adapter. Normal command exit codes (including pytest
failure or grep no-match) are evidence, not transport failures. A private shell
completion marker distinguishes them from Docker/timeout execution failures.
write_file creates parents; scratch is precreated and ignored. read_file supports
metadata_only=true for bounded SHA-256 checks without reopening a submission.
Member limits and sender policy are frozen in the manifest. The async free-communication
pilot has no model-turn, message-count or evidence-read cap. Each member has
no cumulative-token ceiling, each worker 100 domain calls, and leader no domain
tools. Task active time is 1,200 seconds; provider timeout is 120 seconds with no
automatic retries. Tool allowances are nontransferable. Context/per-response
output guards remain unchanged; cleanup can exceed the active-time deadline.
Leader and workers are all runnable at task creation; see experiment1.md.

At submit_assignment(paths=[...]) the adapter freezes the selected implementation
files against the pinned base, including selected committed/new/deleted files.
Tests and known scratch/reproduction paths are rejected. Workers are instructed
not to modify tests and to keep all temporary work in .cooperbench_scratch/.
Capture uses a disposable Git index, not git add -A over the entire workspace;
it never alters the worker's index. Selected and excluded paths are recorded.
At failed termination, current changed/untracked files passing the same path
filter are captured for diagnosis. This fallback is not a semantic classifier
of arbitrary filenames and never changes a failed run into a successful one. It retains the
snapshot, revision and digest; final patch exports come from this snapshot,
not mutable workspace state at process exit. Later edits require explicit
reopening and resubmission. This gate blocks foreground domain-tool writes;
native validation must also ensure no detached background writer races capture.

grade.py requires --authorized-local-evaluation. native.py loads the pinned
upstream merger/test modules without importing unrelated cloud/agent SDKs and
supplies the isolated-docker-cli-v2 execution backend. Before invoking Docker,
it accepts explicit and terminal code snapshots, including incomplete runs;
report-only snapshots, stale IDs and digest/patch/base mismatches are rejected. No cloud backend, model
judge or automatic dependency installation is used. The official evaluator creates
a separate fresh sandbox, merges submitted patches and runs both feature suites.
The backend enforces network=none, no mounts, 2 CPUs, 4 GiB memory, 256 PIDs,
dropped capabilities, no-new-privileges and a 600-second evaluator deadline.
Hash-pinned flit_core 3.11.0 and poetry-core 1.9.1 wheels are copied and installed
offline into both worker and evaluator containers. Official images and upstream
tests are not modified. native_check.py verifies base-fail/gold-pass gates before
pilot.py can launch the fixed three pairs once; failed gates are not replaced.

Keep raw upstream results. This revision has a lead-patch-alone fallback after
conflicts/missing input; our strict joint criterion requires clean or identical
merge AND both feature tests passing. official_both_passed remains separately
visible. This stricter criterion is not the unqualified upstream score.
All started attempts count in the denominator. Deadlock, quota/context exhaustion
and missing submission are agent failures, not dropped/ungraded successes.
Infrastructure errors, external interruptions and unresolved grades are separate
counts. grade.json binds code_correct to exact snapshots, but correct remains
false for agent-failed runs. Neither model reports nor status=completed imply
verified success.

## Accounting and Review

Each attempt directory contains manifest.json, trace.jsonl, result.json and
accounting.json, plus per-worker .submission.json/.patch and optional grade.json.
run.py records balances before/after and usage/cost estimates even when a provider
call fails. Pricing is the frozen configured estimate, not a newly verified
quote. Account-wide balance deltas can include other users of the key; they are
not automatically attributable to this run and must not be summed over overlaps.

scripts/analyze.py accepts one run or a parent of attempt directories, includes
all started runs, reports token-weighted cache reuse and explicit unknowns.
Condition grouping includes global limits as well as per-member limits. Optional
--audit-file PATH supplies external research-validity records. Audit records
bind to exact trace SHA-256, remain outside immutable attempts and distinguish
code-test success from research admissibility. Contaminated attempts are not
silently dropped or converted into model failures.
scripts/feedback.py exports worker request boundaries (optionally --agent and
--call-t), not the unevaluated leader final answer. Reports use separate new
directories and never rewrite runs. The old results/traces layout is not supported.

## Scope and Remaining Evidence

The dated three-pair authorization and fixed sample are in experiment1.md.
Native gate and paid-attempt artifacts are separate; a prepared image, scripted
control-flow check or successful submission does not establish benchmark success.
Model headroom, costs and collaboration mechanisms require measured attempts;
causality requires later interventions. Other projects' images/environments are
not reused or altered. Selecting CooperBench alone does not authorize new runs.

## Validation Entry Points

Run server pytest for member-local limits, nonblocking snapshots, explicit
submission, message provenance, tool execution semantics and Git sanitation.
scripts/cooperbench/verify_workers.py checks these workspace contracts in the
three official images without model calls. scripts/cooperbench/native_check.py
checks actual baseline failure and individual/joint gold success independently.
Both write fresh evidence directories; historical results are not admission.
