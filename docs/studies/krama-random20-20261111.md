# KramaBench Fresh Random20

## Preparation Scope

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

[`krama-random20-protocol.json`](krama-random20-protocol.json) freezes max effort,
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

Frozen preparation source:
`/home/zhoujunye/mas-stages/20261111-krama-random20-ready-01`.
Preparation receipts, synthetic workflows, sixty task/container preflights and
the nonexecuting matrix plan:
`/home/zhoujunye/mas-data/receipts/krama-random20-preparation-20261111-01/`.
No paid output namespace is created. A future paid run must use a fresh namespace,
current runtime proofs and explicit authorization, not a stale two-condition plan.

Planning only, from the source directory with the existing evaluation Python:

```bash
python -m scripts.studies.benchmark_matrix \
  --root /home/zhoujunye/mas-data \
  --output /home/zhoujunye/mas/outputs/krama-random20-20261111-01 \
  --proofs /home/zhoujunye/mas-data/receipts/krama-random20-preparation-20261111-01/native-proofs-final \
  --image mas/research-benchmarks:20261111-sqlite-v2 \
  --benchmarks kramabench \
  --conditions claude-code-single-agent native claude-code-subagents \
  --task-manifest docs/studies/krama-random20-manifest.json \
  --protocol-settings docs/studies/krama-random20-protocol.json \
  --tasks-per-benchmark 20 --concurrency 16 --judge-concurrency 2 \
  --cpus 8 --compute-threads 4 --record-resources --effort max \
  --authorized-attempts 60 --authorized-judges 0 --check-runtime
```

The manifest was generated with the existing `scripts.studies.freeze_manifest`
entry point, `--sample-size 20 --sample-seed 6820760213620092556` and that protocol.
Do not regenerate it based on results. Planning loads no credentials and makes
no paid calls. Actual execution additionally requires `--execute`, an explicit
cost estimate/reserve admission and run-specific authorization; a plan is not a
provider-enforced spending cap or permission to retry.

## Cleanup Boundaries

Remove superseded unpaid two-condition preparation, redundant generated report
copies and regenerable project caches only after checking current replacements.
Keep raw paid runs, failures, accounting, frozen paid sources, current diagnostic
receipts, datasets, environments, credentials, required images and the installed
private tunnel. No result backup, global Docker pruning or other-project cleanup.
See [retention](../archive.md) for exact evidence boundaries and cleanup receipts.
