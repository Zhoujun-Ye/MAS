# Leader-Led Agent Team Harness

Benchmark-independent asynchronous teams with centralized task authority and direct
Worker-to-Worker messages. The Leader selects fixed capability templates, assigns
local work and receives handoffs; Workers execute and communicate directly.
Independent transcripts manage context; shared tools and files are not information
isolation or a security sandbox.

## Runtime

- `harness/team.py`: persistent members, versioned tasks, bounded scheduler and final drain.
- `harness/messaging.py`: direct mailboxes, request/reply linkage and delivery receipts.
- `harness/session.py`: common evidence, audits, budgets and explicit mode selection.
- `harness/single_agent.py`: single-context control with the same total domain capability.
- `harness/agent.py`: append-only turn loop, verbatim reasoning, validation and tool execution.
- `harness/llm.py`, `trace.py`, `accounting.py`: provider, exact inputs and accounting.
- `harness/execution.py`, `workspace_audit.py`: existing-container tools and shared-file snapshots.

See the [implemented protocol](docs/agent-team-design.md) and [historical evidence](docs/archive.md).
Foreground subagents were snapshotted at commit `f9c9a4a` and removed from active
source. Old `mas` and `delegated` flags are rejected, not silently reinterpreted.

## KramaBench

Use explicit `mode="team"` (default) or `mode="single"`. Team has four fixed
templates: `explorer` for source discovery, `analyst` for requirements and analysis,
`worker` for implementation/integration, and `verifier` for focused executable checks.
Explorer has shell and an advisory no-write instruction, not an enforced sandbox.
The Leader actively seeks meaningful multi-member decomposition with complementary
responsibilities, distinct deliverables and explicit dependencies. One end-to-end
member is a justified exception, not the default; a fixed roster or redundant work
is not required. Membership and local briefs are selected per task. The default
`leader_mode="coordinator"` has no domain tools, including file readers: domain work
and execution checks belong to Workers. `leader_mode="full"` is an explicit comparison
condition with all domain tools and the same coordination-first policy. No fixed roster
or mandatory review. Messages can wake idle and dependency-waiting members with
unchanged grants without starting their pending assignments. Workers end assignments
using `finish_task(status, summary)`; only an explicit `completed` claim with a normal
handoff unlocks dependencies. Plain final text is `unclaimed`, not inferred success.
Single and Team submit `pipeline_path`; freeze records file metadata/hashes, and
submit exports only the selected file after checking its frozen hash. Closing lists
paths, hashes and file types; no code is inserted into the Leader's context by submission.
Repeated indefinite waiting after a confirmed stall notice drains the team instead
of idling until the deadline. Message activations retain their grants and have
separate domain-usage accounting from task assignments.
Generic domain checks are shared with Workers through `PROJECT_CONTEXT`.
This proves identity, not execution or correctness. See the
[current benchmark guide](docs/kramabench.md).

Answer grading runs after attempts on the host, bound to exact submissions and the
pinned upstream metric mapping. Numeric approximation uses continuous error/RAE
metrics, not binary success. Lists retain F1/precision/recall. Semantic text grading
requires an explicitly supplied judge; missing authorization yields pending_judge,
not a false failure or an implicit paid call. Pipeline judging remains separate.
A final report is not a success verdict.

The batch launcher supports `--all-tasks --dry-run` to inspect the 104-task,
312-attempt scope without model calls or containers. Default question concurrency
is 12 (maximum 32); numerical libraries use one thread per container to prevent
oversubscription. See the guide before authorizing a paid run.

## Verification

Run only on the project server after inspecting processes:

```sh
scripts/server/sync.sh
scripts/server/remote.sh '.venv/bin/python -m pytest -q'
scripts/server/remote.sh '.venv/bin/python scripts/kramabench/offline.py --mode both --output outputs/team-fixture-NEW'
scripts/server/remote.sh '.venv/bin/python scripts/kramabench/offline.py --mode leader-pair --output outputs/leader-pair-fixture-NEW'
```

These checks use scripted clients, not paid models. The paid entry point is
`scripts/kramabench/pilot.py`; every invocation needs run-specific authorization.
`--mode leader-pair` explicitly selects two attempts, `team_coordinator` and
`team_full`, each with the same per-attempt ceilings and independent workspace.
It is not a third condition or an implicit extra run under `--mode team`.
It creates only selected task containers from an existing image, records frozen
settings and inputs, and removes only its own containers, never run evidence.
Historical scores do not establish results for the new Team runtime.
