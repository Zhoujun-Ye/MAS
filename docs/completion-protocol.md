# Common Completion Protocol v4

This is a new protocol for all handoff forms, not a retrospective repair of
TravelPlanner pilot 03. Existing traces, grades and status labels are unchanged.

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

Reinspection of pilot 03 found all three Adaptive runs' latest Leader drafts
(tasks 60/61/120, events 389/279/424) pass native plus supplemental grading.
They were blocked from submission and remain incomplete in the original study.
The earlier report had only verified the first two. This motivates fixing the
common protocol before the newly authorized BCP pilot, not crediting old drafts.

Server regression after the protocol change: 51 passed, exit 0 (2026-10-29).
Coverage includes all five forms, request versus informational reactivation,
reserved-call accounting, refusal of tools during finalization, and no raw
pending-report bypass. This was the pre-BCP v3 check.

The completed BCP pilot exercised v3: 24/24 submitted, including two reserved
finalizations. Its recovered interface errors motivated v4: only workers receive
`finish_assignment`; roles see append-only shared budget/grant state; invalid
arguments are rejected before domain-budget reservation; requests cannot silently
default to FYI. Schemas/prompts stay stable per role across forms. See the
[results and repair boundaries](bcp-pilot-results-20261029.md). V4 has offline
regression coverage, not a paid efficacy result.
