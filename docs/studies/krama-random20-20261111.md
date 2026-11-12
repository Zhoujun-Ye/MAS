# KramaBench Fresh Random20

## Second Authorized Run

After the final review and commit `642a6dd`, the user explicitly authorized a new
run of the same frozen twenty questions once per Single/Native/Structured condition:
sixty solver attempts, at most six one-call semantic judges and zero retries.
This reuses the diagnostic set; it is not an independent test or a replacement
selection from the first batch. Keep both batches and all incurred accounting.

The detached driver PID is `2124655`; it runs as its own session without a
controlling terminal or SSH/stdin dependency. Closing the local computer does not
stop it. Krama uses server-direct model/judge APIs and no local-Mac web tunnel.
A server reboot or process failure does not trigger an automatic restart/retry.

- Frozen source: `/home/zhoujunye/mas-stages/20261111-krama-random20-02`.
- Output: `/home/zhoujunye/mas/outputs/krama-random20-20261111-02`.
- Authorization, fresh native proofs and planning receipts:
  `/home/zhoujunye/mas-data/receipts/krama-random20-20261111-02/`.
- CPU8/thread4, sixteen solver slots, two grading slots, thinking disabled,
  temperature zero, manifest order and existing task deadlines remain unchanged.
- Balance admission retains a CNY120 estimate, 1.5 safety factor and CNY5 reserve;
  this is not a provider-enforced spending cap or per-condition invoice.

All sixty no-model task preflights and balance admission passed. The first
post-launch check observed sixteen running solvers and no controller failure.
This records startup only, not completion or answer correctness. Read subsequent
progress, host ledgers and eventual summary for outcomes. The launcher records the
exact six eligible semantic-judge pairs; the generic sixty-slot judge-enable switch
does not authorize sixty paid judge calls. No extra paid smoke was added.

## Current Review-Fix Launch

The subsequent November 11 request authorizes fixing the infrastructure review,
free server verification and then executing the same sixty slots. No experiment
was running when checked. Current verification is recorded in
[review fixes](infra-review-fixes-20261111.md): 921 server tests, both native
admission proofs, Fable/Haiku alias probes, nine synthetic workflows and three
503/no-retry probes passed. This is mechanics evidence, not measured accuracy.

Launch source target: `/home/zhoujunye/mas-stages/20261111-krama-random20-fixed-01`.
Admission proofs: `/home/zhoujunye/mas-data/receipts/review-fixes-20261111-01/native-proofs-02`.
Output remains `/home/zhoujunye/mas/outputs/krama-random20-20261111-01`.
The task manifest, organization prompts, sixteen solver slots, CPU8/thread4,
thinking-off/temperature-zero policy and maximum six semantic grades are unchanged.
The shared explicit tool surface, aliases, timeout outcome handling and deferred
offline evaluation are corrected as documented in the review record. Freeze fresh
source-bound task plans; never resume a paid plan across these changes.
No extra paid smoke or retry is authorized by this launch description.
The driver (PID `1744295`) has finished all sixty slots. The retained summary
records fifty `cli_exited`, three `native_condition_unverified` and seven
`timed_out` outcomes. Grading records fifty `graded`, three `invalid_submission`
and seven `incomplete_timeout` outcomes, with five semantic judge calls. No
controller failure or grading exception was recorded. These lifecycle counts are
not accuracy claims or proof of valid delegation. No solver or judge was retried.
The source remains frozen; later shutdown/compliance fixes are not retroactive.

## Preparation Scope (Historical)

The November 11 request is to prepare, clean, verify, commit and push a matched
Single / Native / Structured comparison. No paid solver or judge is launched
during preparation. The prepared matrix contains sixty solver slots: the same
twenty questions once per condition, zero retries and zero paid judges. Semantic
answers that need a judge remain pending, not automatically incorrect.

| Matrix Condition | Runtime | Lead Organization |
| --- | --- | --- |
| `claude-code-single-agent` | Strict Single | Unchanged Single prompt and native delegation denial |
| `native` | Ordinary native Subagents; Teams disabled | Structured opening paragraph plus mandatory delegation |
| `claude-code-subagents` | Ordinary native Subagents; Teams disabled | Exact frozen seven-point Structured prompt |

The approved Native text is in
[`native_subagents.py`](../../scripts/common/prompts/native_subagents.py). It
requires at least one subagent but adds no worker count cap, tool-call allowance,
briefing template, sequencing or completion strategy. The same native lifecycle
audit applies to Native and Structured. This is a minimal delegation-prompted
condition, not an unprompted CLI default. No new adapter or scheduler is added.

