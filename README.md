# MAS Information

Benchmark adapters for the externally installed Claude Code CLI.
No upstream agent runtime is vendored or imported as an SDK.

## Active Conditions

| CLI | Single | Subagents |
| --- | --- | --- |
| Claude Code 2.1.286 | Native delegation disabled and audited | Native Agent; Teams disabled |

The Subagents default is current orchestrator-worker lead prompt, frozen by the user on
2026-11-04. Prompt organization is documented in [scripts/common/prompts/](scripts/common/prompts/README.md).
This is a prompted native baseline, not an unmodified default CLI policy. It adds
no specialist roster or cost-reduction method. Both conditions receive the same task
rules, including the run's wall-clock and web request limits. Structural worker
completion does not prove substantive contribution; that remains a separate
evidence-review question.

Deep Agents, Claude Code Agent Teams and Codex adapters are retired. Do not restore
their active adapters or launch choices. Codex results were removed at the user's
request. Earlier paid results were deleted on 2026-11-04; the subsequently
authorized current run and its derived regrading reports are retained.

## Current Results

All three conditions completed the same 60 frozen Validation20 questions:
20 per benchmark, one assigned attempt each. Claude Code 2.1.286, DeepSeek Flash,
high effort, solver concurrency 6 and grading concurrency 2. Structured is still
the default prompt; Native is a separately authorized prompt study, not Agent Teams.

### DataClaw

| Condition | Mean Score | Full Score | Mean Min/Task | Known Cost Subtotal (USD) | Cost Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single | 0.7750 | 15/20 | 4.27 | 0.604693 | 20/20 |
| Structured Subagents | 0.9000 | 18/20 | 4.86 | 1.076522 | 20/20 |
| Native Subagents | 0.8750 | 17/20 | 5.46 | 1.226527 | 20/20 |

### HDR

| Condition | Mean Score | Full Score | Mean Min/Task | Known Cost Subtotal (USD) | Cost Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single | 0.3500 | 7/20 | 7.87 | 0.939461 | 19/20 |
| Structured Subagents | 0.3500 | 7/20 | 12.56 | 2.187651 | 18/20 |
| Native Subagents | 0.3500 | 7/20 | 13.09 | 2.474321 | 19/20 |

### KramaBench

| Condition | Mean Score | Full Score | Mean Min/Task | Known Cost Subtotal (USD) | Cost Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single | 0.7454 | 14/20 | 3.93 | 0.477129 | 20/20 |
| Structured Subagents | 0.7954 | 15/20 | 6.46 | 1.242427 | 19/20 |
| Native Subagents | 0.7287 | 13/20 | 8.30 | 1.826549 | 20/20 |

Cost coverage is the number of tasks with complete cost records. Below 20/20,
the benchmark total cost is unknown; the displayed subtotal is not the total.

### Overall

| Condition | Full-Score Tasks | Mean Min/Task | Known Cost Subtotal (USD) | Cost Coverage | Complete Total Cost |
| --- | ---: | ---: | ---: | ---: | --- |
| Single | 36/60 | 5.36 | 2.021283 | 59/60 | Unknown |
| Structured Subagents | 40/60 | 7.96 | 4.506601 | 57/60 | Unknown |
| Native Subagents | 37/60 | 8.95 | 5.527397 | 59/60 | Unknown |

- Scores retain the two HDR artifact-only regrades and timeout-zero policy.
  Different benchmark score scales are not pooled into an overall mean.
- Time is mean CLI elapsed time per assigned attempt, not batch wall-clock time;
  all 180 attempts have timing records. Timeouts remain in the denominator.
- Costs use the same off-peak token-price scenario plus successful-HTTP web and
  judge estimates, not invoices. A subtotal includes only tasks with complete
  model, web and judge cost records; other tasks are unknown, never zero.
  Differently covered subtotals are not directly comparable complete totals.
- All three conditions now use the same request-ID/completeness accounting audit.
  This corrects previously reported complete totals without changing any scores,
  solver attempts or original reports. The two separate web diagnostic calls are
  outside these task totals. Actual attributable total charges remain unknown.
- This reused development set and one attempt per condition do not establish
  general superiority or prompt causality. Current code includes previously
  documented evaluation fixes after the original run; see the Native run record.

Sources: [Single/Structured accounting-audited report](outputs/validation20-baseline-accounting-audited-20261105-01/REPORT.md),
[Native accounting-audited report](outputs/validation20-native-20261105-01-report-audited-01/REPORT.md),
and [Native run/diagnostics](docs/studies/validation20-native.md).
Original reports and private raw evidence remain unchanged. Future experiments
require fresh run-specific authorization.

See [current result status](docs/current-results.md) and
[the fixed validation set](docs/studies/validation20.md).

## Layout

- `harness/`: native arguments, hooks, version checks and process transport.
- `scripts/common/prompts/`: solver condition text, prompt selection and shared run-limit wording.
- `benchmarks/{kramabench,dataclawbench,hybriddeepresearch}/`: tasks and independent evaluation.
- `scripts/<benchmark>/{catalog,run,score}.py`: benchmark entry points.
- `scripts/common/`: shared runners, containers, credential gateway, proof admission and tools.
- `scripts/server/`: source deployment, provisioning and explicit batch entry points.
- `scripts/probes/`: isolated native CLI and credential-containment checks.
- `scripts/studies/`: study-specific execution and historical result maintenance, not baseline defaults.
- `analysis/`: read-only native and historical evidence readers.
- `tests/`: offline regressions; run on the server, not locally.
- `docs/`: operational contracts; `docs/studies/` holds study protocols and reports.

## Safety And Execution

Real credentials remain in a mode-0600 host `.env`, outside solver mounts.
Live solver containers have no external network. A Unix-socket gateway provides
fixed native model and search routes, without retries or model orchestration.
Authoritative request accounting lives outside the solver workspace. A run token
does not prove which same-UID process issued a request; native and gateway evidence
must not be presented as tamper-proof attribution.

Default solver limits are DataClaw 1200 seconds, HDR 1800 seconds and Krama 3600
seconds. DataClaw follows its pinned upstream configuration; the other two are
provisional engineering defaults. All conditions within one benchmark share its
limit. See [timeout policy](docs/timeout-policy.md).

Planning is the default. Paid solvers and judges require run-specific authorization
and `--execute`; no automatic retries or replacement attempts. Use a fresh output
directory and current runtime-bound offline proof. Keep new failures unless the
user explicitly authorizes their deletion. Independent conditions use bounded
parallelism with separate outputs; record concurrency in the frozen plan.

Use `scripts/server/sync.sh` for source only, never credentials, datasets,
environments, outputs or `--delete`. Do not touch the unrelated Agent-Team project.

## Documentation

- [Claude CLI contracts](docs/cli-adapters.md)
- [Benchmark structure](docs/benchmark-adaptation.md)
- [KramaBench](docs/kramabench.md) and [DataClaw/HDR](docs/research-benchmarks.md)
- [Server preparation](docs/server-preparation.md)
- [Current evidence retention](docs/archive.md)
