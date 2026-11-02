# Leader-Led Agent Team Protocol

2026-11-02. Implemented v5 task contract with budget-feedback/admission repairs;
test and paid-run evidence are recorded
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
only spawn_worker, assign_task, update_task, continue_worker, finish_team, send_message, read_messages,
resolve_request, get_team_state, wait_event and the adapter's submit. Permissions
are enforced by the registered tool table, not only by instructions.

In the coordinator condition, Workers own discovery, implementation, integration,
repairs and domain verification.
For example, the Leader assigns a Worker to run an existing pipeline, compare the
observed output with the requirements, and report the command/result. This must
finish before finish_team; closure is not a place to start checks or repairs.
There is no mandatory reviewer count or semantic success gate. A Worker report
and Leader acceptance remain claims, not evaluator correctness.

`leader_mode="full"` permits all session domain tools as an explicitly selected
comparison condition. Both conditions share the coordination-first, meaningful
multi-member policy, templates, communication, claims, budgets and submission rules;
only the Leader tool table and its capability description differ. The coordinator
remains the default, not an assumption that one condition will perform better.
Manifest names are `coordinator_only` and `full_tool_leader`. Historical v3/v4
`full_tool_leader_ablation` labels remain in old evidence. Single retains all domain tools.

KramaBench retains four templates (current catalog: `kramabench-team-v8`):

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
`LEADER_SYSTEM` contains no root-only analysis checklist or task-tuned estimand rules.

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
a real model will follow it; the coordinator's tool table separately enforces zero
Leader domain work. The full-tool Leader can investigate, execute or check directly,
while retaining the same organizational responsibility.

Local briefs must distinguish relevant requirement wording from provisional Leader
assumptions. Shared project guidance separates evidence for an interpretation from
execution/arithmetic checks conditional on it: agreeing implementations do not prove
a shared premise. Material ambiguities warrant a focused evidence check, not an
automatic fixed reviewer stage. Further review should name the unresolved question
and evidence that could change the decision; repairs call for checks of changed
behavior and affected interfaces, reusing established artifacts/findings. Remaining
uncertainty and unchecked work belong in the handoff. These are task-neutral policies,
not a semantic evaluator or a guarantee of improved model reasoning.

## Tasks And Persistent Members

Task records contain owner, local objective/context, dependencies, write scope,
state revision, specification revision, result revision, handoff, runtime outcome
and member-declared `completion_status`.
Leader controls are:

- `spawn_worker(template, task, context?, write_scope?, depends_on?)`: preflight capacity, create identity and queue work; return handles immediately.
- `assign_task(worker_id, ...)`: reuse an idle member or queue behind active message-only work after its prior assignment returned/cancelled; no mandatory acceptance.
- `update_task(task_id, expected_revision, action, reason)`: accept, reopen or cancel with compare-and-set revision checking; reopening also preflights capacity.
- `finish_team(reason)`: irreversible stop-new-work and drain barrier.
- `continue_worker(worker_id, instruction)`: resume a checkpointed activation with a focused next step, without resetting history, permissions, tools or report reservation.

Task briefs support `deliverable` and `stop_condition` alongside `task` and `context`.
Publish the complete local brief in one assignment operation; do not send a
preliminary message promising a later task. If such a message has already activated
an idle member, assignment can queue behind that message work. The active history
is not rewritten/interrupted, the old result remains unchanged, and the new task
starts only after message return and satisfied dependencies. A second outstanding
assignment is rejected. Reusing that member's old write scope is safe under this
serialization; other members' active scopes remain protected. Queuing does not
reserve model capacity.

Task states include assigned, running, blocked, reported, accepted, cancelled and
failed. Runtime controls own transitions. Worker progress cannot accept work.
Dependencies reference already-created tasks, preventing a task-board cycle;
execution starts only after all referenced tasks have a normal handoff (`outcome="done"`,
status reported or accepted) and an explicit `completion_status="completed"` claim.
Workers use the sole-call `finish_task(status, summary)` control to return an assignment
as completed, partial, blocked or failed. This ends the activation without another
model call or a compulsory report template. A plain final reply is retained verbatim
as `completion_status="unclaimed"`; the runtime does not infer status from prose.
Accepting a partial/unclaimed report does not release dependencies. Forced closing
reports remain partial runtime outcomes without inferred completion. Reopen clears
the old completion claim for the new specification. Explicit completion is still a
member claim, not execution verification, evaluator correctness or team success.

Reopen preserves identity, complete history and lifetime domain budget, increments
the specification revision and appends the repair brief. If a dependent has used
the prior result, it must first be cancelled and drained. New work for an old owner
does not permit reopening an earlier assignment behind its current assignment.
A message activation before a dependent assignment starts is not treated as having
consumed the dependency result merely because its member is active.

A Worker can have one active activation. An activation ends with its normal final
reply, a partial/limited outcome or failure. There is no extra summarization call.
Reports retain per-activation usage deltas and outcome; lifecycle status never
asserts scientific correctness or erases earlier recoverable errors.
Handoffs also include the shared budget after releasing that activation's report
reservation. This is a snapshot, not an allocation to the recipient.