## Frozen Questions And Settings

[`krama-random20-manifest.json`](krama-random20-manifest.json) records the public
task IDs/fingerprints, full 104-task public population, method, Python version and
seed `6820760213620092556`. Selection is one shuffle of upstream order followed
by the first twenty items, without replacement or inspecting prior scores.
The sample selected before the third-condition correction is preserved exactly;
it is not rerolled to improve domain balance or results.

In order: `wildfire-hard-21`, `legal-easy-25`, `legal-easy-5`, `legal-hard-24`,
`legal-hard-7`, `legal-easy-13`, `wildfire-easy-3`, `environment-hard-19`,
`astronomy-easy-1`, `biomedical-hard-7`, `biomedical-hard-8`, `wildfire-easy-2`,
`biomedical-hard-3`, `wildfire-hard-10`, `legal-easy-4`, `legal-easy-11`,
`legal-hard-16`, `astronomy-easy-5`, `legal-easy-26`, `wildfire-hard-18`.

Four naturally overlap Validation20: `legal-easy-13`, `wildfire-easy-3`,
`astronomy-easy-1`, `biomedical-hard-8`. The original Validation20 IDs/hashes are
unchanged. This unstratified diagnostic sample has nine legal, five wildfire,
three biomedical, two astronomy and one environment task, with no archeology.
It is not a domain-balanced or independent final test, and no performance gain
can be inferred from preparation or a single matched run.

