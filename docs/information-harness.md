# Runtime and Information Harness Boundaries

Each member has its own append-only context. Public metadata, fixed role prompts
and private assignments are initialized independently. No member inherits the
leader's full conversation. A shared filesystem is not a shared model context.

## Ownership

| Component | Owns | Must not do |
| --- | --- | --- |
| Runtime (agent_team.py) | Scheduling, budgets, permissions, verbatim mailbox transport, lifecycle, submission versions, finalization | Choose or rewrite substantive message content |
| Information Harness (information.py) | Frozen sender instructions, outgoing-message validation, explicit evidence/artifact access | Change scheduling, roles, permissions, budgets, completion rules or evaluator |
| Benchmark adapter | Private inputs/workspaces, immutable code snapshots, protected merge/tests | Leak hidden tests/gold or treat a report as a tested solution |

CommunicationPolicy is an immutable versioned instruction artifact, included in
the control digest and each sender's stable system prefix. It guides the sender's
choice of content, recipients and explicit references. prepare_message is the
single validation boundary for send_message, explicit submission reports and
nonempty worker idle replies forwarded to the leader. Idle replies never submit.
Runtime delivers the resulting text verbatim.
This is not an executable plugin, an additional LLM encoder, or a guarantee of
semantic compliance. A policy updater is not implemented.

Status events and list_tasks expose a fixed metadata projection only. They do
not carry free-form progress reports, results, assignment text or automatic
evidence summaries. Full snapshots live in evaluator/trace storage and are never
silently appended to the leader's context. See completion-protocol.md.
Identical team_state is not repeatedly appended. Protocol denials (missing grants,
frozen writes, invalid arguments) and ordinary nonzero command observations are
separate from execution failures in review packets.

## Explicit Attachments

Tool observations and published artifacts are private by default. Selecting
evidence_ids or artifact_ids grants access to those exact immutable records.
A reference is not a read: read_evidence/read_artifact materializes it.
Recipients may forward granted references, not unrelated records. New artifact
revisions require new explicit grants. Publication alone never broadcasts.
The invariant access checks are infrastructure, not an RSI-mutable policy.
Missing grants return an actionable attachment instruction and a typed protocol
error. Send receipts enumerate selected attachments. There is no implicit grant
from a quoted artifact ID and no automatic private-context sharing.

## Domain Execution and Evaluation

CooperBench workers have separate feature descriptions and repository containers.
Hidden tests and gold patches are evaluator-only. ContainerWorkspace exposes
read_file, write_file and terminal inside externally provisioned containers; it
never runs model commands on the host or provisions containers itself. The caller
owns mounts, credentials, network/resource isolation and background-process control.

The adapter captures explicitly selected implementation files against the pinned
base. Tests/scratch paths are excluded and the worker index is not changed.
Agent-failed runs retain terminal snapshots for diagnosis and count as failures. Final exports
come from the frozen snapshot, never a fresh end-of-run workspace read. grade.py
checks snapshot IDs, content digests, exported patches, base and official image
identity before invoking the pinned merger/tests in a fresh evaluator sandbox.
Tool output and message bodies are raw text with short metadata headers, not
nested JSON strings. Trace storage may use JSON without changing model-visible
text. Offline contract tests and native baseline/gold checks are separate gates;
only graded paid attempts establish observed Agent Team task outcomes.

Receipts establish what was sent, delivered and included in a model request, not
truth, attention or causal use. Policy changes cannot alter the delivery ledger.
