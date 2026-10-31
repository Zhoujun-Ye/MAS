# Communication Policy and Research Scope

The fresh lite100 setup is documented in [Fresh Lite Study](lite100-20261030.md).
It additionally forwards worker idle replies through the same message boundary
and offers explicitly granted, byte-exact source patch transfers. No strategy
or integration algorithm is imposed on agents.

Only direct-message Agent Team execution is supported. There is no encoder,
summary transport or alternative information channel. The current implementation
has a fixed neutral free-collaboration prompt; agents choose when, whom and what
to communicate. Policy learning and causal replay are not implemented.

## Fixed Runtime, Mutable Policy Artifact

Runtime fixes the team, domain permissions, allowed communication graph, tool
schemas, scheduler, budgets, lifecycle and submission/verification contract.
The benchmark fixes private tasks, workspaces, snapshots and evaluation.
Information Harness maintains invariant ACLs and the outgoing-message boundary.
These mechanisms are not update targets.

CommunicationPolicy contains only version and instructions. Its digest is part
of the run's control digest; instructions enter each sender's stable prompt.
A future updater may replace this artifact BETWEEN collection batches, not
during an episode. It cannot execute privileged hooks or change Runtime.

Within permitted opportunities, sender instructions may guide:
- Which locally available facts and qualifiers to share.
- Which allowed recipient needs them and how to express uncertainty.
- Which authorized references to attach or read.
- When to ask for missing information or send a correction rather than repeat.

These are agent decisions under a fixed event-driven execution mechanism, not
changes to scheduling, event triggers, task allocation or tool permissions.
Task-adaptive decisions are not themselves cross-task self-improvement.

## One Content Boundary

All substantive outgoing paths use InformationHarness.prepare_message:
send_message and explicit submit_assignment reports. Tool-free replies only yield.
It validates sender/recipient, text and reference permissions, then returns the
exact content. Runtime transports it unchanged. There is no additional model
call and no inspection of hidden teammate context. Semantic policy compliance
must be measured, not inferred from passing this structural validation.

Structured envelopes remain in the trace. Model-visible messages have a short
identity/reference header followed by the exact unescaped payload; newlines,
quotes and Unicode are preserved. There are no incoming_handoff, handoff_form
or context_id prompt fields. Free-form text is not
forced into a fact schema. No message kinds, semantic deduplication, supersession
graph or general task dependency system are implemented.

Automatic submission/status notifications use a fixed metadata whitelist.
They cannot carry summaries, patches, findings or free-text status explanations.
Substantive reports consume the same content-message budget as explicit sends.
References grant exact versions, not implicit reads or whole-context access.
Delivery/read/input receipts remain invariant and cannot be edited by policy.

## Observation Before Intervention

The current question is which collaboration failures actually occur under free
communication: loss, delay, misuse, coordination or overhead. Do not choose the
evolution target before collecting evidence. Freeze each task's TeamSpec,
assignments, tools, model, budgets, evaluation and scheduler across policy arms.
CooperBench uses its fixed two-worker plus leader adaptation. The primary pilot uses fixed async scheduling. Serial scheduling is available
for diagnosis, not pooled with the async pilot. Neither architecture selection nor async scheduling is RSI. Later candidate
mechanisms may include confirmations, protocol/state synchronization or proactive
notifications, not just content selection; their design follows observed failures.

1. Motivation: characterize missing acquisition, insufficient selection, delayed
   availability, post-arrival reasoning and environment/merge failures. Review
   semantic facts and qualifiers, not merely missing references. Unknown remains
   unknown; timing receipts and code-test failure alone are not causal evidence.
2. Causal checks: restore a supported missing fact at a frozen decision boundary,
   compare unchanged-context repetition and matched controls, and replicate under
   fixed budgets. Do not infer causality from full-context scores alone.
3. Policy updates: only after a recoverable problem is established, propose
   reusable policy versions using approved training-task feedback. Keep the
   updater outside runtime and hidden evaluation data outside agent inputs.

Keep each candidate fixed through its collection/validation batch. Compare with
a simple fixed policy, a carefully specified fixed policy, task-time adaptation,
a one-shot revision and compute-matched static tuning. Split related task families
to limit leakage. Select on held-out validation, then freeze before final test.
Preregister acceptance on task quality and total cost with uncertainty, not just
semantic-loss scores. Preserve candidates, parents and rejection reasons.

Count training, feedback, judging and validation costs separately from inference.
No held-out transfer, no rescue from supported fact restoration, or gains matched
by a simple fixed policy are evidence against the evolution hypothesis. Do not
claim recursive improvement of the updater or efficacy from offline fixtures.

## Design References

- [CooperBench](https://arxiv.org/pdf/2601.13295): file/terminal work, free-form
  messages at the next step and executable joint evaluation.
- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams):
  independent contexts, direct messaging and shared task state.
- [A2A lifecycle](https://a2a-protocol.org/latest/topics/life-of-a-task/):
  distinguish messages, task state and artifacts. This is not an A2A wire implementation.

All paid pilots, replay, feedback and update experiments require separate approval.
