# Fixed Agent Pool and Task-Adaptive Team: Design Contract

Status: the minimal peer runtime and fixed pool are implemented and tested with
scripted clients; real-model behavior and policy evolution are not verified.

Decision: reusable capability templates -> task-adaptive selection -> independent
team execution -> communication-policy feedback and optional cross-task update.
Team architecture search and role evolution are explicitly out of scope.

## Current implementation

| Capability | `harness/team.py` | `harness/fixed_plan.py` |
| --- | --- | --- |
| Leader splits tasks | Dynamic dispatch | Separate planner creates linear stages |
| Independent persistent contexts | Yes | Yes |
| Worker sends directly to another worker | No | No |
| Peer inbox, wake-up and conflict/response protocol | No | No |
| Leader coordinates and synthesizes final answer | Via synchronous reports | No, final worker answers |
| Frozen organization across five conditions | No | Yes, but only a linear pipeline |

These legacy modules were removed during cleanup; the table is historical.
The replacement is `harness/agent_team.py`:
queued peer delivery, persistent contexts, round-robin wake-up, leader synthesis,
five boundary encodings and per-recipient evidence ACLs. `harness/pool.py` supplies
immutable selections and capability bindings. The graph is all selected peers;
Leader decomposition and frozen-plan persistence are generic in `harness/planning.py`.
Leader has no domain tools; the runtime rejects attempts to grant them.
The Information Harness mediates private evidence, artifacts, memory and state
through a versioned, authorized workspace. See [hard boundaries](information-harness.md).
TravelPlanner is retired. Richer executable dependency graphs remain future work.

## Three separate layers

| Layer | Responsibility | Research status |
| --- | --- | --- |
| Agent Pool | Versioned capability templates, system prompts, permission profiles and protocol | Fixed infrastructure |
| Team Composition | Select existing members and assign concrete task work | Task-adaptive infrastructure, not evolved |
| Information Exchange | Decide what/when/to whom to send, request/read, correct and deduplicate | Main research object; updates evaluated separately |

The Meta-Agent is a selection/planning function, not necessarily another paid
LLM instance. Leader is the runtime coordinator. In a multi-agent task, one
bounded leader initialization call can implement selection and assignment; do
not stack separate router, planner and leader calls without a demonstrated need.

## Reusable pool

Worker templates include Researcher, Solver, Coder and Reviewer. Treat their
names as broad capabilities, not narrow domain identities. A Coder may work on
SQL or Python; a Reviewer may apply task-specific audit criteria. Selection must
not invent a DatabaseExpert system prompt for one task or grant Coder permissions
to Reviewer because a task appears difficult.

| Template | Stable capability | Permission intent, bound before a study |
| --- | --- | --- |
| Researcher | Retrieve, inspect and compare information with provenance | Approved search/read tools |
| Solver | Combine evidence, reason, calculate and resolve constraints | Approved reasoning/calculation tools; no implicit write permission |
| Coder | Implement and execute task-specific computation | Sandboxed code/tool execution; writes only within explicit scope |
| Reviewer | Independently check evidence, constraints and proposed results | Read/verification tools; no unrestricted corrective writes by default |
| DataAnalyst | Quantities, tables, comparisons and calculations | Read/search/compute |
| ConstraintAnalyst | Feasibility, budgets, dependencies and conflicting requirements | Read/search/compute |
| Executor | Carry out approved actions and report exact resulting state | Read/search/explicit execute capability |
| Synthesizer | Reconcile cross-source findings into supported conclusions | Read/search |
| Leader | Assign work, coordinate conflicts and synthesize | Team communication/control; no hidden access to worker contexts |

`bind_permissions` maps these capability profiles to actual adapter grants. An adapter binds
concrete executable tools to profiles once per versioned environment setup. Pool
records must pin template id/version, exact system prompt, capability description,
permission/tool-schema digest and base communication protocol. Changing a binding
creates a new pool/environment version, not a task-time permission edit. If the
fixed pool cannot cover a task, report unsupported or require a new version; do
not silently add a role or weaken the task.

For the initial design, select at most one worker instance per template within
a task. Leader is a fixed controller outside the selectable worker subset.
Report total active contexts honestly: two selected workers plus a leader are
three contexts. Reviewer is an executing team member, not the independent grader.

Task-specific domain requirements, acceptance criteria, dependencies and the
assignment belong in dynamic task input. They do not rewrite the template's
system prompt or tools. Reusable means templates and prefixes, NOT cross-task
conversation history. Each new task starts clean contexts; each selected member
keeps its own append-only context throughout that task.

## Selection and execution

Input: complete public task, permitted environment/tool catalogue, frozen pool
and resource limits. Never use future user turns, evaluator state, gold answers
or condition outcomes to choose a team. Output: a TeamSpec referencing existing
template ids, concrete assignments, dependencies, completion criteria, execution
mode, leader requirement and allowed peer graph. System prompts and permission
lists are resolved from the pool, not generated in the TeamSpec.

Support three routing baselines without conflating their gains with communication:

- Rule routing: deterministic public-input/capability checks; no LLM routing call.
- LLM routing: one explicitly budgeted selection/planning call, persisted once.
- Fixed team: one predeclared roster plus condition-blind task assignments.

Begin with the simplest applicable router. Cheap routing is not assumed accurate;
retain unsupported/misrouted cases for routing analysis. Do not silently fall back
from one router to another after a failure. Compare routing quality and total
cost in a SEPARATE experiment, not by changing router across handoff conditions.

Solo mode selects one worker that directly executes and answers. It need not
invoke a meta LLM, leader or automatic reviewer; do not silently turn every
one-worker request into a two-model-call team. Team mode selects multiple workers
and a coordinating leader that produces the final synthesis. Selection and
initial decomposition occur once, not per message. Reject infeasible initial
plans before observing condition outcomes.

