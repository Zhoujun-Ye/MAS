# Leader-Subagent Harness

A benchmark-independent leader solves tasks directly or delegates bounded work to
fixed, capability-limited subagent templates. Children receive selected task context
and may use permitted tools on shared workspaces. Independent transcripts are not
strict information isolation or an OS sandbox.

## Runtime

- `harness/subagents.py`: bounded parallel delegation, in-session resume, tool
  grants, shared session budgets and infrastructure-impact reporting.
- `harness/single_agent.py`: single-context mode using the same loop, all approved
  domain tools and full own history, without delegation.
- `harness/agent.py`: append-only context, schema validation and tool dispatch.
- `harness/llm.py`, `trace.py`, `accounting.py`, `runner.py`: retained infrastructure.
- `harness/execution.py`: optional container tools; no automatic provisioning.
- `harness/workspace_audit.py`: trace-only file/hash snapshots for Git workspaces.
- `analysis/`: cache accounting, general statistics and historical run readers;
  `scripts/analyze.py` expects old scheduler-based manifests, not new sessions.

See [architecture](docs/leader-subagent.md) and [historical evidence](docs/archive.md).

## Agent Team Design Target

The next design is a [Leader-led Agent Team](docs/agent-team-design.md): the Leader
assigns tasks and maintains team state; persistent Workers execute and communicate
directly; key progress, risks and results reach the Leader; communication is retained
for analysis. The proposal specifies event-driven scheduling, task authority,
message delivery and a final draining barrier. It is not implemented: the runtime
and commands below still use foreground delegation, without peer messaging.

## KramaBench

[KramaBench adapter](docs/kramabench.md) uses a pinned public task catalog and
eight fixed capability templates for discovery, pipeline implementation, data
preparation, calculation, result review, requirements, auditing and reproduction.
The Leader selects templates at runtime; questions and host paths stay out of stable
role prefixes. Generic inspection/provenance lives in `harness/`, benchmark-specific
task and response handling in `benchmarks/kramabench/`. Native grading is deliberately
separate because upstream metrics can invoke paid judges.

Use `mode="single"` or `mode="mas"` for matched task/model/tool/session-budget
comparisons. The no-paid paired smoke is `scripts/kramabench/offline.py --mode both
--output outputs/kramabench-single-mas-NEW` (server only). It uses separate fixture
workspaces; it is not an official evaluation or evidence of MAS superiority.

## Verification

Run only on the project server, after inspecting processes:

```sh
scripts/server/sync.sh
scripts/server/remote.sh '.venv/bin/python -m pytest -q'
scripts/server/remote.sh '.venv/bin/python scripts/subagent_demo.py --output outputs/subagent-demo-NEW'
```

The demo uses a scripted model and in-memory evidence, with no paid calls. It is
not a benchmark. Real adapters must bind authorized tools, record frozen model,
prompt, source and budget settings, and provide independent outcome evaluation.
A run-specific KramaBench pilot is retained in the adapter documentation. No
further paid runs are authorized; current verification uses offline fixtures.
Historical scores do not transfer.
