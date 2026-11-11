# Solver Prompts

Shared runner prompt modules live in `scripts/common/prompts/`, not a standalone
top-level package.

| File | Responsibility | Active |
| --- | --- | --- |
| `structured_subagents.py` | Frozen seven-point Subagents lead prompt | Subagents default |
| `native_subagents.py` | Approved opening paragraph plus mandatory delegation | Opt-in Krama Native study |
| `single_agent.py` | Strict Single condition text | Single default |
| `conditions.py` | Backend selection and explicit raw-text study overrides | Yes |
| `limits.py` | Identical wall-clock and web-limit wording for every condition | Yes |

Structured refers to ordinary native Claude Code subagents, not
Agent Teams. FULL/OBS and their prompt-only study prompts are retired.
Moving the text here does not change the
default, permissions, delegation policy or benchmark protocol. The Single text
does not replace native permission enforcement in `harness/`.

Runners import prompt functions directly from this package; the harness does not
depend on experiment prompts. `--organization-prompt` still reads a plain text file;
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

Krama's `--subagents-prompt native` selects the minimal prompt without a raw-file
override. The matrix exposes it as `--conditions ... native ...`, retaining
independent task/condition outputs and grades while using the existing Subagents
runtime/proof. Native and Structured both require actual native delegation;
neither condition is an unprompted CLI default. Structured remains the default.
