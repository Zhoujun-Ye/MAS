# Archived Leader-Subagent Design

Historical foreground baseline, snapshotted at commit `f9c9a4a`. Its implementation
was removed at the user's request. The active runtime is the
[Leader-led Agent Team](agent-team-design.md). The semantics and commands below
describe archived evidence only, not the current runtime.

## Task And Context Contract

The leader sees the original task, works with authorized domain tools and delegates
bounded subtasks to fixed templates. A child receives only its template, common
reporting instructions, static limits, shared project instructions and the leader's
local task/context. The original task and parent conversation are never automatically
injected. There is no fork, recursive delegation or peer messaging. A leader can
explicitly quote relevant task information in the brief. Shared files can contain
additional information; this is context separation, not strict information secrecy.

Tools are allowlisted at dispatch. A template cannot expand its grants through a
brief or resume. Both leader and child grants must be registered within the session's
explicit capability ceiling. Shell access is not a read-only permission or OS sandbox.
Adapters remain responsible for path, network and secret restrictions.

## Scoped Delegation

The generic leader prompt treats children as owners of substantive exploration,
implementation, calculation or repair, as well as optional independent checks.
Before implementing the whole task, the leader identifies bounded deliverables and
dependencies. When useful, it delegates early after minimal orientation, not after
doing all production work itself. Each deliverable has one owner, root or child.
Small or tightly coupled tasks may remain direct work; no delegation quota applies.

Local briefs identify objectives, evidence paths and versions, checked scope,
unverified assumptions, acceptance criteria, exclusions, prerequisites, deliverables
and write ownership. Independent ready work is batched together; dependent work
waits for its input artifacts. The foreground leader cannot work during the batch.
It integrates produced artifacts instead of automatically rewriting or replaying
each child workflow. Producers validate their own work; an extra reviewer addresses
a named risk, uncertainty or requested assurance, not a mandatory post-work panel.
Intentional overlap must have a verification purpose. The leader may recompute for
gaps, contradictions, stale inputs or changed artifacts.

Execution children implement, run and validate their assigned deliverables, rather
than merely recommending what the leader should build. Children reuse supplied
locations without treating supplied claims as proof. They
may re-read raw sources and recompute for an independent check, and expand discovery
when the supplied sources are inadequate. Follow-ups resume the existing context
and target new questions or changed evidence rather than restarting a full survey.

These are fixed prompts, not runtime deduplication, mandatory phases, automatic
evidence sharing, or prohibitions on repeated tool calls. The Single root has no
delegation policy added. Grants, budgets, scheduling and reporting are unchanged.
Benchmark-specific production capabilities, source inventories and checks belong in the
adapter prompts. Scripted tests check transport and allowed workflows, not whether
real models actually reduce duplication or cost.