For motivation, persist one condition-blind TeamSpec per task and reuse it across
all five communication forms. Different tasks MAY have different compositions.
The pool, model settings and routing policy are fixed across the study; within
each task, roster, assignments, permissions, dependencies, allowed graph and
budgets must match. A reviewed multi-agent subset is chosen before outcomes;
solo tasks belong to routing/cost evaluation, not fabricated handoff-loss cases.
All workers receive the full public goal and constraints. Runtime clarification
is allowed inside frozen responsibilities; roster/permission/role changes are not.

Freeze pool version/digest, environment/tool-schema digest, router version,
TeamSpec/public-task digest, model settings, graph/scheduler/budgets and the
communication-policy version in the manifest. Record selection usage once per
task. Validate artifacts before inference: missing/stale/invalid plans are
initialization failures, not reasons to replan one arm. Schema checks cannot
certify semantic division of labor.

Workers have independent append-only contexts and may address another worker or
the leader directly. Local findings are private until explicitly sent or read
through a permitted evidence mechanism. No unconditional global broadcast.

Use queued delivery, not recursive calls into another running agent. A send
acknowledges queuing, not peer completion. Deliver at tool-safe message boundaries;
serialize writes to each context; wake only agents with work/new messages. Record
queued, delivered and consumed states separately. Leader resolves conflicts,
requests bounded clarification and produces the final synthesis.

Keep a small predeclared team-size limit and bounded messages/coordination rounds.
Do not instantiate every pool member by default. No busy polling, recursive
delegation or one worker per tool call. The scheduler policy is fixed; actual
sends and tool trajectories may change because of the communication intervention.

Full Context exposes a selected SENDER snapshot at an explicit message boundary,
not the whole team's hidden history to everyone. Summary/Structured encode that
boundary; Retrieval/Adaptive allow declared evidence reads. Apply the mechanism
to peer and worker-leader edges alike. Count all materialized read tokens; a
dangling reference is not full-context delivery. Compare five communication
policies, not five different organizations.

## Communication-policy boundary

`PoolSpec` defines who agents are; `TeamSpec(x)` defines who works on task x and
their responsibilities; `CommunicationPolicy(version)` defines how they exchange
information. See [communication policy and evolution](communication-policy.md).

Do not import Blueprint evolution or team architecture search into this study.
Blueprints can remain a separate organization-level project; capability templates
are not a new name for Blueprints. A task-specific TeamSpec is not a learned
policy update. Only reusable communication policy versions are candidates for
feedback-driven updates here, and only after the motivation study supports them.

## Motivation and attribution

Separate information asymmetry (someone knows a needed fact), insufficient
sharing (not sent), transmission loss (omitted/distorted/inaccessible), and
coordination failure (stale/conflicting findings, duplicate work, unmet
dependencies or wrong decisions despite available information). A missing
citation or failed task does not distinguish these mechanisms.

Semantic fact/qualifier checks need original observations and actual recipient
decision-time contexts, including read evidence. Causal claims need frozen-point
repeats, supported missing-fact supplementation and a matched control. The
five-arm end-to-end test alone measures a broader communication-policy effect.

## Cache-aware engineering

- Stable system/role/tool-schema prefixes. Sort schemas once and enforce
  budgets outside the model, rather than changing tool inventories each round.
- Append inbox deliveries, tool outputs and instructions at the tail. Do not
  rebuild prefixes from timestamps, random trace ids, mutable dashboards or
  budget counters. Preserve reasoning_content verbatim.
- Persist worker contexts. Generate/reuse the plan once, not once per arm or
  after every message. Avoid automatic summarization after every tool action.
- Order context as stable role/protocol and tool definitions, then a versioned
  communication-policy block, then task/assignment, then append-only execution
  and inbox events. Task text is not a cross-task stable prefix. Policy changes
  must not rewrite the shared role prefix; their cache impact is still measured.
- Generate compressed messages on context copies, not by altering sender
  execution state. Charge encoding calls and cold starts as well as readbacks.
- Share common prefixes where natural, never extra hidden facts merely for cache
  reuse. Counterbalance arm order; do not always give the last arm warm caches.
- Use provider-reported token-weighted hit/miss telemetry per condition and
  leader/worker/handoff role, separating first and later calls. A high hit rate
  is not a success criterion or a substitute for a monetary budget.
- Cost forecasts need cold-cache/worst-case bounds and must include output/
  reasoning tokens, all repeated reads, planning, coordination, retries and
  judges. Bound calls/dollars/time, not only domain tool calls.

DeepSeek documents prefix matching as best-effort, not guaranteed:
https://api-docs.deepseek.com/guides/kv_cache/

Implemented now: stable role prompts, sorted schemas, immutable task selection,
append-only contexts, copy-based handoff encoders and explicit usage_role metadata
for each capability and handoff calls. Retrieval text is materialized into tool
responses and subsequent inputs. No real-model cache improvement is claimed.

## Implementation boundary

The small runtime deliberately uses `pool.py` and `agent_team.py`, not six new
abstractions. The offline driver persists TeamSpec and verifies identical control
digests for all five forms. Calls include encoders; domain calls, messages, reads
and input size are bounded. Full Context is never silently truncated.

Peer events record queued/encoded/delivered states and decision-time contexts;
they do not assert agreement or semantic consumption. Full Context can grow
rapidly with reciprocal messages; exceeding the size limit is incomplete, not
wrong. Compression can fail its schema and also ends incomplete. Future paid
entry points need monetary/latency guards, provider recovery integration and
explicit authorization; none is supplied here. The updater, causal replay and
semantic-arrival judge are not implemented by this change.
