# MAS

Run data-analysis benchmarks through the externally installed Claude Code CLI.
The repository owns task adaptation, isolated execution and evaluation, not the
agent runtime or its scheduling.

## Conditions

| Condition | Runtime | Lead Prompt |
| --- | --- | --- |
| Single | Native delegation removed, denied and audited | Single baseline |
| Structured | Ordinary native subagents; Teams disabled | Frozen orchestrator-worker prompt |
| Native | Same Subagents adapter and audit; opt-in for KramaBench | Structured opening plus mandatory delegation |

Single and Structured remain the defaults. Native must be selected explicitly;
it is minimally prompted delegation, not untouched CLI behavior. The exact
[prompts](scripts/common/prompts/README.md) and shared task rules are unchanged.
Deep Agents, Agent Teams, Codex, FULL and OBS are retired, not launch options.

## Current Configuration

| Setting | Default |
| --- | --- |
| CLI | Claude Code 2.1.286; automatic updates disabled |
| Model | DeepSeek Flash, native context selector `deepseek-flash[1m]` |
| Sampling | Thinking disabled, temperature 1.0, effort not applicable (`--effort none`) |
| Hooks | Native observations and strict-Single permissions only; no loop detector |
| Per solver | 8 CPUs, 4 numerical threads, 8 GiB memory |
| Retries | 0; no automatic replacement attempts |
| Task limits | DataClaw 1200s; HDR/FDABench 1800s; Krama 3600s |

The [historical Krama random20 study](docs/studies/krama-random20-20261111.md)
retains its frozen T=0 configuration, twenty questions across three conditions,
concurrency sixteen and CPU8/thread4. It is not rewritten to match the current
T=1.0 default. The frozen Validation20 set is separate and unchanged; new paid
dispatch requires run-specific authorization.

The host gateway rejects thinking/temperature/effort drift before provider
dispatch; it does not rewrite requests. Inputs, source, CLI/image identity and
effective settings are frozen. See [reproducibility](docs/reproducibility.md)
for verification and remaining nondeterminism, and [timeout policy](docs/timeout-policy.md)
for the benchmark-specific limits.

## Workflow And Safety

Prepare the existing server environment and inputs using
[server preparation](docs/server-preparation.md), then use the benchmark's
`catalog`, `run` and `score` modules. Runners plan by default. Execution needs
`--execute`, current runtime-bound offline proof and run-specific paid authorization.
Use fresh, isolated outputs and record concurrency; preserve failed attempts and
unknown accounting rather than selecting a better retry.

Credentials stay in a mode-0600 host `.env`, outside solver mounts. Solver
containers use `network=none` and an ephemeral Unix-socket gateway token.
Model/search/judge APIs are server-direct; solver web GETs use the private
[Clash tunnel](docs/studies/web-infra.md). Never touch the unrelated Agent-Team
project. Tests run on the server with fake providers, not paid APIs.

## Layout

- `harness/`: native adapters, container/runtime support, tools and credential transport.
- `benchmarks/`: tasks and independent evaluation for Krama, DataClaw, HDR and FDABench.
- `scripts/`: benchmark workflows, frozen prompts, studies, probes and server operations.
- `common/`: persistence, fingerprints and durable claims.
- `analysis/`: read-only native, host-accounting and historical evidence analysis.
- `tests/`: offline behavior, safety and ownership regressions.
- `docs/`: current contracts and retained study reports.
- `outputs/`: retained evidence/reports only; never active source or test fixtures.

See [ownership](docs/repository-layout.md), [CLI contracts](docs/cli-adapters.md),
[benchmark adaptation](docs/benchmark-adaptation.md) and [script entrypoints](scripts/README.md).
For benchmark details: [Krama](docs/kramabench.md), [DataClaw/HDR](docs/research-benchmarks.md),
[FDABench](docs/fdabench.md).

## Evidence

[Current results](docs/current-results.md) separates measured outcomes from
free infrastructure checks and historical conditions. [Study index](docs/studies/README.md)
links the protocols and reports; [retention](docs/archive.md) defines protected
paid traces, frozen sources and disposable material. Cleanup never rewrites
historical settings or establishes a benchmark improvement.
