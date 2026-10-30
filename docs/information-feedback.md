# Information Selection, Availability and Delay

Information-specific diagnosis uses a decision requiring a specific fact and
qualifiers, not merely a failed task or missing citation. The broader study also
examines coordination, misuse, delay and overhead (docs/experiment1.md). The current hypothesis is: even with timely delivery,
agents may choose the wrong content to send and cause collaboration failure.
This is not established by the runtime or offline tests.

## Operational Evidence

Every trace event has an ordered run-local t, UTC ts and monotonic_ns. Wall-clock
timestamps are for inspection; within-run latency uses the monotonic clock.
These fields never enter model prompts.

- evidence records the returned observation and source_tool_call_id.
- peer_queued records sending, recipient, exact text and explicit evidence IDs.
- peer_mailbox records immediate delivery to the recipient mailbox.
- peer_delivery records append to the recipient context at a safe boundary.
- model_input records the immutable input boundary before provider execution.
- peer_consumed links each newly included message to that request_id.
- llm_call records the returned completion and usage, with the same request_id.
- policy_message binds each accepted outgoing message to the frozen policy.
- task_status and agent_state describe operational changes, not discovered facts.
- submission_snapshot freezes a version for grading; it is not a message to the leader.

Consumed means included in an attempted model request, NOT read, understood,
accepted by the provider or used correctly. Failed requests remain provider
errors. A message arriving during a request cannot affect that request.
Provider retries use the same input. Request-start, not response-end, is the
decision cutoff. Never append to an in-flight context.

message_lifecycle exposes sender, receiver, message_id, source_tool_call_ids,
sent_at, delivered_at, consumed_at, request_id and monotonic durations.
Plural provenance permits multiple sources. Empty references mean unknown
provenance, not absence of relevant knowledge. A reference does not prove
semantic relevance; inspect exact tool output and sender input.

At each decision distinguish:
1. Not acquired: no reviewed supporting observation in the sender's earlier input.
2. Acquired but not selected: reviewed relevant content was available, but absent
   from what was sent. An empty message log alone cannot establish this.
3. Sent but unavailable: transport pending, mailbox waiting for the next step,
   or sent after this decision. Keep these timing cases out of selection-loss labels.
4. Included but not used correctly: requires semantic review of sufficiency/use.

Later lifecycle receipts remain visible, labelled relative to the chosen cutoff;
future evidence is excluded from decision-time context and source analysis.

## Controlled Motivation

Freeze pool, TeamSpec, tools/permissions, model, budgets, scheduler and transport.
The exploratory driver defaults to async, with autonomous when/whom/content.
Controlled serial execution is only an explicit diagnostic setting. Do not pool them or
let RSI change scheduling, architecture, assignments, permissions or budgets.
Candidate Harness mechanisms will be selected after observing failure modes.
No updater is implemented or authorized here.

Immediate mailbox delivery does not guarantee availability before an already
running decision. Primary selection-loss cases require reviewing all relevant
messages and ruling out timing, acquisition, environment and permission failures.
Report delayed/unknown cases separately, without silently dropping hard tasks.
Even this selection is descriptive, not causal proof: restoring a supported
missing fact must be compared at a frozen decision against unchanged-input
repeats and matched controls. Such replay and paid tests are not implemented.

Use scripts/feedback.py to export review packets. Keep semantic and causal
attribution unknown until independently reviewed. Code-test failure alone is
not evidence of information loss.

For CooperBench, packets default to all worker model-input boundaries, not the
leader's unevaluated final text. --agent and --call-t restrict the review target.
Both analysis and feedback read per-attempt manifest.json/result.json/trace.jsonl
directories. All started attempts remain visible; deadlock and resource-induced
incompleteness are agent failures. Terminal code tests are diagnostic and cannot
retroactively remove those failures. Infrastructure/unknown cases are separate.
