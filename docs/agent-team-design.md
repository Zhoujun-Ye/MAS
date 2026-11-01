# Leader-Led Agent Team Design

2026-11-01. Design proposal, not an implemented runtime or an experiment result.
The user has selected four architectural requirements: the Leader assigns work
and maintains team state; Workers can message one another directly; the Leader
receives key progress, risks and results; communication is retained for analysis.
The protocol choices below make that direction concrete for implementation.

This replaces the proposed hub-only communication policy, not historical source
or evidence. The currently implemented foreground runtime remains documented in
[leader-subagent.md](leader-subagent.md). Do not restore retired CooperBench code,
old study criteria, fixed peer teams or RSI machinery to implement this design.

## 1. Architecture And Scope

Use centralized task authority with distributed execution and direct peer
communication. A team is created for one benchmark attempt, not a permanent
cross-task organization. Membership and decomposition adapt to the task, while
capability templates, tool ceilings and model settings are fixed for the session.

```text
                         Leader
                 assignments / decisions
                  /          |          \
              Worker A <-> Worker B <-> Worker C
                  \          |          /
                  versioned work artifacts

       risks / blockers / milestones / results -> Leader
       messages / state changes / execution -> append-only trace
```

The diagram does not restrict peer connectivity: any existing live member can
address any other member. There is no mandatory broadcast, discussion round,
fixed roster, worker count, review panel or majority vote. Simple tasks may use
one Worker; dependent tasks need not be artificially parallelized.

