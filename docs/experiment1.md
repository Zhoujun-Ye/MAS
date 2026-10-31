# Twenty-Pair Collaboration Study

This records the earlier twenty-pair study. The newly authorized fresh 100-pair
lite batch and superseding collaboration contracts are in
[Fresh Lite Study](lite100-20261030.md); do not apply the old limits to that batch.

Observe collaboration failures before choosing a Harness mechanism to evolve.
The team, private assignments, permissions, async scheduler and evaluator are
fixed; agents freely choose when, whom and what to communicate. No RSI updates
or prompt tuning occur inside the batch. Coding is one domain, not the definition
of the generic team runtime.

## Authorization and Selection

On 2026-10-30 the user authorized repairs, historical-result deletion, complete
pinned CooperBench environment preparation and twenty paid feature pairs once
each. Official downloads, project-isolated containers and necessary dependencies
are authorized; other projects, Docker daemon settings and credentials are not.
No aggregate monetary cap, automatic paid retries, replacement samples or expansion.

select_pairs.py freezes 20 pairs from official lite.json before gates or outcomes.
Selection is repository-stratified round robin with SHA-256 ordering under seed
cooperbench-20-20261030, covering all 12 repositories. Three observed pairs are
excluded; shared tasks/features can overlap. This is not an untouched held-out
test set or a representative success-rate estimate.

## Admission Before Payment

1. Acquire all 30 official task images and record exact image IDs. Prefer direct
   server pulls through an explicit mirror, checked against independently obtained
   official config digests. Never change shared DNS or Docker daemon settings.
   Local archive transfer is a last resort requiring a separate traffic discussion,
   not an automatic fallback. Reuse already imported layers and images.
2. Check all 30 environments with worker isolation and native baseline/gold
   evaluation on a fixed pair per task. This is environment coverage, not
   verification of all 652 possible feature pairs.
   Missing offline dependencies are prepared in project-owned derivative images,
   bound to official base IDs. Preparation may access the public package mirror;
   agents and evaluation remain offline, with no hidden fixtures in workers.
3. Independently gate all 20 selected pairs: genuine base failures, individual
   gold and joint gold success. A failed setup blocks payment, not sample replacement.
4. Pass server regressions and real-image pagination probes. Freeze runtime,
   launcher/config digest, images, sample, model settings and provisioning wheels.
5. Run up to four isolated tasks at a time, with each task's agents concurrent.
   This task-level concurrency was explicitly authorized after the first attempt.
   All started attempts count.
   Wrong code/merge conflicts continue; infrastructure or context/output/resource
   anomalies stop new paid attempts for investigation, without automatic retry.
   Already-started tasks drain and keep their results; source/configuration never
   changes in place while they execute. Per-task account deltas overlap and must
   not be summed; batch-level balance observations and token-based estimates are
   recorded separately. Explicitly reused completed runs retain original traces,
   manifests and an immutable grading correction, not a new paid sample.

## Capacity Calculation

Admission verified on 2026-10-30: 30/30 task environments and 20/20 selected
pairs passed (49 unique checks), with 30/30 real-worker probes and 178 server
regression tests passing. Evidence: outputs/setup/native-unified-20261030-01/
and outputs/setup/workers-all-20261030-04/. A separate cache check reused all 49
matching cases without executing tests again. These are setup results, not agent
success rates. The source digest at admission is cc897f478757deab.

