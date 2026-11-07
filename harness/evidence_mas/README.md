# Shared Evidence Workspace

Opt-in observation sharing and execution-backed decision tools for ordinary
native Claude Code subagents. Active FULL uses decision-v4; OBS has the same
bounded cross-context observation delivery but no decision mutation tools.
The exact frozen Structured baseline is unchanged.

- `sharing.py`: bounded incremental hook context and emission receipts, no polling.
- `hook.py`: raw observation/lifecycle capture, worker submission interface guard.
- `decision.py`, `measurements.py`: explicit executed candidates/intermediates,
  evidence access, task-grounded selection and submission consistency.
- `store.py`: run-bound SQLite observations and immutable hashed payloads.
- `mcp.py`, `config.py`, `cli.py`, `integration.py`: native tool wiring,
  source-bound launch configuration and descriptive audits.

Historical manual ledger, source/outcome registration and retired runtime
readers were removed. Read-only decision-v3 parsing remains solely for the one
retained CPU8 experiment. Old protocols cannot launch or mutate a new store.

See [active infra](../../docs/studies/evidence-infra.md) and
[decision contracts](../../docs/studies/intermediate-full.md).
Native scheduling stays in Claude Code; no custom scheduler, automatic semantic
choice, final submission or model retry exists here.

Only solver-visible inputs enter stores. Keys and private evaluation data stay
host-side; containers have no external network. A hook emission is not an
acknowledgement, a read is not comprehension, and consistency is not correctness.
Same-UID stores and configured roles are not authentication or a security boundary.
