# Common Completion Protocol v4

This protocol applies to all handoff forms. Existing traces, grades and status
labels are never changed retrospectively.

- A worker explicitly calls `finish_assignment(report, evidence_ids)` or emits
  a tool-free final report. The harness records completion and sends one report.
- `send_message` requires an explicit `requires_reply` boolean. Findings, corrections and
  acknowledgements are delivered and appended, but do not restart an idle worker.
  A concrete request with `requires_reply=true` reopens the recipient's assignment.
  All messages to the Leader wake it, including late corrections.
- Ordinary finalization waits for unfinished assignments and explicit pending
  requests, not for unrelated informational inboxes to become empty.
- The common total model-call cap includes encoders and a configurable reserve
  (default one call). Work/encoding cannot consume the reserve. On reaching it,
  the Leader receives its already encoded inbox and is asked to submit without
  more tools, retaining its existing context and model settings.
- Unencoded pending intents and other workers' private observations are never
  forwarded during finalization. This avoids a hidden Full Context fallback.
- Finalization tool calls are refused, not executed. Any format retry uses only
  the remaining reserve. Invalid/empty output remains incomplete. Provider,
  context and output-limit errors are not disguised as valid final answers.
- Submitted answers have `termination=workers_completed` or `budget_finalization`
  and list unfinished roles. Completion is not correctness; grade independently
  and report budget-finalized outcomes separately.

BCP preflight extension: the message-count cap also enters bounded finalization,
labelled `message_limit_finalization`, rather than discarding an otherwise
submittable answer. It uses at most the reserved number of calls, still inside
the total cap; it does not forward any unencoded message or raise a budget.

The scheduler, protocol, reserve and prompts are frozen across conditions.
This does not implement adaptive communication learning, automatic fact repair,
or a global shared notebook. A mistaken `requires_reply` choice is observable
model behavior, not silently corrected by the runtime.

Only workers receive `finish_assignment`; roles see append-only shared budget
and grant state. Invalid arguments are rejected before domain-budget reservation;
requests cannot silently default to FYI. Schemas and prompts stay stable per
role across forms. Offline regression coverage is not a paid efficacy result.
