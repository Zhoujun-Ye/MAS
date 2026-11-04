# MAS Information

Benchmark adapters for the externally installed Claude Code CLI.
No upstream agent runtime is vendored or imported as an SDK.

## Active Conditions

| CLI | Single | Subagents |
| --- | --- | --- |
| Claude Code 2.1.286 | Native delegation disabled and audited | Native Agent; Teams disabled |

The user-selected Subagents prompt asks for an orchestrator-worker organization.
This is a prompted native baseline, not an unmodified default CLI policy. It adds
no specialist roster or cost-reduction method. Structural worker completion does not prove substantive
contribution; that remains a separate evidence-review question.

Deep Agents, Claude Code Agent Teams and Codex adapters are retired. Do not restore
their active adapters or launch choices. Codex results were removed at the user's
request. Only the current all-high Claude batch is retained; older result batches
were deleted explicitly. The retained study remains an engineering pilot.

## Current Results

The sole retained batch is `claude-all-high-01-21a0cdb`: six tasks each for Single
and MAS, all solver requests at `high`, solver concurrency 12, no retries.
Single scored fully on 4/6 tasks; MAS on 6/6. Total estimated costs were USD 0.11310
and USD 0.23288 respectively; the shared-account balance decreased by CNY 2.07.
These are single-attempt pilot observations, not a general superiority claim.

See [the current results report](docs/current-results.md) for per-task scores,
timing, cost components, role accounting, evidence paths and limitations.

## Layout

- `harness/`: native arguments, hooks, version checks and process transport.
- `benchmarks/{kramabench,dataclawbench,hybriddeepresearch}/`: tasks and independent evaluation.
- `scripts/<benchmark>/{catalog,run,score}.py`: benchmark entry points.
- `scripts/common/`: containers, credential gateway, prompts, proof admission and tools.
- `scripts/server/`: source deployment, provisioning and explicit batch entry points.
- `analysis/`: read-only native and historical evidence readers.
- `tests/`: offline regressions; run on the server, not locally.

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
- [Historical cleanup and source retention](docs/archive.md)