## Messages And Requests

All members can call:

- `send_message(to, content, kind?, task_id?, reply_to?, needs_reply?)`
- `get_team_state()`
- `read_messages(offset?, limit?)`
- `resolve_request(message_id, reason)`
- `wait_event(timeout_seconds?)`

`send_message` also accepts `action=none|reply|work`, `expected_result` and
`stop_condition`. All actions may wake idle members with unchanged tools. Omitted
action defaults to reply for questions/needs_reply requests and none otherwise.
None is an FYI: guidance asks for an immediate short return without tools or
acknowledgement mail, not another review. Reply requests a focused answer. Work
requires both expected_result and stop_condition before any mail is published.
These are logged instructions, not a semantic classifier or a read-only permission
variant. Sole-call `finish_message(summary)` returns message-only work without an
extra summarization call or assignment completion claim. It notifies the Leader,
not the peer, avoiding automatic acknowledgement cycles. Plain final text remains
supported. Legitimate checks/repairs retain original tools; semantic adherence to
work scope still depends on the model.

Workers also have `report_status(status, summary)`, with progress, blocked or checkpoint, and
the assignment-only `finish_task(status, summary)` described above. `report_status`
blocked yields while retaining the active assignment; `finish_task` blocked returns
it with an unresolved-blocker claim. Message-only activations cannot finish a task.
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
including ordinary info, can wake an idle or dependency-waiting member; `needs_reply` tracks response
expectations only and does not control wakeup.
Missing replies and undelivered messages remain evidence, not silently successful
communication. Shared files and arbitrary shell output are additional channels;
the explicit-mail log is not a complete information-flow monitor.

An idle or dependency-waiting Worker receiving mail gets a bounded message activation on the same context
with its original template grants. No post-wakeup read-only policy or variant exists.
Message follow-ups do not overwrite the prior task result or grant task-assignment
authority. All calls count against the original shared budget and lifetime tool
usage. Activation admission, closure and exhausted identities may still prevent
wakeup; queued is not a guarantee of execution. Unconsumed mail remains recorded.
For a member whose assignment has not started, this activation receives its local
pending brief/context and explicit mail, not the Leader history. The pending task
stays assigned with no result update. When the message activation returns, the member
returns to assigned unless that task was cancelled; only satisfied dependencies can
start its assignment activation. There is no concurrent message/assignment invocation
within the same member and no new read-only permission variant.

Message activations may perform domain work without a new task-board assignment.
Cancelling the old task does not cancel an independent message activation; closing
the team does stop new actions. Activation records distinguish `cause=message`,
`task_id=null`, `previous_task_id` or `pending_task_id` and triggering message IDs from assigned work.
`report.json.activation_usage` counts model attempts and domain-tool calls by cause
and activation. It includes trigger sender/task links, newly exposed mail, domain-call
event references, declared tool paths, before/after snapshot references, observed
file/hash deltas and overlapping activations. Leader domain usage is separate.
`workspace_changes=null` means missing audit evidence, not no writes. Snapshots use
the existing tracked/nonignored workspace scope and are non-atomic; concurrent peers,
the full-tool Leader or background commands may cause the same observed delta.
These are execution-cause/shared-interval statistics, not verified conflicts, reasons
for edits, semantic productivity or exclusive write attribution. Inspection through
read_messages remains a separate logged tool path, not automatic mailbox exposure.

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

`wait_event`, `report_status`, `finish_task`, `finish_message`, `finish_team` and submit are sole-call controls.
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

### Bounded Work Checkpoints

`worker_quantum=16` is the default maximum model requests per uninterrupted Worker
slice, for both assignment and message activations. It is a scheduling quantum,
not a new task budget or a claim that 16 calls suffice. It is recorded in session
configuration and the pilot's frozen common limits; Single ignores this Team-only
setting. It does not increase shared ceilings or final-call reservations.
Sixteen is an explicit coarse scheduling default, not an empirically optimal or
question-specific value. Smaller slices increase Leader-decision overhead.

At a safe completed turn boundary, an unfinished slice reaching the quantum pauses
in `checkpoint`; no extra report/model call is made automatically. Workers may also
call `report_status(checkpoint, summary)` early with useful observed progress. The
Leader receives a logged checkpoint and current budget. A checkpoint releases its
executor slot but retains history, activation identity, lifetime tools and report
reservation. It is not a handoff/completion claim and releases no dependencies.
Only `continue_worker` resumes the slice with an appended local instruction and a
fresh scheduling quantum, not a fresh budget. Cancellation and team closure can
drain paused work. Pending mail does not silently bypass a checkpoint or count as
a runnable progress source; messages are delivered at the next resumed/draining
safe boundary. Idle members can still wake for any message action.

Leader and Worker turns receive append-only count-based budget feedback; Workers
also see calls left in the current slice and are asked to use its last call for a
checkpoint summary if unfinished. Shared domain guidance prioritizes execution of
the saved production artifact over optional independent reconstruction, limits
discovery to needed sources, and scopes post-edit checks to changed behavior.
The runtime enforces pauses, not semantic correctness or the importance of a check.