This distinction follows the public capability designs: [Claude Code's general-purpose
subagent](https://code.claude.com/docs/en/sub-agents#built-in-subagents) supports
exploration and code modification, while [Codex's worker](https://learn.chatgpt.com/docs/agent-configuration/subagents)
is execution-focused, alongside an explorer and general-purpose fallback. Neither
design restricts subagents to post-hoc review. Our fixed tools, brief-only contexts,
foreground scheduling and no-fork policy remain deliberate experimental choices,
not an exact implementation of either product. Prompt changes alone do not establish
a latency or cost improvement.

## Final-Message Summary Baseline

Every child receives the same fixed `CHILD_REPORT_POLICY` in its initial system
prompt and its final-call reminder. The child writes a concise natural-language
summary as its normal final reply. There are no required section headings or
numeric length targets. Relevant evidence references, material failures, uncertainty
and unfinished work remain requested. Resume reports emphasize changes and current
unresolved items rather than repeating the previous report.

When granted storage tools and an assigned path, children save detailed tables,
logs and reproducible artifacts during work and cite their locations in the reply.
Read-only children cite existing sources or accessible output IDs; the policy does
not grant writing or invent saved artifacts. Unsaved detail is disclosed, especially
when the last model call has tools disabled. Leaders inspect referenced detail only
as needed, not automatically.

The runtime still returns the child's final text verbatim in `report`, with the
existing identity/lifecycle metadata. There is no length validator, truncation,
history rewrite, automatic file write, summary model call or extra retry. An overlong
reply is retained unchanged, including in the leader's tool result and trace. Full
child reasoning and tool history stay in the child context and trace for resume;
they are not automatically copied into the leader context. The root's final-answer
contract is unchanged.

### Baseline Provenance And Alternatives

[Claude Code](https://code.claude.com/docs/en/sub-agents) describes returning a
summary from an independent child context; [Codex documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)
recommends summaries instead of raw intermediate output. These public descriptions
do not establish every internal model call, nor prescribe our previous four-part
format. This is a mainstream-style return mechanism, not a full product replica.

The [AutoGen paper](https://arxiv.org/abs/2308.08155) provides a related multi-agent
framework. Its later [v0.2.35 implementation](https://github.com/microsoft/autogen/blob/v0.2.35/autogen/agentchat/conversable_agent.py)
explicitly distinguishes `last_msg` (the default, takes the final message without
an inference) from `reflection_with_llm` (calls a model over chat history with a
summary prompt). Our return path follows the former mechanism, but preserves text
verbatim rather than stripping AutoGen's termination marker. This is not a claim
that the 2023 paper evaluated our configuration or this later API.

Potential ablations, not additional implemented modes: a separate history summarizer
with all its calls/tokens/time charged to the shared budget; or a frozen structured
summary with artifact references and on-demand detail retrieval. The latter is a
project-specific enhancement, not an established paper baseline. Final-message
summaries can omit evidence or uncertainty, and verbosity remains model-dependent;
those failures must remain observable rather than being silently repaired.

[Magentic-One, Section 4.1](https://arxiv.org/html/2411.04468v1) is a useful separate
system baseline, but its task/progress ledgers and replanning context resets change
orchestration and memory, not just report compression. Do not label a summarizer
swap as a reproduction of that system. Existing scoped-delegation prompts, tool
grants and artifact conventions are held fixed in this summary-only change.

## Parallel Scheduling And Resume

The delegate arguments are template, task, optional context and optional resume_id.
Multiple delegate calls in one leader response execute in a bounded pool, default
max_parallel=4. Results enter the leader transcript in original call order after the
batch drains. This is parallel foreground delegation, not background spawn/poll:
the leader waits for the batch before its next model call. In mixed batches,
contiguous explicitly concurrency-safe calls form a parallel group. Each other call
is a serial barrier: preceding groups drain before it runs, and following groups
start only afterward. Results remain in provider call order.

New-child allocation and delegation counters are locked. A child marked running
cannot be resumed concurrently. Completed or partial children retain their transcript,
fixed tools and lifetime tool allowance on resume. Invalid/empty/unknown IDs never
create replacements. Provider/context/execution-failed children cannot resume.

Child IDs are assigned in provider call order before worker dispatch, not in thread
arrival order. Rejected requests can leave ID gaps. Shared-budget/admission allocation
among concurrent requests can still vary with scheduling. Every admitted invocation
has an invocation ID and call ID in start/end events and returned reports; audit
intervals use that same invocation ID. Completion is published under the session
lock after the end event, so resume cannot race ahead of its predecessor's end record.
No barrier creates a frozen common workspace. Concurrent
writers can conflict: the leader should assign non-overlapping work, and adapters
may provide stronger conflict handling. No worktrees or conflict merge are implicit.

## Budgets And Reporting

Default session ceilings are 40 model requests and 80 budgeted domain-tool calls,
shared atomically by leader and all children, including resumes. One request is
reserved for the leader's final answer in both arms; children cannot spend it. When
accepting each delegation (including resume), the runtime also reserves one request
for that invocation's report. Admission is rejected visibly if no unreserved request
is available. When unreserved requests run out, an agent spends its own reservation
on a forced final report. Unused reservations are released on completion or failure;
resumes acquire a fresh reservation without resetting lifetime tools or history.
Reservations are inside, never added to, the same ceiling. Per-child maxima are
ceilings, not guaranteed allocations: four
20-turn children are not promised 80 calls from a 40-call session. Requests are charged
before provider execution, including requests that fail; rejected local capacity
checks do not spend a request. Invalid/denied tool requests do not spend tool budget.
Final-mode selection and local capacity preflight run under the same budget lock.
Any shared-budget final notice is appended before capacity is checked; only a
successful preflight consumes a request or its report reservation. A rejected
preflight leaves the notice in append-only history, emits no provider attempt and
records context_length outside the budget lock. Normal session cleanup releases
the unused reservation. Execution time is checked again after preflight before
admission. Provider failures after admission remain charged, without retries.
The estimator remains conservative, not an exact tokenizer: it includes the fixed
tool catalog even when a final submit-only request advertises a subset. Capacity
events log the checked context length and final-call reason.
Per-agent lifetime tool budgets and per-invocation turn limits remain additional
ceilings. A tool must explicitly declare budgeted=True to count as a domain action.
Local and shared tool-budget denial messages identify their respective scope.
No hidden retry/recovery call or reasoning-effort change is made. retries defaults to 0.

Limits are visible from the start. The last invocation call receives a fixed final
report instruction and tool_choice=none, within the existing call limit, except for
roots configured with a submission tool (see below). Disallowed tool calls are
refused with the actual final-call reason and actual number of turns. A one-call
child invocation is report-only. A sibling cannot spend another child's reserved
report call, but a deadline, fatal error, context overflow or provider failure can
still prevent a report. There is no call beyond the ceiling and no report invented
from observations.

Every delegation result includes a trailing `usage` object: this invocation's model
attempts, tool dispatch attempts and charged domain tools, plus shared remaining
model/tool calls and reserved/unreserved model calls. Counts on resume are deltas,
not lifetime totals. Shared counts are concurrent snapshots, not promised allocations.
Rejections return zero invocation usage and the same shared snapshot. No timestamps
or usage updates are inserted into the static prompt prefix.

`budget.limit_events` records encountered invocation/shared call, domain-tool, time,
context and output limits; reports retain each invocation's termination reason.
Equal request ceilings are NOT token, cost or compute matching. Known token receipts,
cache reuse and costs must be reported alongside results. An optional aggregate token
ceiling is not implemented in this revision: parallel in-flight token reservations
and protected final-report capacity need a separately frozen admission policy;
a post-receipt cutoff would neither be a hard cap nor protect pending summaries.

## Lifecycle Is Not Correctness

Child outcome describes this invocation: done, length, turn_limit, empty_report or
session_model_limit. Submission roots also distinguish submission_missing and
submission_invalid. Errors and budget denials remain in tool_events/trace but do
not permanently change later reports to partial. A normal final report can follow
a corrected argument error, permission denial or unsuccessful command.

Session status is done when the leader returns a final report, otherwise incomplete.
It is NOT a verdict on the task or on every delegated attempt. Returned fields include
leader_status, child_statuses, all reports, rejected delegation requests, errors,
tool_events, budget counters and infra_affected. Historical failures are retained even
when lifecycle status is done. An evaluator must bind task success to actual artifacts.
Never use lifecycle status alone as a benchmark score or drop failed attempts.

Non-context provider errors mark infra_affected even if the leader continues and
returns a final answer. Context overflow, ordinary nonzero commands, invalid arguments
and permission denials are not provider failures. Execution transport failures and
audit failures also mark infrastructure impact. Key/balance errors stop new requests
and tool dispatch. All tools, including unbudgeted tools, pass a common dispatch
admission gate after preflight. Admission is the linearization point: already-admitted
work is in flight and cannot be recalled. Siblings stopped by the fatal gate receive
stopped_after_fatal, not provider_error; only actual failed provider requests count
as provider failures. The pool drains
before an exception escapes with session_outcome and a session_end trace record.

A session_seconds ceiling defaults to 900 seconds of execution time. Once expired,
new model/tool dispatch stops and late model replies are marked session_time_limit.
The built-in HTTP client and container operations receive remaining-time timeout
caps. Built-in audits accept the remaining timeout; audit starts after expiry are
recorded as skipped, not successful. This is a cooperative deadline, not an OS-level
kill: HTTP phase timeouts, process cleanup and already-running third-party callbacks
may overrun it. Custom clients/tools/audit hooks must enforce their own cancellation
or bounded timeout; no thread is force-killed and no in-flight work is abandoned.

Audit-only wall intervals are excluded from execution time. The budget tracks the
union of active audits and model/domain-tool activity across threads: overlapping
audits are not double-subtracted, and an audit overlapping a running model/tool does
not pause that execution's clock. Orchestration time outside audits still counts.
Audits have their own 120-second shared allowance (`audit_seconds`). Audit exhaustion
or overrun marks infrastructure impact and skips subsequent snapshots instead of
silently stealing the root's final call. Budget snapshots report wall, execution,
audit-wall and excluded-audit seconds. Trusted custom callbacks must still honor
their timeout; the harness cannot kill an arbitrary Python callback.

## Workspace Audit

Pass workspace_audit=GitWorkspaceAudit(path) for a host-owned Git workspace, or
workspace_audit=container.audit_snapshot for an already-provisioned ContainerWorkspace.
The latter needs git/python3 inside the container. Audit output uses a trusted full
capture path independent of the 30 KB model-visible tool-output limit and never
changes that limit on the shared adapter. No container is provisioned. Before/after snapshots run for each admitted
delegation and resume, including failure paths. Without a hook, enabled=false is
recorded; no audit coverage is claimed.

Both modes also capture `session_workspace_snapshot` before and after the root
run, including the provider-failure path. This covers direct root-agent writes even
when no delegation occurs. Session audit failures set the same `infra_affected`
flag; snapshots remain trace-only and do not add model calls.

Real adapters resolve input, work, output and raw-output archive paths before model
dispatch. Evidence paths cannot overlap either model-visible mount, including via
symlinks. This precedes creation of the trace: a read-only Docker bind does not stop
the host from writing logs into the input lake. Retained-output namespaces must start
empty. Docker mount metadata is canonicalized by destination before comparing snapshots.

## Request And Failure Accounting

Each admitted provider attempt emits `llm_attempt`, followed by `llm_call` with a
receipt or `llm_error` without one. `usage_summary.llm_calls` counts attempts, with
additional attempted/succeeded/failed/unknown-usage counts. Old success-only traces
remain readable; missing historical attempts are not invented. Token/cache totals
cover known receipts. Unknown usage is not zero usage: total estimated cost is
unknown if receipts are missing; a separate known-usage estimate is available.
Zero-token scripted calls no longer imply cache hits.

Accepted benchmark attempts write terminal reports even for provider errors,
invalid final JSON or incomplete execution, then re-raise the original exception.
They do not invent submissions or verdicts. Invalid preflight placement is rejected
before creating an attempt directory, without model calls. Fatal key/balance errors
stop subsequent model calls, including the other arm of a paid pair.

Adapters can supply an unbudgeted, serial root-only `submission_tool` and a fixed
`leader_final_prompt`. Successful schema-validated submission ends the loop without
another completion. Invalid arguments return ordinary visible tool errors; correction
uses another already-budgeted turn. Plain text is not accepted as a submission: an
explicit reminder continues the loop within the same ceiling. A submission must be
the only call in its reply; mixed submissions execute nothing. The last reserved
root call advertises only the submission tool and does not enable domain actions.
Missing/invalid final submissions are incomplete, without an extra repair request.
The adapter owns the schema and serialization; the runtime owns termination.

KramaBench does not use `response_format` on any call. Generic opt-in support remains
Agent-local, logged on `llm_attempt`, and never mutates the shared client. The final
submission tool is offered with automatic selection, not a forced named-function
parameter: [DeepSeek Chat Completions docs](https://api-docs.deepseek.com/api/create-chat-completion/)
explicitly reject `required` and named tool choices in thinking mode (HTTP 400).
The client also rejects those combinations locally. Runtime enforcement is not a
guarantee that a model will submit. No thinking-mode switch or paid probe is implicit.
Each attempt logs advertised tool names and final-call reason.

Child execution exceptions produce one identified failure report, not a second
anonymous rejected delegation. Fatal provider errors still stop the session.
Retired Agent arguments and notices are removed. `boundary_msg` is no longer a
special emitted event; its reader/validator compatibility is retained solely for
immutable historical peer-team evidence.

Snapshots include tracked/nonignored untracked file hashes, symlink-target hashes,
HEAD commit ID (or null for an unborn repository), symbolic HEAD, refs, Git status
entries and a hash of the diff against HEAD. Every audit Git command inherits
GIT_OPTIONAL_LOCKS=0 in both host/container paths to avoid optional index writes.
Ignored assets are excluded;
deleted files are represented. Only hashes and metadata, not diff contents, enter
trace. Audit data never enters model messages. An audit failure emits an audit error
and sets infra_affected rather than silently claiming an intact snapshot.

Snapshots are non-atomic. Concurrent modifications can occur during capture and
before/after intervals overlap: attribution is shared_interval_not_exclusive, NOT
proof that one child authored every change. File snapshots and diff hashes are audit
receipts, not a full patch archive or an external-process write attribution mechanism.

## Single-Agent Comparison

`harness/single_agent.py::SingleAgent` is the no-delegation specialization of the
same session implementation. It uses the identical `Agent` loop, schema validation,
tool execution, budget accounting, error handling and append-only history. It is
not a second independently maintained agent engine. Standalone SingleAgent grants
all supplied domain tools by default; an explicit `domain_tools` ceiling can narrow
that set. It cannot register the reserved delegate tool or create child contexts.

Full context means the original public task, shared project instructions, and all
of this agent's own assistant/reasoning/tool messages, without summarization or
trimming. It does not mean automatic ingestion of every dataset file, benchmark
answers, hidden evaluator data, or transcripts from a different MAS run. Data is
retrieved with tools as in MAS. Provider context overflow is still incomplete work;
there is no invisible compaction, overflow fallback or extra recovery call.

`comparison_session(..., mode="single"/"mas", domain_tools=...)` explicitly gives
both arms the same approved domain tools, base leader instructions, model settings
and session ceilings. The delegated arm adds delegation instructions, template catalog,
limits and the delegate tool. The leader-only arm has no empty catalog or delegation
instructions. The underlying constructor remains deny-by-default for leader tools;
it never silently grants all registered capabilities.

Legacy `delegated=False/True` maps to these modes; contradictory options are rejected.
The comparison factory makes root invocation/tool limits default to the shared
session ceilings, and rejects smaller explicit root limits that would prevent the
single context from using the declared total budget. The normal LeaderSubagent API
still permits smaller per-agent limits for other non-comparison settings.

Trace `mode` and `context_mode` distinguish the conditions. For compatibility,
the sole root remains named `leader` and result fields retain `leader_status`;
`usage_role="single"` identifies single-agent token/cache accounting. Its effective
child/delegation/parallel-child limits are zero. A forged delegate call is rejected
and retained in error history, not silently discarded.

Equal request/tool ceilings are not equal FLOPs, latency or token cost. Report actual
tokens, cache reuse, cost and latency as well as ceilings. Freeze model, price source,
budgets, templates, prompts and adapter revision before any authorized experiment;
this change does not select a benchmark, invent current prices or authorize paid runs.

For a real pair, use separate fresh workspaces, output archives, clients/sessions
and histories, with identical read-only input contents. Freeze task/input hashes,
model parameters, common prompt, tools, budgets, source, evaluation and prices.
Record run order and cache warmup policy; the provider's shared cache can affect
sequential comparisons. Evaluate both final artifacts independently and retain
incomplete/infra-affected attempts. This contrast measures full system configurations
(decomposition, specialist prompts, context distribution and concurrency), not the
causal effect of context separation alone.

`harness/comparison.py::validate_pair` checks task, model, tools, shared prompts,
budgets, prices, source, image, input hashes and resource limits. It rejects reused
container IDs, overlapping workspaces/evidence roots and preexisting output paths.
Each arm revalidates its environment against the frozen record immediately before
running. Container provisioning and task selection require explicit authorization.

## Verification

Server-only scripted tests cover concurrent execution, shared-budget races, duplicate
resume rejection, fatal-error draining, local briefs, report prompts, error-history
retention without poisoned status, infrastructure markers, comparison grants and Git
snapshot changes. Docker audit integration and real-model performance remain separate
validation gates; no empirical superiority follows from these wiring tests.
