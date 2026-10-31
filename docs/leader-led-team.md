# Fixed Agent Team Architecture

Current lite100 changes supersede the older lifecycle details below: see
[Fresh Lite Study](lite100-20261030.md). Worker idle replies notify the leader;
mutating domain tools automatically reopen, and explicit source patch transfers
avoid model-mediated copying. Submission remains explicit and immutable.

Fixed capability templates and permission profiles define the pool. Member
identity is distinct from template, so multiple members may share coder. A once-only
Leader plan selects members and assignments for each task; this is not RSI.
Workers have separate append-only contexts and may message any selected peer.
They do not inherit the Leader conversation. The Leader has no domain tools.

## Execution

AgentTeam defaults to async: a dedicated executor can run one model/tool turn per
member concurrently. Shared-state locks cover mailbox, grants and reservations,
not network calls or domain execution. No recursive teammate calls occur.
Only the owning turn appends to its context. Immediate mailbox messages are
consumed at the next input boundary, never injected into an in-flight request.

Task creation activates every member, including the leader, under the pinned
all-members-ready-v1 startup contract. The leader can ask questions and coordinate
before any worker report; it receives no private feature text or worker history.
This is initial eligibility, not a forced communication policy. After yielding,
normal message/status/finalization events wake it; there is no idle polling.

The coordinator wakes runnable/mailbox-ready members on events, detects global
quiescence and joins in-flight work before finalization or trace closure.
Provider calls cannot be forcibly canceled; shutdown waits for configured
provider/tool timeouts. Already running domain operations are not rolled back.
Provider failures take precedence over resource-limit finalization.

A controlled deterministic serial scheduler remains a fixed research control.
CooperBench drivers now default to async for the free-collaboration pilot;
controlled execution is retained only as an explicit diagnostic setting.
The manifest/control digest pins the choice. No policy may alter it. Model,
domain-tool, message and read quotas are per member, not a shared pool.

## Completion and Scope

Agent lifecycle, versioned task submission and verification are distinct.
Normal finalization requires frozen worker submissions, no active/runnable worker
and no queued content/status event. A received message wakes a submitted worker
without reopening it; trusted read-only checks remain available, while writes
and shell execution require explicit reopening. Budget
finalization can produce an incomplete submission set, never implicit success.
Both schedulers retry a deferred final when the last submitted worker becomes
idle. Agent-caused incomplete runs count as failures and retain terminal artifacts.
Container setup, immutable code capture, protected tests and patch merging belong
to the adapter. Runtime controls state transitions; Information Harness policy
guides sender content, never rewrites transport or declares completion.

Shared leader responsibilities, context-capacity checks, output retention and
pagination are implemented in harness/, without repository names, feature IDs or
coding-specific coordination strategies. Adapters supply domain capabilities,
private assignments, public acceptance rules, submission capture and independent
verification. Coding is one adapter, not a special branch in Team behavior.

See completion-protocol.md, information-harness.md and information-feedback.md.
The evolution target is not predetermined: observed collaboration failures will
guide candidate Harness changes. Architecture, isolation, scheduler and evaluator
stay fixed within a comparison. No real-model efficacy is assumed.