Provider documentation checked 2026-10-30:
[model capacity](https://api-docs.deepseek.com/quick_start/pricing/) and
[request limits](https://api-docs.deepseek.com/api/create-chat-completion/).
deepseek-flash advertises 1M context and up to 393,216 output tokens. We use a
conservative decimal capacity of 1,000,000, reserve 65,536 output tokens and
8,192 framing/safety tokens, leaving 926,272 estimated input tokens. Model,
thinking=enabled and reasoning_effort=high remain fixed.

Prior smoke capacity measurements: peak prompt 82,413 tokens, peak completion
20,772 tokens, maximum worker domain calls 41, maximum active time 349.4 seconds.
These are sizing observations, not retained benchmark success evidence.
New input headroom is 11.2 times the observed peak; reply capacity 3.15 times;
150 domain calls per worker 3.66 times; 2,400-second active deadline 6.87 times.
These empirical margins cannot prove arbitrary conversations fit finite context.

The generic Agent anchors the unchanged input prefix to its last provider token
receipt and charges each appended UTF-8 byte as a token, plus message framing.
Initial requests include schemas; reasoning and tool arguments are retained.
The guard logs its estimate and refuses oversized input without dropping or
summarizing history. It is conservative, not an exact provider tokenizer.
The obsolete 800,000-character guard is disabled for this batch; there is no
cumulative-token, message-count or model-turn cap. Provider context errors and
output-length stops remain visible member-local failures, never hidden successes.

Tool responses expose at most 30,000 bytes while retaining COMPLETE output in
the owning member's private archive. read_output retrieves later pages without
rerunning commands. UTF-8 boundaries, byte counts and SHA-256 are recorded.
Paging is not lossy truncation. Peers cannot read another member's private output
IDs; explicit sharing remains necessary.

Provider timeout is 300 seconds with retries=0. Domain commands default to 120
seconds and may explicitly request up to 600 for builds. The 2,400-second team
deadline refuses late actions; joining in-flight work/snapshots adds cleanup time.
Worker/evaluator containers have 4 CPUs, 16 GiB RAM and 512 PIDs; network disabled,
no host mounts, dropped capabilities and no-new-privileges. Library/build threads
are fixed at four regardless of the host CPU count; cached model loading uses
offline lookup. Evaluation time is
separate from agent budgets. Snapshot export refuses rather than silently clips
patches exceeding its independent 2,000,000-byte bound.
Across the pinned dataset's 229 feature/combined reference patches, the largest
is 39,585 bytes: the snapshot bound is 50.5 times that observed size. This is
sizing evidence, not permission to clip a larger agent patch.

## Measured Twenty-Pair Pilot

The 2026-10-30 fixed selection finished: 20/20 completed and graded, 15 passed
and 5 failed. After the first attempt, task-level concurrency was explicitly
authorized and the remaining 19 ran four at a time in separate worker containers.
The first attempt's derived-image grading mismatch was corrected by offline
regrading of the same frozen patches, not another paid agent attempt. Its failure
remains in the denominator and its original error/provenance remain available.
Analysis separates the original source condition (0/1) from the parallel batch
(15/19); the combined 15/20 is descriptive, not a uniform-version comparison.

Final server regression suite: 180 passed. All 20 traces passed integrity checks;
there were no member halts, context/output exhaustion or lossy truncation events.
Observed maxima were 170,774 prompt tokens, 13,004 reply tokens, 59/150 domain
calls per worker and 2,066.11/2,400 active seconds. All 535 peer messages were
delivered and consumed by run end, which does not prove timely or correct use.
All merges were identical-worker-patch integrations. The five remaining failures
are implementation/API behavior under official tests, not merge conflicts.
Their causal attribution still requires a requirement/message/decision audit.

Evidence: `outputs/cooperbench/team20-20261030-parallel-01/`; concise report and
deterministic condition/role analysis: `outputs/reports/team20-20261030-parallel-01/`.
The 19 new attempts took a 49m22s batch accounting window and an estimated
USD 1.562569; including the retained first attempt gives USD 1.612790. The observed
parallel-batch account delta was CNY 10.17, potentially including shared-key
activity. Overlapping per-run balance deltas must not be summed. These are pilot
observations, not a paid resampling campaign or a held-out efficacy claim.

## Contracts and Attribution

CooperBench states ordinary git merge, zero conflicts, both feature suites on the
same merged codebase, no external conflict fixer, and evaluation of frozen code
rather than reports or temporary simulations. This adaptation allows explicit
code sharing/integration and identical patches; no upstream PR service or shared
Git remote is provided. All members receive these facts; no Jinja-specific
solution or coordination algorithm is injected.

Generic leader responsibility, capacity and output handling belong to harness/.
Benchmark inputs, snapshots, provisioning and grading belong to the adapter.
Clarifying public rules is baseline correctness, not an RSI improvement.
Distinguish omission, delay, misuse, coordination and overhead from task ambiguity,
environment defects and resource failures. Message availability is not proof of
understanding or causal use. Later interventions must retain the same public contract.
