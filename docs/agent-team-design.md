# Leader-Led Agent Team Protocol

2026-11-01. Implemented v4 contract; test and paid-run evidence are recorded
separately. Foreground subagents are archived at commit `f9c9a4a`; their active
implementation was removed at the user's request. No compatibility engine runs
behind the old `mas` or `delegated` flags.

## Architecture

The Leader assigns work and maintains team state. Workers execute and can message
one another directly. Risks, milestones, blockers and terminal handoffs reach the
Leader. Explicit messages, state transitions, model inputs and tool results remain
in an append-only trace.

This shares the broad team-lead/member/mailbox shape of
[Claude Code agent teams](https://code.claude.com/docs/en/agent-teams), not its exact
implementation. Here the Leader selects predeclared capability templates and writes
local task briefs. Workers cannot self-assign work, change permissions or spawn
nested agents. Membership is task-adaptive, not a fixed panel.

A team lasts one attempt. Single is a separate control using the same Agent loop
and overall domain capability ceiling. No fork or automatic full-task injection:
a new Worker receives its fixed template/project instructions and a local brief.
Later information comes through its own observations, explicit messages and shared
tools/files. This is context management, not strict information isolation.

## Authority And Capabilities

The main Team baseline defaults to `leader_mode="coordinator"`. Its Leader has
zero domain tools, including list/inspect/read/terminal/write. Its tool table contains
only spawn_worker, assign_task, update_task, finish_team, send_message, read_messages,
resolve_request, get_team_state, wait_event and the adapter's submit. Permissions
are enforced by the registered tool table, not only by instructions.

Workers own discovery, implementation, integration, repairs and domain verification.
For example, the Leader assigns a Worker to run an existing pipeline, compare the
observed output with the requirements, and report the command/result. This must
finish before finish_team; closure is not a place to start checks or repairs.
There is no mandatory reviewer count or semantic success gate. A Worker report
and Leader acceptance remain claims, not evaluator correctness.

`leader_mode="full"` retains all session domain tools only as an explicitly selected
ablation in this runtime. It is never launched automatically and is not the main
baseline. Manifest arm names are `coordinator_only` and `full_tool_leader_ablation`,
not the prior T0/T1 labels. Single retains all approved domain tools.

KramaBench v4 freezes four templates:

| Template | Responsibility | Domain grants |
|---|---|---|
| worker | Implement and integrate assigned components | Readers, write_file, terminal |
| explorer | Discover sources, schemas and relevant evidence | Readers, terminal |
| analyst | Clarify requirements, source meaning and scoped analytical questions | Readers, write_file, terminal |
| verifier | Run focused checks of assigned artifacts/claims and report discrepancies | Readers, write_file, terminal |

Readers include list/inspect/read files and retained output. All templates inherit
shared model/domain ceilings. These are fixed specialization instructions, not four
distinct permission levels or a mandatory four-stage pipeline. Multiple instances
of a template may own separate packages.

Explorer is instructed not to modify files but its shell can write. This is an
advisory role, not an enforced read-only sandbox or a reproduction of Claude Code's
shell permission system. It no longer has to inspect every row through file paging.
All templates and Single receive the same generic domain checklist through
`PROJECT_CONTEXT`: units/precision, coverage/missingness/duplicates/types, joins,
reproducibility and observed artifact checks as relevant. Weighting/interpolation
hints were removed rather than justified by the previously inspected task. Pipeline
implementation instructions apply to assigned implementation, not every explorer.
`LEADER_SYSTEM` contains no root-only analysis checklist. The prior task-tuned
archeology estimand heuristics remain inactive; see [improvement notes](team-improvement-candidates.md).

Model settings and grants cannot change mid-session. A shell grant allows arbitrary
code and writes within the container. Assigned write scopes are coordination rules,
not OS-enforced per-worker isolation. The runtime rejects overlapping outstanding
write scopes at task assignment; it cannot infer arbitrary shell write provenance.

The default Leader policy actively seeks meaningful multi-member decomposition
before assigning work: complementary specialists, distinct deliverables, explicit
interfaces/dependencies, parallel independent work and direct peer information
exchange. A single end-to-end member is an exception when no useful split fits the
task and remaining capacity; the Leader is instructed to record that reason in its
brief. There is no fixed minimum count, mandatory reviewer/panel, voting, discussion
rounds or automatic scientific-method selection. Duplicating work solely to fill
roles is discouraged. This is a delegation policy, not a runtime quota or proof that
a real model will follow it; the tool table separately enforces zero Leader domain work.

## Tasks And Persistent Members

Task records contain owner, local objective/context, dependencies, write scope,
state revision, specification revision, result revision, handoff and outcome.
Leader controls are:

- `spawn_worker(template, task, context?, write_scope?, depends_on?)`: create identity and queue work; return handles immediately.
- `assign_task(worker_id, ...)`: reuse an idle member after its prior handoff or cancellation; no mandatory acceptance.
- `update_task(task_id, expected_revision, action, reason)`: accept, reopen or cancel with compare-and-set revision checking.
- `finish_team(reason)`: irreversible stop-new-work and drain barrier.

Task states include assigned, running, blocked, reported, accepted, cancelled and
failed. Runtime controls own transitions. Worker progress cannot accept work.
Dependencies reference already-created tasks, preventing a task-board cycle;
execution starts after all referenced tasks have a normal completed handoff
(`outcome="done"`, status reported or accepted). Acceptance is optional. Forced
closing/limit reports are partial and do not unblock dependencies. Normal completion
is a lifecycle signal, not a semantic check that the result is sufficient or correct.

Reopen preserves identity, complete history and lifetime domain budget, increments
the specification revision and appends the repair brief. If a dependent has used
the prior result, it must first be cancelled and drained. New work for an old owner
does not permit reopening an earlier assignment behind its current assignment.

A Worker can have one active activation. An activation ends with its normal final
reply, a partial/limited outcome or failure. There is no extra summarization call.
Reports retain per-activation usage deltas and outcome; lifecycle status never
asserts scientific correctness or erases earlier recoverable errors.

## Messages And Requests

All members can call:

- `send_message(to, content, kind?, task_id?, reply_to?, needs_reply?)`
- `get_team_state()`
- `read_messages(offset?, limit?)`
- `resolve_request(message_id, reason)`
- `wait_event(timeout_seconds?)`

Workers also have `report_status(status, summary)`, with progress or blocked.
Risk/milestone messages are copied to the Leader; blockers and final/failure
handoffs automatically notify the Leader. Ordinary peer dialogue is not broadcast.
The Leader can inspect all explicit mail through bounded pages; Workers can inspect
only their own sent/received records.

Sender identity is supplied by the runtime. Reply linkage must match the original
requester and recipient. Replies associated with a superseded specification are
marked stale; a reply never mutates a task. Request disposition is open, responded
or resolved. Requester/Leader can explicitly resolve it with a reason. A late reply
does not reopen a resolved request.

Queued, appended to context and included in an attempted provider request are
distinct receipts. Exposure does not prove reading, use, trust or causal influence.
Send acknowledgements include recipient state and wake policy. Every message type,
including ordinary info, can wake an idle member; `needs_reply` tracks response
expectations only and does not control wakeup.
Missing replies and undelivered messages remain evidence, not silently successful
communication. Shared files and arbitrary shell output are additional channels;
the explicit-mail log is not a complete information-flow monitor.

An idle Worker receiving mail gets a bounded message activation on the same context
with its original template grants. No post-wakeup read-only policy or variant exists.
Message follow-ups do not overwrite the prior task result or grant task-assignment
authority. All calls count against the original shared budget and lifetime tool
usage. Activation admission, closure and exhausted identities may still prevent
wakeup; queued is not a guarantee of execution. Unconsumed mail remains recorded.

Message activations may perform domain work without a new task-board assignment.
Cancelling the old task does not cancel an independent message activation; closing
the team does stop new actions. Activation records distinguish `cause=message`,
`task_id=null`, `previous_task_id` and triggering message IDs from assigned work.
`report.json.activation_usage` counts model attempts and domain-tool calls by cause
and activation. These are execution-cause statistics, not a semantic classification
of productive work or exclusive attribution of workspace writes.

## Scheduling And Stop Semantics

One safe step comprises one model response and every associated tool result.
Mail is appended only between such steps, never while a request or tool batch is
in flight. One member cannot have concurrent steps. Global ordering is recorded
rather than assumed deterministic.

The executor has bounded Worker slots and a separate Leader slot. Waiting yields
the slot, retains history and wakes on incoming mail or an explicit timeout. Omitted
timeouts wait for an event within the session deadline; explicit timeouts have no
120-second cap. Blocked reports also yield; wakeup/progress restores running status.
The Leader receives one no-runnable-work notice per stalled episode only when no
member operation is in flight/ready, no assignment is runnable, no mail can be
delivered and no active finite wait can expire. Mail retained for terminal members
does not count as a progress source. Meaningful task/message/activation changes
re-arm that notice, not repeated state reads. If the Leader again requests an
indefinite wait with the same confirmed stall, the runtime starts draining and
retains the final-submit reservation. This avoids either waiting to the global
deadline or repeatedly polling the model. A finite wait is an explicit progress
source, not deadlock; it remains bounded by the session deadline. Circular waits
have no hidden model calls or automatic domain repair.

`wait_event`, `report_status`, `finish_team` and submit are sole-call controls.
A mixed batch containing one is refused without partial execution. `update_task`
can be batched; updates execute serially and each retains its revision check.
Write scopes accept both relative paths and paths under the workspace root (e.g.
`/workspace/producer`); traversal/outside-root paths remain invalid.

Closure is open -> draining -> frozen -> final submission. Draining refuses new
actions, waits for already-admitted operations, and requests bounded final handoffs.
Workers' slots/reservations remain owned until handoffs and audits finish. Freeze
also waits for admitted Leader operations in the full-tool ablation. Freeze
records a shared-workspace snapshot, then publishes a
closing state with unresolved work/mail and `frozen_files`. Each file has its path,
snapshot hash, type and submission status. Regular files are `hash_recorded`, not
pre-exported or guaranteed readable/valid/executable. The Leader selects a regular
file path directly without reading file content.
The final Leader request receives queued Leader notices before it submits.
No new Worker tool action is admitted after closure. This is not an OS-level
filesystem freeze; arbitrary shell background processes are not individually
isolated. Submit reads only the selected file; its bytes must match the snapshot
hash. Later changes are rejected rather than silently exported. No post-freeze domain tool
is admitted, even for the full-tool Leader ablation.

A key/balance error stops further admission immediately. Already-in-flight requests
cannot be cancelled retroactively; their receipts and failures are still collected.
Timeout/provider/output/context failures are recorded, with no retry or repaired
transcript. Aborted runs retain partial handoffs and unclosed-mail dispositions.

## Budgets And Evidence

The pilot entry point exposes these bounded settings (not authorization to run):

| Limit | Value |
|---|---:|
| Shared model calls, including message activations/final handoffs | 64 |
| Shared domain-tool calls | 120 |
| Execution time | 1800 seconds |
| Audit allowance | 120 seconds |
| Worker identities / activations / parallel Workers | 8 / 64 / 4 |
| Explicit send/report operations / UTF-8 bytes per message | 128 / 8192 |

These are ceilings, not targets. Each active Worker has one reserved report call;
the Leader has one reserved final call. Reservations are inside the shared ceiling.
The Leader cannot spend its final reservation while Workers remain active.
Control tools are not domain calls, but every model request producing controls
counts. No hidden mail-model call, paid judge or automatic retry exists.
There are no lower 20/12-turn or 60/24-domain defaults for individual templates.
The runtime's default activation ceiling inherits the shared model-call ceiling;
the pilot explicitly uses 64. Message activations still consume shared model,
message and domain budgets, but no longer encounter a separate default 16-wakeup
bottleneck. Explicit lower activation overrides remain available and recorded.
Static budget numbers are absent from both Single and Team system prompts. Limits
remain enforced and recorded; dynamic remaining-budget state and final-call notices
remain operational signals, not hidden extra compute.

Audits measure shared intervals, not exclusive write attribution. The execution
clock excludes audit-only time, never audit time overlapping model/tool execution.
Input-capacity checks include final notices and preserve reasoning verbatim;
exhaustion never triggers silent truncation or summarization.

The adapter freezes source, model, prompts, template/tool contracts, budgets, input
hashes and environment. Single and Team submit `answer`, `pipeline_path`,
`evidence` and `unfinished`. Team snapshots files after drain and before its closing
notice; Single performs the same snapshot at its sole submit call with no concurrent
member. The runtime exports only the selected file at submit as native `pipeline_code`,
after checking the frozen hash. Submit receipts contain path/hash/status, not code;
runtime exports are separate from model-visible observations. No Leader code reading
or copying is needed. Retries of invalid submissions are ordinary model turns inside
the same budget, not automatic calls. Single takes a fresh snapshot for each attempt;
Team remains bound to its original snapshot hashes.

Artifact export rejects outside-root/traversal paths, symlink components, nonregular
files, empty/non-UTF-8 files, files over 1 MiB and snapshot/hash mismatch. There is
no aggregate 128-file/16-MiB capture quota and no eager per-file export at freeze.
Unrelated CSV/binary files cannot consume the selected artifact's export quota.
The workspace snapshot still hashes all audited files once and uses audit time;
this is not constant-cost handling of arbitrarily large workspaces. These shared
artifact-transport limits apply equally to Single and Team. Snapshot/export I/O
uses the audit allowance and remaining execution deadline, not model/domain calls.
A missing pipeline requires null answer, null path and explicit unfinished work.
The immutable native export still uses `pipeline_code` for evaluator compatibility.
Hash binding proves artifact identity, not execution or scientific correctness;
no trusted pipeline re-execution or automatic correctness check is added implicitly.
The runtime does not feed file contents to the Leader. Workers can still explicitly
send content in messages, so this tool restriction is not strict information isolation.

The v1.1 inline hash-binding policy and the v1 paid result are historical. See
[the historical review](team-review-20261101.md) for v2 evidence and the
[coordinator baseline verification](team-coordinator-20261101.md) for v3, followed
by [stability and specialist-policy verification](team-stability-v4-20261101.md) for v4.

Trace analysis includes exact reconstructed inputs, usage and error accounting,
prompt sizes/cache reuse by role, request exposure and unresolved mail. Estimated
token cost is distinct from attributable actual cost; shared-account balance deltas
cannot isolate this run's charge.

## Implementation And Verification

| Owner | Responsibility |
|---|---|
| harness/team.py | Task authority, persistent activations, scheduler and closure |
| harness/messaging.py | Queues, request linkage and communication receipts |
| harness/agent.py | Shared append-only model/tool turn loop |
| harness/session.py | Common budgets, audits and session evidence |
| harness/artifacts.py | Bounded snapshot-bound file export, without executing it |
| harness/trace.py | Reconstruction, integrity checks and exposure summaries |
| Adapters | Domain grants, input/output contracts and independent grading |

Server-only scripted tests cover asynchronous peer delivery, history/turn integrity,
idle message wakeup with unchanged grants, stale updates, automatic dependencies, reopening, quota
rejection, shared boundaries, fatal errors, mixed-control refusal and final drains.
Scripted correctness does not establish real-model coordination quality.

Not implemented: distributed/crash-resumable execution, OS-enforced per-worker file
isolation, semantic judging of messages, automatic priority optimization, or a full
causal attribution system. Worker task metadata can be read explicitly through the
shared task board; this is not a hidden-context experiment.

## Research Boundary

The previously inspected archeology case is diagnostic, not held-out evidence.
Its pinned numerical reference disagreement must remain visible, not be repaired
to improve a score. One Team run cannot establish superiority or a communication
effect.

Future comparisons should freeze task splits, exact source/settings and evaluator
coverage. Single, one-Worker coordination and adaptive multi-Worker teams address
different questions. To isolate peer communication, vary routing on the same Team
scheduler and artifact visibility, not against the retired foreground runtime.
Equal call ceilings are not equal realized compute. Retain failed attempts and
measure redundant work, unresolved requests, stale assumptions, costs and
independently verified outcomes before selecting improvements.
