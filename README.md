# MAS

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
request. Retained experiments are the CPU8 paired run and its two authorized
four-task engineering comparisons; see [retention](docs/archive.md).

## Current Results

The retained twenty-question 8-CPU KramaBench Structured/FULL comparison uses
20 fixed questions per condition, eight concurrent tasks total, Claude Code
2.1.286 and DeepSeek Flash at high effort. The three authorized upstream-503
recoveries replace the matching primary rows; original failures and all incurred
cost evidence remain part of this batch.

| Metric | Structured | FULL (decision-v3 run) |
| --- | ---: | ---: |
| Mean score | 0.7453846154 | 0.7453846154 |
| Full-score questions | 14/20 | 14/20 |
| Mean effective CLI minutes | 7.3662 | 7.7321 |
| Mean CPU cores | 0.4901 | 0.5357 |
| Measured quota throttled seconds | 0 | 0 |

Scores match on every question. These reused validation questions do not establish
held-out performance or causal superiority. Earlier experiments and their
result-only compatibility paths were removed at the user's request on 2026-11-07.
See [current evidence](docs/current-results.md) for scope and cost limitations.

The repaired decision-v4 FULL was subsequently tested twice on the same four
questions. Mean FULL time fell from 232.87 to 173.55 seconds with identical scores;
Structured varied from 162.30 to 150.79 seconds. This small stochastic sample is
not a full-benchmark speed guarantee. See [paid speed check](docs/studies/infra-smoke4-speed-check.md),
[active infra](docs/studies/evidence-infra.md) and [full-scale operation](docs/studies/fullscale-infra.md).

## Layout

- `harness/`: native CLI adapters and our opt-in MAS harness; see [ownership](harness/README.md).
- `harness/evidence_mas/`: observation sharing, execution-backed decisions and hook/MCP interfaces.
- `scripts/common/prompts/`: solver condition text, prompt selection and shared run-limit wording.
- `benchmarks/{kramabench,dataclawbench,hybriddeepresearch}/`: tasks and independent evaluation.
- `scripts/<benchmark>/{catalog,run,score}.py`: benchmark entry points.
- `common/`: domain-independent persistence, fingerprints and durable phase claims.
- `harness/runtime_support/`: containers, native CLI environment, tools, credential transport and provenance.
- `scripts/common/`: shared benchmark experiment workflows, not reusable runtime implementations.
- `scripts/server/`: source deployment, provisioning and server operations.
- `scripts/probes/`: isolated native CLI and credential-containment checks.
- `scripts/studies/`: frozen manifests, bounded matrix execution, journal recovery and reporting.
- `analysis/`: read-only active native evidence and current-run analysis.
- `tests/`: offline regressions; run on the server, not locally.
- `docs/`: operational contracts; `docs/studies/` holds study protocols and reports.

Directory ownership and dependency rules: [Repository Layout](docs/repository-layout.md).

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
