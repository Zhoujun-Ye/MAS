# Shared Evidence Workspace

Opt-in collaboration support for ordinary native Claude Code subagents. Current
FULL uses decision-v3; OBS and FULL share the exact existing Native (N) prompt.
The frozen Structured baseline is separate and unchanged. Current protocol,
intermediate result contracts and one-time shadow grading are documented in
[Intermediate Results](../../docs/studies/intermediate-full.md).

## Components

| Module | Responsibility |
| --- | --- |
| `store.py` | Run-bound SQLite observations, immutable payloads and historical ledger records |
| `hook.py` | Native tool-event capture and submission checks |
| `mcp.py`, `config.py`, `entrypoint.py` | Role-specific tools, explicit configuration and isolated Python entry |
| `cli.py`, `integration.py` | Native launch, source-bound proofs, mounts and post-run audits |
| `measurements.py`, `decision.py` | Typed intermediate results, anonymous candidates and consistency checks |
| `audit.py` | Read-only successful-method/role checks, not scheduling or submission |

FULL is a superset of OBS observation access plus decision tools. Workers cannot
select or check the final decision through their configured MCP tool interface.
Missing/degraded capture and inconsistent submissions remain incomplete; the
harness never chooses an answer, repairs a submission or retries a model.
Consistency is not correctness.

## Integration

Existing `scripts/<benchmark>/run.py` entrypoints accept `--evidence-mode
observations|full` with `--backend claude-code-subagents`. Omitting evidence mode
retains the baseline adapter and prompt. The matrix requires
`--backends claude-code-subagents --evidence-modes observations full`.
`scripts/studies/run_validation20_evidence.py` composes these workflows for the
frozen validation set; planning is the default. Paid execution requires fresh
run-specific authorization, matching proofs and explicit `--execute`.

Run server tests with the existing evaluation Python. The native fake-provider
probe is `python -m scripts.probes.evidence_mas --output FRESH_DIRECTORY`;
without `--execute` it only plans. Fake-provider probes verify wiring, not actual
provider behavior, reasoning quality or benchmark gains.

## Boundaries

The historical ledger API remains for retained evidence and fixtures, not as the
active FULL interface. Its superseded designs and receipts are indexed in
[Retention](../../docs/archive.md). Do not restore old Structured composition or
old submission semantics from historical descriptions.

Only solver-visible inputs belong in the store. Gold, credentials and private
evaluation logs remain host-side. Reads prove access, not comprehension. Capture
cannot recover arbitrary Bash dependencies. Actor/role settings and same-UID
writable stores are not authentication or a security boundary; hashes do not
make storage tamper-proof. Native scheduling and model calls remain external.