[Claude Code agent teams](https://code.claude.com/docs/en/agent-teams) provide a
public reference for a team lead, independent member contexts, shared task state
and direct member messages. Our Leader-only assignment authority is a deliberate
restriction relative to systems that also allow self-claiming work. This is not
a product reproduction or evidence that direct communication improves results.

## 2. Responsibility And Authority

| Actor | Owns | Does not own |
|---|---|---|
| Leader | Task interpretation, decomposition, member selection, ownership, dependencies, priorities, acceptance decisions, final answer | Main implementation, bulk computation, silently repairing every failed Worker |
| Worker | Assigned execution, local planning, self-checks, peer questions and answers, artifact production, reporting limitations | Assigning another Worker's tasks, changing global requirements, granting tools, declaring benchmark correctness |
| Runtime | Identity, queues, scheduling, admission, permissions, counters, state transitions and trace receipts | Choosing a scientific method, judging answer correctness, deciding which substantive claim is true |
| Adapter/evaluator | Domain tools, input/output contracts and independently bound evaluation | Team orchestration or hidden repair of submissions |

Leader domain access is limited to registered read-only evidence tools and final
submission, alongside team-management tools. Do not grant a terminal and describe
it as read-only. Workers implement, calculate, repair and execute integrated
pipelines. The Leader can read evidence, reason about contradictions and synthesize
the final explanation; restricting tools does not prevent mental calculation.
Leader reasoning or token expenditure is not assumed to be small.

When integration requires code changes or a full execution, the Leader assigns an
integration work package to an existing or new Worker. Failure leads to an explicit
follow-up, reassignment within the frozen policy, or an incomplete result, not an
unlogged switch to Leader execution. No hidden model/provider retries are added.

Start with two fixed capability templates: an execution-capable `worker` and an
`explorer` with only registered read-only domain tools. Both have team messaging.
Review, preparation and calculation are task purposes rather than mandatory
permanent roles. Adapters may later offer frozen specialist catalogs as separate
configurations. Neither a generated brief nor a peer message changes permissions.

## 3. Persistent Members And Task State

Workers retain identity, append-only context and lifetime tool consumption for the
attempt. They are not discarded when a work package finishes. One Worker owns at
most one active execution assignment at a time, but can answer peer questions
without acquiring the sender's task. There is no recursive spawning or delegation.

The runtime maintains a versioned task board; the Leader makes the organizational
decisions recorded in it. It is not a second model-generated summary of team state.
Each task records its objective, acceptance criteria, owner, dependency IDs,
input/output references, write scope, status and decision history. A specification
revision identifies the objective/ownership contract; a separate state revision
orders progress updates, and result revisions identify distinct handoffs. Routine
progress does not invalidate every message referring to the same specification.
Each member has a stable ID, template, current task and operational state.
Compact roster/task summaries are available to all members for addressing peers;
full original tasks and transcripts are not automatically broadcast.

Separate three kinds of state:

| State | Meaning |
|---|---|
| Member lifecycle | Ready, in flight, waiting, idle, exhausted, failed or closed |
| Work-package state | Planned, assigned, running, blocked, reported, accepted, failed or cancelled |
| Evaluation | Independently evaluated outcome, or not evaluated |

A Worker can report progress, blocking conditions and a candidate result for its
own assignment. A normal final reply for an execution assignment becomes a
`reported` handoff, not automatic acceptance. Forced-limit replies also retain
their partial termination reason.
Only the Leader accepts, reopens, cancels, reprioritizes or reassigns a task.
Acceptance is the Leader's decision about a particular result revision, not a
runtime or benchmark proof of correctness. Prior errors remain visible.

Leader mutations use an expected state revision. Worker updates also identify
their assignment/specification revision. Stale mutations are rejected visibly
rather than overwriting newer state. Reassignment fences the previous assignment:
no new domain action may start for it. Already-admitted work must
drain before a new owner writes to that scope. In-flight actions cannot be undone.
Dependencies are released by explicit Leader acceptance, not by a Worker's claim
that its output is ready. Incorrectly declared dependencies remain observable;
the runtime cannot infer the true task graph.

Briefs identify the local goal, relevant original wording, known evidence,
unverified assumptions, prerequisites, output interface and write ownership.
Workers may challenge a brief and suggest replanning. They must not treat a peer's
suggestion as an authorized change of task, permissions or acceptance criteria.
Fixed shared project instructions still apply; there is no fork or automatic
parent-history/full-task injection.

## 4. Direct Communication And Leader Visibility

### Message contract

`send_message` addresses one member, without Leader approval or an extra relay
model call. The runtime derives the sender identity; callers cannot forge it.
The envelope contains a run-local message ID, recipient, kind, relevant task and
specification revision, optional reply-to ID, content, artifact references and
`needs_reply`. Replies validate the referenced request and its participants;
replying to an unrelated message does not resolve another member's request.
Kinds are `question`, `answer`, `info`, `milestone` and `risk`.
IDs support routing and provenance; timestamps and trace-event IDs stay out of
model prompts. Message content is member-supplied information, not a system prompt.

Questions and answers may refine an interface, exchange evidence, challenge an
assumption or expose a conflict. They do not transfer ownership or create tasks.
There is no all-to-all broadcast tool in V1; multiple explicit recipients require
multiple accounted sends. Acknowledging a send means queued, not delivered to a
model, understood, answered or acted upon.

Unknown, failed, closed or exhausted recipients produce an explicit rejection,
not a silently lost message. An idle recipient is not a failed recipient.
Replies to stale task revisions are retained and marked stale; they cannot
overwrite current task state. Corrections are new messages referencing the old
message, never edits to old context.

### What the Leader receives

| Event | Delivery to Leader |
|---|---|
| Ordinary peer question, answer or info | No automatic full-content copy; visible through the communication log |
| Sender-labeled risk or milestone | Same content copied automatically, linked to the original message |
| Blocked work, final handoff, partial work, execution/provider failure or exhausted limit | Automatic runtime notice with task/member identity and actual outcome |
| Ownership/dependency changes and outstanding-request dispositions | Versioned task-board event |

Workers report meaningful milestones, not every tool call. The runtime routes
declared risks but does not use an unbudgeted model to classify every message.
A Worker can fail to recognize a risk or label it as ordinary info; this is a
measurable reporting failure, not something the design claims to eliminate.
The Leader can inspect any recorded team message on demand using bounded paging.
It sees task-state changes and unresolved-request metadata without automatically
receiving every peer conversation or tool transcript.

Milestone/risk delivery to the peer and the Leader is one admission decision:
either both are queued or the send is rejected. The payload is stored once with
linked deliveries. Each recipient's subsequent model input is charged normally.
Critical events are not interrupts inside an in-flight model/tool call; their
latency to the next safe boundary must be measured.

### Requests and blockers

`needs_reply` creates a tracked request, not a synchronous RPC. The sender can
continue independent work or explicitly wait. An `answer` tied to `reply_to`
records a response; it does not prove the request was substantively satisfied.
The requester can mark it resolved or ask again. Only the Leader can close
another member's request with a recorded disposition.

Workers do not busy-poll. Missing prerequisites are reported as blocked, with
the relevant task/message IDs. Waiting cycles and a team with no runnable work
produce a Leader notice; the runtime does not invent a repair or declare success.
Wait timeouts are frozen configuration and yield one visible event per wait,
not automatic repeated paid calls. The Leader decides whether to resume, revise,
cancel or finish with unresolved work.

## 5. Event-Driven Scheduling

Replace foreground batch waiting with a bounded event-driven team scheduler.
Spawning returns identity/task handles immediately. The Leader can receive and
process events while Workers execute, instead of waiting for the slowest member
of an entire batch. This changes scheduling as well as communication; old versus
new results cannot isolate the causal effect of direct messages.

- At most four Worker model/tool turns run concurrently by the initial default,
  plus at most one Leader turn. A member never has two concurrent model calls.
- A turn comprises one model response and all corresponding tool results.
  Only that member's execution owner appends to its context. Incoming messages
  are queued while a request or its tools are in flight.
- At a safe boundary, after every outstanding tool call has a result, the owner
  appends an ordered inbox snapshot and freezes the next request. New arrivals
  belong to a later snapshot; they never mutate an in-flight request.
- Runnable members are serviced by a bounded fair queue. Multiple arrivals for
  one member coalesce into one pending activation, not one model call per message.
- `wait_event` yields to the scheduler and releases the execution slot. It must
  be the only tool call in its response, preventing a wait from blocking an
  unsent question or other tools in the same batch. Dependency waits also release
  slots. A waiting member must not occupy a thread needed by its answerer.
- An active Worker consumes incoming messages on its next turn. A waiting Worker
  can wake on an applicable message, dependency change, timeout or stop event.
  Unrelated arrivals do not create unlimited empty wakeups.
- An idle Worker is retained. A peer question with `needs_reply=true` can schedule
  a bounded clarification activation without Leader approval. Informational mail
  alone does not wake an idle Worker. Clarification can read evidence and reply,
  but new production requires a Leader assignment; fixed dispatch rules reject
  production actions without a live owned task.

Every activation, including peer-triggered clarification, consumes the same
session model allowance and fixed activation limits, with its own report
reservation. Mail arrivals never reset lifetime tools or the current activation's
turn counter. Rejected wakeups remain visible to the sender and Leader. No hidden
inference, automatic retry, extra summarizer or adaptive model switch is involved.
These are fixed session admission rules, not peer-granted capabilities.

Clarification activations answer requests using explicit linked messages while
tools are available. Their final reply is an activation summary, not a new task
result or an automatic answer to every pending question. Any unanswered requests
stay visible. This prevents a peer question from silently reopening an accepted
artifact or changing its owner.

Context delivery is append-only, in per-recipient accepted order. Large inboxes
are split into bounded ordered batches; the remainder stays pending and its count
is visible. No accepted message is silently truncated or dropped. Capacity checks
include the selected inbox batch, applicable final notices, tools and output
allowance before provider admission. Unfitting mail remains visibly pending or
ends in a recorded capacity failure; a reserved call is not reserved context
space. Full reasoning histories remain verbatim.

V1 requires process-lifetime delivery guarantees, not crash-resumable distributed
execution. Trace writes must precede exposing state to another actor; logging
failure stops new dispatch. Flushes are not a promise of fsync durability or
exactly-once execution across process/host crashes. An interrupted attempt remains
incomplete evidence rather than being transparently replayed.

## 6. Artifacts And An Example

Use direct messages for small coordination content; use workspace artifacts for
large tables, code, logs and reproducible results. An artifact reference includes
path, producing task/revision and content hash when verified by a trusted tool.
A merely declared hash is labeled unverified. A receiving Worker checks relevant
version/interface assumptions rather than treating a path as proof of correctness.
New revisions should use new output locations; artifacts under review are not
modified intentionally. Directory ownership remains a coordination convention,
not a sandbox against a Worker with shell access.

Example, not a required pipeline:

1. The Leader assigns A to prepare observations, and B to independently inspect
   a second source and establish its units. Output locations are disjoint.
2. A asks B which join key its source actually exposes. B replies directly with
   observed evidence. A does not need the Leader to relay this exchange.
3. B finds a unit conflict and sends a risk message to A. The same message reaches
   the Leader automatically. A reports a blocker if this prevents valid output.
4. The Leader decides whether the interpretation or task interfaces must change,
   updates task revisions and sends the decision to affected members.
5. Workers deliver artifact references, actual checks and unresolved assumptions.
   The Leader accepts or requests revisions; ready dependent work can then start.
6. A Worker integrates and runs the final pipeline. The Leader reviews evidence,
   completes the shutdown handshake and submits the chosen result.

This permits useful local negotiation while leaving global decisions attributable.
Reviewers are not mandatory. When an independent check is assigned, label whether
candidate conclusions were available or communicated; independent context alone
does not establish an independent method or unbiased verification.

## 7. Budgets And Termination

Preserve shared model/domain-tool/time accounting, charged failed provider
attempts, report reservations, fatal key/balance stop and no paid retries.
Do not increase the experiment's model budget just because messaging was added.
Model ceilings count all Leader, Worker, reporting and mail-handling calls.
Per-member tool usage persists across assignment changes and resumptions.

Messaging/control actions have explicit counters and limits, separate from domain
actions; calling them unbudgeted must not imply unlimited use. Initial engineering
defaults for offline testing are eight member identities, four concurrent Workers,
sixteen total Worker activations, 128 explicit sends/reports and an 8192-byte UTF-8
limit per explicit message. These are ceilings, not activity targets or validated
optimal settings. Model, domain-tool, execution-time and audit-time ceilings remain
explicit run configuration. Every limit and wakeup rule is frozen in the manifest.

Oversized or over-quota sends are rejected visibly, with no silent clipping or
automatic paid rewrite. Runtime-generated lifecycle notices and terminal reports
use a separate control path bounded by admitted work; explicit progress/risk
messages cannot bypass the quota. A terminal natural-language reply is retained
verbatim under the provider output limit, rather than clipped to the message cap.
Queue exhaustion and denied communication remain part of the attempt's evidence.

An accepted Worker activation reserves its final report inside the shared model
ceiling; an activation offered useful execution must have at least one work call
as well as that report capacity. Waiting retains its existing reservation.
Worker completion/failure releases unused reservations. The Leader's final call
is protected throughout. When ordinary model capacity runs out, the runtime enters
draining before allowing the Leader to spend its final reservation: otherwise the
Leader could submit while reserved Worker reports are still outstanding.

Normal termination uses a barrier, not the Leader's first final-looking sentence:

1. The Leader requests `finish_team`, identifying accepted artifact revisions and
   dispositions for unfinished tasks, outstanding requests and unread peer mail.
   It may finish with explicitly unresolved work, but not silently discard it.
2. The runtime changes from open to draining. New assignments, peer-triggered
   activations, ordinary peer sends and new domain actions are refused. Admitted
   work drains; Workers get a reserved final-report opportunity when feasible.
3. Late results, risks, errors and artifact changes are collected. Every queued
   message ends with an explicit delivery or undelivered disposition. Control
   reports remain allowed; no further coordination loop is silently started.
4. Once model/tool work has drained, final artifact hashes and the team-state
   revision are frozen. The Leader receives the closing state before its final
   submission. A late change to a selected artifact is exposed, not accepted as
   matching a previously checked version.
5. The adapter binds submission to the exact final artifacts. It records whether
   submitted code matches the executed/checked revision; copying or modifying
   code during final response construction is not silently credited as tested.

`finish_team` is a sole-call yielding control operation. Once draining begins,
V1 does not reopen the team; new defects are reported as unresolved. Automatic
budget-driven draining records the unresolved items even without a Leader closing
decision. No reservation guarantees a report after context overflow, deadline or
provider failure. Fatal key/balance errors stop further calls, including closing
calls; already-admitted work is drained without invented summaries. Cooperative
timeouts are not an OS-level kill or rollback.

Submission validity, team quiescence, unresolved work, infrastructure impact and
external task correctness remain separate output fields. A valid submission can
contain incomplete work. Leader acceptance and a clean shutdown are not scores.

## 8. Trace And Research Evidence

Retain full explicit communication, task-board changes, exact model inputs and
execution receipts. Do not inject the entire audit log into any agent's context.
The runtime emits identifiable events for:

- Member creation, activation cause, ready/wait/wake/idle transitions and limits.
- Task creation/revision, ownership changes, dependency decisions and acceptance
  of an exact result version, including rejected stale updates.
- Message attempts, acceptance/rejection, sender/recipient, content, task/reply
  links, inbox insertion and closing disposition; Leader copies link to originals.
- Inbox batches appended to a context and the precise subsequent model-attempt
  input that contains them. Local capacity rejection is not a provider exposure.
- Artifact references, verified/declarative hashes, tool receipts, provider
  attempts/errors, submission and shutdown state.

Keep model-visible local IDs separate from trace clocks/timestamps. Exactly-once
context insertion is checked per recipient/message within the live process.
Receipt of a message means it was included in a request, not that the model
understood, agreed with or used it. Reply, request resolution, task acceptance and
external validation are different events.

The explicit message channel can be completely logged. Shared files and arbitrary
shell operations are additional information paths; existing workspace snapshots
do not capture every read or establish exclusive authorship. Record available
artifact/tool provenance and unknown channels. Do not call the explicit-message
graph a complete information-flow graph or infer semantic causality from timing.

Useful diagnostics are delegation/execution distribution, Leader coordination
cost, task overlap, clarification and blocking time, stale references, conflicting
claims, unresolved requests, risk-notification delays, repeated unsupported
assumptions and communication that changes an artifact or decision. Distinguish
intentional independent checks from wasted duplicate execution. Message counts,
agreement and communication density are not quality metrics by themselves.

Report prompt lengths, token-weighted cache reuse by role, known and unknown
usage, estimated versus attributable actual cost, latency and independent outcome.
Diagnostic labels should be evidence-backed; no retired P1-P4 criteria or paid
semantic judge is implicitly reintroduced.

## 9. Implementation Boundaries And Verification

| Area | Proposed change |
|---|---|
| `harness/team.py` (new) | Leader authority, member/task state, asynchronous activation and draining lifecycle |
| `harness/messaging.py` (new) | Message validation, inboxes, request linkage, key-event routing and transport receipts |
| `harness/agent.py` | Expose a safe turn/yield boundary while reusing the same model/tool loop, history, validation and failure handling |
| Shared budget/accounting/trace | Activation reservations, communication counters, exact inbox exposure and shutdown receipts |
| Adapters | Fixed capability grants, artifact/submission binding and domain evaluation, not scheduling |
| `analysis/` | General trace readers and measurable team diagnostics, not study-specific success criteria |

Candidate model-facing controls are `spawn_worker`, `assign_task`, `update_task`,
`send_message`, `report_status`, `resolve_request`, `get_team_state`,
`read_messages`, `wait_event` and `finish_team`, plus the adapter's submission
tool. Spawn/assignment returns handles, never waits for the whole task.
Leader-only controls cannot be invoked
by Workers. `report_status` changes only the caller's assignment; blocking reports
yield. An execution assignment's ordinary final reply generates its handoff;
clarification-only activations follow the separate request rules above.
Status-changing yielding controls must run as sole calls to avoid continuing
execution after a reported handoff. Final API schemas are an implementation step.

Do not maintain a separate copied LLM engine for teams. Preserve existing
`single` and `mas` semantics; add an explicitly versioned `team` configuration
rather than silently changing what old manifests mean. The current comparison
factory grants all domain tools to both roots; the new protocol must instead
record the common team-wide capability ceiling and different per-role grants.
Single keeps the same overall domain capability, without coordination tools.

Required server-only scripted checks before any paid experiment:

1. A peer message reaches a running or waiting Worker before other long tasks
   finish, and the Leader is not trapped behind the old batch barrier.
2. No concurrent mutation/calls on one member; inbox delivery never splits an
   assistant tool-call/result sequence; every input reconstructs from trace.
3. Direct request/reply, concurrent sends, coalesced wakeups, idle clarification,
   invalid recipients, stale revisions and rejected quota/permission operations.
4. Risk/milestone copying, ordinary-message non-broadcast, result/failure notices,
   and explicit separation of queued, context-inserted and provider-exposed mail.
5. Wait-slot release, dependency waits, cycles, timeouts, exhaustion and fatal
   stops, including full pools and missing replies. No busy-poll model calls.
6. Assignment fencing and already-running writes, partial handoffs, task/result
   version checks, peer attempts to reassign work and expired owners.
7. Shared reservations under parallel load; no uncharged mail-handling, summary
   or retry calls; final barriers with pending messages, tools and late artifacts.
8. Existing Single/foreground regressions and adapter-specific fixture runs.
   Scripted fixtures do not establish real-model coordination or performance.

Inspect server processes/CPU ownership first. Sync, deployment and new runs remain
subject to authorization; this design change authorizes none of them.

## 10. Benchmark Questions After Implementation

First compare Single, Leader with one execution Worker, and the adaptive team.
This separates a coordinator wrapper from actual multi-Worker division of work,
without presuming that more Workers are better. Use the same model settings,
task inputs, overall capability ceiling and frozen shared budgets, with fresh
workspaces and independent evaluation. Equal call ceilings are not equal compute.

To investigate communication, compare direct peer messaging with Leader-mediated
messaging on the SAME new scheduler, task rules, templates, artifact visibility
and budget policy. Comparing the old foreground system with the new asynchronous
team instead measures a bundled system change. Shared files remain a communication
channel in both conditions; a disabled peer API is not a no-information condition.

Freeze development and held-out task sets and evaluator coverage before claims.
The previously inspected archeology case remains diagnostic, not held-out evidence.
Retain unsuccessful and infrastructure-affected attempts. Hypotheses include better
interface repair through peer dialogue, lower Leader relay burden, and conversely
more shared false assumptions, stale decisions or communication overhead. Failure
analysis should determine which mechanism to change next; none of these effects
is established by the architecture itself.
