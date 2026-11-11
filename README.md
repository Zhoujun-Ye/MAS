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
evidence-review question. KramaBench additionally supports the explicitly selected
`native` study condition: the approved opening paragraph and a requirement to
deploy at least one subagent, without Structured's seven detailed constraints.
It reuses the same adapter and audit; it is not an unprompted CLI default.

FULL, OBS and prompt-only ablations were retired on 2026-11-10. Active launch
defaults remain Single and Structured; the opt-in Native study does not restore
any retired condition. Historical results below are not launch choices.
Deep Agents, Claude Code Agent Teams and Codex adapters are retired. Do not restore
their active adapters or launch choices. Codex results were removed at the user's
request. Paid comparisons and their frozen source/accounting are retained under
the explicit [retention policy](docs/archive.md).

## Retained Results
The FDABench CPU8/thread4 rerun repeated the four fixed questions in Single and
Structured, eight explicitly authorized attempts, no retries or paid judges.
Both raw scores remain 4/4, but two missing SessionEnd records leave only 6/8
native audits passing. Against the preceding 2-CPU/thread1 diagnostic, mean CLI
time fell 16.5% for Single and rose 41.7% for Structured. Common-rate estimated
API cost fell 21.2% for Single and was essentially unchanged for Structured.
This is not an overall speedup or an isolated causal CPU experiment. See
[the matched comparison](docs/studies/fdabench-cpu8-rerun-20261110.md) and
[the original diagnostic](docs/studies/fdabench-smoke4-20261110.md).

Current defaults are 8 CPUs and 4 numerical threads across all four benchmarks
and all supported conditions. The shared image includes native PDF rendering. These
repairs have free runtime verification and the bounded paid rerun above. The
original paid diagnostic remains unchanged, including its actual 2-CPU profile.

Earlier paid Structured/FULL results remain historical evidence in
[current results](docs/current-results.md) and [retention](docs/archive.md).
FULL/OBS and their ablations are no longer active launch choices.

## Layout

- `harness/`: native CLI adapters and shared execution infra; see [ownership](harness/README.md).
- `scripts/common/prompts/`: solver condition text, prompt selection and shared run-limit wording.
- `benchmarks/{kramabench,dataclawbench,hybriddeepresearch,fdabench}/`: tasks and independent evaluation.
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

Current DeepSeek inference defaults are thinking disabled and temperature zero;
reasoning effort is inapplicable, expressed as `--effort none`. Main and worker
requests are verified before forwarding, not silently rewritten. Explicit high/max
study overrides enable thinking; max is never the default. Configuration ownership,
CPU verification and remaining nondeterminism are in [Reproducibility](docs/reproducibility.md).

Real credentials remain in a mode-0600 host `.env`, outside solver mounts.
Live solver containers have no external network. A Unix-socket gateway provides
fixed native model and search routes, without retries or model orchestration.
Authoritative request accounting lives outside the solver workspace. A run token
does not prove which same-UID process issued a request; native and gateway evidence
must not be presented as tamper-proof attribution.

Default solver limits are DataClaw 1200 seconds, HDR/FDABench 1800 seconds and Krama 3600
seconds. DataClaw follows its pinned upstream configuration; the others are
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

- [Prepared Single/Native/Structured random20 comparison](docs/studies/krama-random20-20261111.md)
- [Claude CLI contracts](docs/cli-adapters.md)
- [Benchmark structure](docs/benchmark-adaptation.md)
- [KramaBench](docs/kramabench.md) and [DataClaw/HDR](docs/research-benchmarks.md)
- [FDABench local, publicly scoreable scope](docs/fdabench.md)
- [Server preparation](docs/server-preparation.md)
- [Current evidence retention](docs/archive.md)
