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

The separately authorized full environment preparation uses environments.py
with --registry-mirror and --expected-image-ids for server-side pulls. The latter
is an independently obtained official image/config-digest map (or import receipt
list); a mirror mismatch is rejected before creating the official tag. No daemon
configuration changes are needed. Public dependencies use prepare_dependencies.py;
prepare_public_assets.py fetches the PDF and --asset tiktoken fetches the six
tokenizer files with the hashes declared by the task source.

Run native_check.py --all-tasks --selection SELECTION --jobs 4 for one deduplicated
offline queue. It exports separate all/ and selected/ admission directories.
An exclusive queue lock prevents duplicate launches. Successful cases are cached
by pair, pinned benchmark revision, exact environment and validation-code SHA256;
failed, interrupted, changed or fingerprint-less cases are never reused. Per-case
cache writes are atomic and old attempts remain immutable. A new output directory
can resume after interruption without rerunning already verified matching cases.
Code/environment changes during a case invalidate its evidence. Paid admission
also checks the current validation fingerprint. The authorized paid queue now
uses --task-concurrency 4, with separate worker containers, budgets and artifacts
for every task. Generic bounded dispatch lives in harness/runner.py: stop new
work on an engineering failure, but drain in-flight jobs without discarding them.
An exclusive paid-batch lock prevents duplicate launches. No automatic paid retries.
The grader verifies the full recorded runtime environment, including derivative
image IDs, rather than comparing a derived image against the original tag.
--grade-output stores a new immutable correction without overwriting a failed
grading attempt. --reuse-run RUN CORRECTED_GRADE explicitly carries a compatible
completed attempt into a fresh batch, with provenance and zero new model calls.
verify_workers.py --all-tasks probes actual sanitized worker containers. All
three require --authorized-local-evaluation and fresh --output directories.
pilot.py requires both admission directories and the fixed twenty-pair selection.

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

Agent tool output is displayed in 30,000-byte pages; complete output is retained
privately and retrievable with read_output. Snapshot export uses a separate
2,000,000-byte workspace adapter. Normal command exit codes (including pytest
failure or grep no-match) are evidence, not transport failures. A private shell
completion marker distinguishes them from Docker/timeout execution failures.
write_file creates parents; scratch is precreated and ignored. read_file supports
metadata_only=true for bounded SHA-256 checks without reopening a submission.
Member limits and sender policy are frozen in the manifest. The async free-communication
pilot has no model-turn, message-count or evidence-read cap. Each member has
no cumulative-token ceiling, each worker 150 domain calls, and leader no domain
tools. Task active time is 2,400 seconds; provider timeout is 300 seconds with no
automatic retries. Tool allowances are nontransferable. Generic context capacity
reserves 65,536 output tokens and 8,192 margin within 1M tokens; no history trimming.
Cleanup can exceed the active-time deadline. See experiment1.md for sizing assumptions.
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
supplies the isolated-docker-cli-v8 execution backend. Before invoking Docker,
it accepts explicit and terminal code snapshots, including incomplete runs;
report-only snapshots, stale IDs and digest/patch/base mismatches are rejected. No cloud backend, model
judge or automatic dependency installation is used. The official evaluator creates
a separate fresh sandbox, merges submitted patches and runs both feature suites.
The backend enforces network=none, no mounts, 4 CPUs, 16 GiB memory, 512 PIDs,
dropped capabilities and no-new-privileges, with bounded evaluator lifetimes.
Hugging Face/Transformers use offline cache lookup rather than retrying blocked
network metadata requests. CPU-library/Go/Cargo parallelism is fixed at four,
matching the container CPU quota rather than the host's 128 visible CPUs.
Evaluation reuses the generic command-completion marker: a runner's own nonzero
exit (including its test timeout) is a test outcome, not automatically a Docker
transport error. Actual sandbox deadline/transport failures remain separate.
Large evaluator patch-writing scripts travel through stdin, not oversized shell
arguments; the real-container probes verify a 200,000-byte transfer without loss.
Hash-pinned flit_core 3.11.0 and poetry-core 1.9.1 wheels are copied and installed
offline into both worker and evaluator containers. Official tags and upstream
tests are not modified. When official dependency caches cannot support offline
execution, prepare_dependencies.py builds a project-only derivative using public
dependencies, with no hidden tests, solutions, mounts or credentials. Only this
preparation container has network access, using the Tsinghua package mirror.
The immutable receipt binds the official base ID, derived image ID and commands;
workers and evaluators use the same derivative, still with network=none.
Gates and manifests record both image IDs; changing either invalidates admission.
Outlines caches uv resolution/build inputs; DSPy retains the official litellm
1.77.1 pin and installs its matching proxy dependencies. Datasets retains a local
PyArrow 20.0.0 wheel because its official runner uninstalls and reinstalls PyArrow
on every evaluation. Per-image package-index/find-links settings are recorded;
one repository's uv cache index does not override another repository's cache.
Tiktoken installs its declared setuptools-rust build dependency in the system
environment while preserving the image's ignored native build cache. Its six
public vocabulary files are SHA256-verified and installed in the normal tokenizer
cache; tokenization itself is unchanged.
LlamaIndex removes the separately installed released core and its package cache,
then installs the task's core editable. Public tokenizer data is preserved outside
the repository so the runner's clean operation cannot delete it.

Two explicit offline transport adaptations live in offline_assets.py, not in the
Team harness. LlamaIndex's public W3C PDF is fetched on the server and SHA256-bound
in each environment manifest; requests/httpx GETs for that exact URL receive the
unchanged PDF bytes. Outlines 1706's llama.cpp loader resolves an exact filename
from the image's existing HF cache instead of querying an online file listing;
it runs the real model with the original constructor arguments. Missing files or
unsupported filename patterns fail, never substitute dummy models. Neither
adaptation changes repository code, test assertions or test selection. Workers
and evaluators receive the same transports and remain network-isolated.
native_check.py verifies base-fail/gold-pass gates before
pilot.py can launch the fixed twenty pairs once; failed gates are not replaced.
For Go admission baselines, the unchanged official runner uses bash -x: its set -e
otherwise exits at a failing captured go test command before printing the test
output. Tracing retains the actual assertion failures for the gate. Paid grading
still uses the unmodified official invocation; diagnostic baseline counts are not
benchmark outcome metrics.

Every agent receives the exact joint acceptance contract: ordinary git merge,
zero conflicts, both test suites on the merged tree, no external conflict fixer.
Unlike upstream PR mode, this adaptation has no shared remote/PR service and
permits explicit peer-code integration and identical submitted patches. The
leader coordinates delivery, but the team chooses its own collaboration strategy.

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

The dated twenty-pair authorization and fixed sample are in experiment1.md.
Native gate and paid-attempt artifacts are separate; a prepared image, scripted
control-flow check or successful submission does not establish benchmark success.
Model headroom, costs and collaboration mechanisms require measured attempts;
causality requires later interventions. Other projects' images/environments are
not reused or altered. Selecting CooperBench alone does not authorize new runs.

## Validation Entry Points

Run server pytest for member-local limits, nonblocking snapshots, explicit
submission, message provenance, tool execution semantics and Git sanitation.
scripts/cooperbench/verify_workers.py checks these workspace contracts in the
selected or all official images without model calls. scripts/cooperbench/native_check.py
checks actual baseline failure and individual/joint gold success independently.
Both write fresh evidence directories; historical results are not admission.
