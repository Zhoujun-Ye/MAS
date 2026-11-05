# Solver Prompts

Shared runner prompt modules live in `scripts/common/prompts/`, not a standalone
top-level package.

| File | Responsibility | Active |
| --- | --- | --- |
| `structured_subagents.py` | Frozen seven-point Subagents lead prompt | Subagents default |
| `native_subagents.py` | User-supplied four-point alternative lead prompt | No |
| `single_agent.py` | Strict Single condition text | Single default |
| `conditions.py` | Backend selection and explicit raw-text study overrides | Yes |
| `limits.py` | Identical wall-clock and web-limit wording for both conditions | Yes |

Both Subagents prompt names refer to ordinary native Claude Code subagents, not
Agent Teams or different runtimes. Moving the text here does not change the
default, permissions, delegation policy or benchmark protocol. The Single text
does not replace native permission enforcement in `harness/`.

`scripts/common/runtime.py` re-exports the existing prompt functions so runner
imports remain compatible. `--organization-prompt` still reads a plain text file;
do not pass one of these Python modules as its input.

## Ownership Boundaries

- Benchmark task/output rules stay with the runners:
  `scripts/kramabench/cli_runtime.py:INSTRUCTIONS` and
  `scripts/common/run.py:instructions` (DataClaw/HDR).
- Evaluation prompts stay with `benchmarks/kramabench/semantic_judge.py` and
  `scripts/common/score.py`; they are not solver instructions.
- Probe fixture prompts stay in `scripts/probes/` beside the checks they serve.
- Frozen run prompts and historical evidence stay in their original artifacts.

Lead-only organization text must not be copied into worker-visible rule files.
Run limits remain shared task rules, not a Subagents-only policy.