[`krama-random20-protocol.json`](krama-random20-protocol.json) freezes thinking off,
temperature zero and effort not applicable (`none`),
the three organization hashes, existing task/web limits, CPU8/thread4, resource
recording, sixteen solver slots in total and two offline grading slots. Each
solver has eight GiB memory. Model, native CLI pin and image are unchanged.
The inspected server had 128 logical CPUs, approximately 988 GiB available
memory, negligible load and no containers; runtime admission must recheck this
before execution. [DeepSeek's published Flash account limit](https://api-docs.deepseek.com/quick_start/rate_limit/)
was 2,500 concurrent requests when checked November 11, not a throughput promise.
Native worker fan-out remains external; CPU quota does not accelerate model waits.

## Infrastructure Fairness

Native and Structured use identical native arguments, tools, settings, hooks,
model/environment, image, inputs, CPU/thread/memory quotas and deadlines. Their
only intended solver-visible difference is the approved organization text.
Single keeps its explicit native delegation denial. All three retain the same
task/output rules, data and instrumentation. No hidden token cap, worker roster,
automatic semantic selection, polling guard or custom worker scheduler is added.

The shared CLI receipt now separates version preflight, native process lifetime,
process-group cleanup and result parsing. Legacy `elapsed_seconds` still includes
all these phases. Container shutdown is recorded separately. Generic model/tool
interval unions live in `analysis/timing.py`, independent of retired workspace
readers; overlap is not added twice or treated as measured pure network time.

One host-receipt reducer in `analysis/request_accounting.py` serves token and
cost reports. Only unique dispatch/terminal pairs with complete observed usage
contribute known subtotals. Missing, duplicate, rejected, partial or cancelled
calls keep full totals unknown, while valid completed requests are no longer
hidden by another call's missing usage. Native report analysis maps the condition
to its actual Subagents adapter, without changing its output/journal identity.
Native result usage and role cache statistics are not substituted for host billing.

Free three-condition workflow checks exercise the real CLI, mounted data, exact
prompts, native policy/delegation, submission and offline replay. A separate
upstream-503 injection observed exactly one request and no retry per condition;
it is a failure-path check, not an admission proof or a guarantee for every native
error type. Runtime admission proofs are collected separately. These checks use
synthetic provider responses and no real provider keys or paid calls.

This removes identified bookkeeping/configuration ambiguity, not model behavior.
The model can still spend tokens on reasoning, repeated investigation, background
workers or native cancellations. Such activity is part of the selected condition,
not something the adapter silently suppresses to improve cost/time. Partial
charges remain unknown. Real provider latency, concurrency effects, lifecycle
exceptions and external transport behavior still require measured paid evidence;
preparation cannot guarantee their absence or establish comparative efficacy.

## Server Planning

Current thinking-off verification source:
`/home/zhoujunye/mas-stages/20261111-krama-reproducibility-01`.
Its native proofs, synthetic workflows, CPU checks, sixty no-model task preflights
and nonexecuting matrix plan are recorded under
`/home/zhoujunye/mas-data/receipts/reproducibility-20261111-01/`.
Older max-profile preparation is superseded, not paid evidence. Cleanup details
are in [retention](../archive.md). The post-cleanup source needs fresh source-bound
plans before execution; do not reuse an older plan across source changes.
No paid output namespace had been created at that preparation checkpoint.

Planning only, from the source directory with the existing evaluation Python:

```bash
python -m scripts.studies.benchmark_matrix \
  --root /home/zhoujunye/mas-data \
  --output /home/zhoujunye/mas/outputs/krama-random20-20261111-01 \
  --proofs /home/zhoujunye/mas-data/receipts/reproducibility-20261111-01/native-proofs \
  --image mas/research-benchmarks:20261111-sqlite-v2 \
  --benchmarks kramabench \
  --conditions claude-code-single-agent native claude-code-subagents \
  --task-manifest docs/studies/krama-random20-manifest.json \
  --protocol-settings docs/studies/krama-random20-protocol.json \
  --tasks-per-benchmark 20 --concurrency 16 --judge-concurrency 2 \
  --cpus 8 --compute-threads 4 --record-resources --effort none \
  --authorized-attempts 60 --authorized-judges 0 --check-runtime
```

The manifest was generated with the existing `scripts.studies.freeze_manifest`
entry point, `--sample-size 20 --sample-seed 6820760213620092556` and that protocol.
Do not regenerate it based on results. Planning loads no credentials and makes
no paid calls. Actual execution additionally requires `--execute`, an explicit
cost estimate/reserve admission and run-specific authorization; a plan is not a
provider-enforced spending cap or permission to retry.

## Authorized Paid Run

After preparation, the user explicitly authorized deployment and one execution
of all sixty selected task/condition slots: sixteen solver processes in total,
CPU8/thread4, the same model/image/prompts, zero retries. Two grading
slots may overlap solving. Only `legal-easy-25` and `wildfire-hard-18` have the
pinned `string_approximate` type, so at most six one-call semantic grades are
authorized. Other answers retain their deterministic scoring; failed/unknown
judges and solvers are not repeated. No best-of selection or replacement is allowed.

The generic driver's conservative `--authorized-judges 60` switch enables grading
for the sixty slots; its type/status guard and the pinned semantic-judge validator
admit only those six eligible task/condition pairs. The exact allowed pairs are
recorded separately in the run receipt, not an authorization for sixty judge calls.
Balance admission uses a CNY120 remaining-cost estimate, 1.5 safety factor and
CNY5 reserve. This is neither a hard invoice cap nor attributable accounting.

The user subsequently corrected effort to high, then explicitly selected thinking
off/temperature zero for greater reproducibility and asked to review configuration
before starting. Thus high is not an effective reasoning setting for this profile.
The earlier max preparation/proofs are not admission evidence for the revised run.
No paid dispatch happened before these corrections. Question IDs, fingerprints
and the sampling seed are unchanged; only the explicit inference/settings profile
is revised. See [reproducibility](../reproducibility.md).

The prematurely named `20261111-krama-random20-paid-01` and the earlier
`20261111-krama-random20-ready-01` were unpaid max-profile source stages, not
paid solver attempts. Both were removed by the release cleanup after verification.
Post-cleanup source verification lives in
`/home/zhoujunye/mas-stages/20261111-release-cleanup-01`, with tests, nine synthetic
workflows and sixty no-model task preflights under
`/home/zhoujunye/mas-data/receipts/maintenance-20261111-release-cleanup/`.
Freeze a new paid source after configuration review; do not mutate any source
once its paid work starts.
Output: `/home/zhoujunye/mas/outputs/krama-random20-20261111-01`.
Future deployment uses source-only sync and an explicit reviewed retired-file
list, never touching frozen paid stages or runtime resources.
The paid source remains frozen while analysis is written outside the raw run.

## Cleanup Boundaries

Remove superseded unpaid two-condition preparation, redundant generated report
copies and regenerable project caches only after checking current replacements.
Keep raw paid runs, failures, accounting, frozen paid sources, current diagnostic
receipts, datasets, environments, credentials, required images and the installed
private tunnel. No result backup, global Docker pruning or other-project cleanup.
See [retention](../archive.md) for exact evidence boundaries and cleanup receipts.