Server offline verification after scoring/cleanup (2026-11-02):
**273 passed, 5 Docker opt-ins skipped**.
New regressions cover assignment behind active/paused message work, unchanged
history and old results, duplicate outstanding-task rejection, message intent and
work-boundary validation, one-call message return with unchanged domain grants,
automatic/voluntary checkpoints, continuation without new activations, dependency
safety, cancellation/drain and paused mail/stall handling in the common scheduler.
Existing coordinator/full grant, frozen-artifact and 128-call regressions also pass.
No paid calls, retries, pipeline replay or container experiment was run for these
changes. Real-model scope adherence, token/cache overhead, accuracy and cost effects
remain unmeasured. Prior runs and their reports are unchanged.

## Budgets And Evidence

The pilot entry point exposes these bounded settings (not authorization to run):

| Limit | Value |
|---|---:|
| Shared model calls, including message activations/final handoffs | 600 |
| Shared domain-tool calls | 300 |
| Execution time | 3600 seconds |
| Audit allowance | 120 seconds |
| Worker identities / activations / parallel Workers | 8 / 64 / 4 |
| Maximum Worker model calls per scheduling slice | 16 |
| Explicit send/report operations / UTF-8 bytes per message | 128 / 8192 |

These are ceilings, not targets. Each active Worker has one reserved report call;
the Leader has one reserved final call. Reservations are inside the shared ceiling.
The Leader cannot spend its final reservation while Workers remain active.
Control tools are not domain calls, but every model request producing controls
counts. No hidden mail-model call, paid judge or automatic retry exists.
There are no lower 20/12-turn or 60/24-domain defaults for individual templates.
The runtime's default activation ceiling inherits the shared model-call ceiling;
the pilot retains its explicit 64-activation ceiling. Message activations still consume shared model,
message and domain budgets, but no longer encounter a separate default 16-wakeup
bottleneck. Explicit lower activation overrides remain available and recorded.
Static budget numbers are absent from both Single and Team system prompts. Limits
remain enforced and recorded; dynamic remaining-budget state and final-call notices
remain operational signals, not hidden extra compute.

The prior six-question rerun used 128 shared model calls and 240 domain-tool calls.
For the user-authorized paper-informed checkpoint rerun, pilot/batch defaults are
600/300 with a 3,600-second execution ceiling, common to all conditions. See the
[benchmark guide](kramabench.md) for the paper-informed diagnostic ceiling.
No task-dependent allowance, retry or extra final call was added. Generic harness caller-supplied ceilings are
unchanged. The Leader receives a compact shared-budget snapshot at every safe turn
boundary before its next request, after queued mail. This append-only notice contains
counts/limits/reservations, not timestamps, trace IDs or a rewritten system prefix.
It costs no extra model call but does add input tokens. Spawn/assign/update receipts
and activation-rejection notices also include current counts. Concurrent requests
can consume capacity after a snapshot; counts are not a promise of future capacity.

Spawn, assign and reopen reject insufficient model/activation capacity before
publishing or modifying an assignment. The model preflight uses the same minimum
as activation admission: two unreserved calls, one for work and one report reservation,
in addition to existing reservations. It is an advisory capacity test, not a claim
that two calls can finish the assignment or a reservation for queued work. Dependencies
still gate execution; dependency-waiting assignments do not reserve calls or start
early. Activation rechecks and reserves atomically, so concurrent consumption can
still prevent queued work from starting. Accept/cancel remain available at low
capacity, and the Leader final reservation is preserved. No extra repair quota or
fixed review roster is imposed.

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

Earlier inline-submission protocols and dated experiment reports are retired from
active documentation. Git and retained source archives contain those versions;
see [retention and cleanup boundaries](archive.md).

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

Budget-feedback coverage includes nonmutating spawn/assign/reopen rejection, dependency waiting,
advisory preflight versus atomic concurrent reservation, late activation refusal,
fresh Leader/handoff budgets, append-only traces in both Leader modes and a
128-call ceiling regression. Scoring tests cover the six pinned answer types and
all offline workload references; see [benchmark metrics and coverage](kramabench.md).
No paid agent/judge/retry or new container experiment was run for this cleanup.

Not implemented: distributed/crash-resumable execution, OS-enforced per-worker file
isolation, semantic judging of messages, automatic priority optimization, or a full
causal attribution system. Worker task metadata can be read explicitly through the
shared task board; this is not a hidden-context experiment.

## Research Boundary

The explicit `--mode leader-pair` runner selects coordinator and full-tool Teams
once each, with independent workspaces, a matched common contract and separate
frozen condition records. It neither flips the default nor authorizes paid calls.
Both arms prioritize collaboration; the intended treatment is the Leader tool grant
and the accurate capability description, not different task decomposition prompts.
Realized membership, decomposition and verification remain model decisions and can
therefore differ between conditions. This comparison cannot by itself isolate the
effect of peer communication, equalize actual compute or establish causal superiority.

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
