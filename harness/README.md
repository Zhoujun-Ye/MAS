# Harness Ownership

The harness is our reusable execution and collaboration layer built on the
external Claude Code runtime. It does not replace native model loops, context
management or scheduling. Agent Teams and retired adapters remain retired.

| Path | Ownership |
| --- | --- |
| `claude_code_single_agent/`, `claude_code_subagents/` | Native baseline adapters |
| `_cli.py`, `_claude_cli.py`, `_claude_hooks.py` | Shared CLI lifetime and native observation/policy |
| `evidence_mas/` | Our opt-in MAS harness: observations, analytical decisions, evidence and dependency tracking |
| `runtime_support/` | Containers, native CLI environment, provenance, SQL/web tools, credential gateway/bridge and runtime proof validation |

Outside this package:

- `benchmarks/`: task data, reference protection and evaluation contracts.
- `scripts/<benchmark>/`: catalog/run/score workflows and benchmark-specific replay.
- `scripts/common/run.py`, `score.py`, `grading.py`: benchmark workflow composition.
- `common/`: domain-independent JSON persistence and fingerprints.
- `benchmarks/policy.py`: benchmark-specific timeout defaults and their sources.
- `scripts/common/prompts/`: unchanged frozen baseline prompts and task limits.
- `scripts/server/`, `scripts/probes/`: operations and explicit probe entrypoints.
- `scripts/studies/`: experiment drivers, not reusable MAS components.
- `analysis/`: read-only run analysis, not runtime decisions.

The 2026-11-05 relocation moves reusable tool/transport/proof implementations out
of `scripts/common/`. Imports and container source mount paths use their new
owners; container-facing filenames and tool behavior are unchanged. No forwarding
copies are retained at old source paths. Historical frozen source stages remain
untouched. Server validation uses a fresh stage to detect stale-path imports.

`runtime_support/runtime.py` owns container lifecycle, CLI environment and run
provenance. Experiment prompts are imported directly by workflows, never by the
harness. Moving code does not change baseline prompts or runtime settings.
