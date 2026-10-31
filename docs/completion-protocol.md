# Submission and Completion Protocol

Runtime owns lifecycle, submission state and finalization. Information Harness
owns the sender-policy boundary, not the authority to declare verified success.

## Three Independent States

- Agent lifecycle: idle, running, waiting, failed, terminated. Termination does
  not imply that its assignment was submitted or correct. Shutdown is traced.
- Worker assignment: working, blocked, submitted; completed is evaluator-only.
  Each assignment has a revision and, after submission, a submission_id.
- Verification: not_run, passed, failed, error. Only a trusted evaluator can
  change this field; agent reports and status tools cannot do so.

The leader coordinates; it is not a required worker submission. There is no
general dependency DAG: CooperBench requires both worker revisions followed by
external merge and tests.

## Submission and Reopening

Only explicit submit_assignment captures an immutable snapshot through the
adapter's submission_hook. Code submissions must select implementation paths;
an empty list explicitly submits an empty patch. Without a hook, only the report
is frozen (report-only-v1); this is not a coding submission. Snapshot I/O runs in
the owning turn outside the shared-state lock. Failed capture does not submit.

After capture, the runtime records the version and digest and sends a fixed
metadata-only task_submitted notification to the leader. Status delivery does
not consume the content-message budget. It cannot carry report text, assignment
text, patches or evidence. The substantive report goes to the leader and pending
requesters through the same policy, ACL and budget checks as send_message.
Thus a snapshot may be recorded even if its report exhausts the message budget.

Every incoming message wakes its recipient but does not invalidate its snapshot.
A submitted worker can inspect authorized messages/artifacts or send a correction.
Trusted read-only file tools remain available, including read_file with
metadata_only=true for SHA-256 checks. These read the current workspace, not the
immutable submission, and still consume the member's tool allowance. Writes and
arbitrary terminal commands automatically reopen the assignment before execution.
This invalidates the current submission, increments
the revision and resets verification. Earlier snapshots remain in the trace.
update_task(status=blocked) also reopens a submitted revision, but yields.
Any tool-free worker reply makes the member idle without submitting. Nonempty
replies are forwarded verbatim to the leader through the same outgoing-message
validation boundary; empty replies only yield.

Mutating domain tools and terminal commands reopen even when they follow a
submission in the same assistant turn; the new revision requires a new explicit
submission. Duplicate submissions are errors. wait_for_message changes only
readiness/lifecycle, not task validity.
list_tasks exposes only fixed identity, status, revision and verification fields.
The communication-only leader is not presented as an unfinished worker assignment.

## Finalization and Verification

Normal finalization requires both current worker submissions, no runnable or
in-flight worker turn, and no queued message/status event. A message arriving
during a model call must enter a later input before normal finalization. This is
an operational quiescence check, not a claim that all important facts were sent.
Both schedulers reawaken the leader when the last blocker yields and all workers
are submitted. This also handles a deferred final answer without a new message.
Messages appended at a quota boundary but never included in a request still block
normal finalization; context append is not consumption.

Budget finalization reserves a bounded leader answer without tools and joins
in-flight work first. It may return a partial answer: status=completed means the
execution returned a final answer, NOT task success. submission_status is
submitted only when the submission/quiescence gate holds, otherwise incomplete.
verification.status remains separate. Deadlock, missing explicit submissions,
member budget exhaustion preventing completion, and context/output overflow are
agent failures. All started attempts remain in the success-rate denominator.
Infrastructure failures and external interruptions are reported separately, never
silently removed. Unknown grades remain visible; confirmed success / all started
is a conservative rate until grading is complete.

After workers have joined, non-submitted revisions receive a terminal snapshot.
For member-level context/model/token exhaustion, capture occurs when that member
halts, while its peers may continue. Final cleanup reuses that snapshot.
This does NOT set submitted=true or rescue the primary failure. CooperBench can
merge/test these frozen partial artifacts diagnostically. Snapshot errors are
recorded, not grounds to drop the attempt. Existing valid explicit snapshots
remain the evaluation source. The in-process success verifier still requires a
normal complete submission set.

A trusted in-process verifier receives detached frozen snapshots, not agent
claims. record_verification(role, submission_id, status) is a host-only API that
rejects stale versions; only passed marks that assignment completed. A joint
verification result does not automatically assert each individual task passed.
CooperBench instead grades after execution: grade.json binds the joint verdict
to both exact explicit/terminal snapshot IDs/digests. code_correct and
verification describe the code tests; correct remains false for an agent-failed
run even if its terminal code happens to pass. The original result is immutable.

## Independent Budgets

Each member has an independent domain-tool quota. Optional cumulative-token,
model-call, message and evidence-read caps remain available for diagnostics;
the authorized rerun sets all of these to null. Refusing one member's tool/message
does not charge its peers. Exhausting a member's model/token allowance halts that
member; runnable peers continue. A task wall-clock deadline stops new work and
refuses late actions. The manifest pins limits; result.json records member_usage.
Provider receipts still meter tokens and cost without imposing a cumulative-token
stop. When explicitly configured in diagnostics, an over-limit response has its
tools refused. Per-response output/context safety bounds remain unchanged.
No independent communication-round cap is imposed.

Local/provider context overflow stops only that member. Output truncation refuses
all actions from the incomplete reply and appends a recovery notice; one consecutive
recovery turn is allowed under the same budgets. A second consecutive truncated
reply halts that member. A normal response resets the recovery counter. This is
distinct from provider transport retries, which remain disabled. Shared deadline
and infrastructure errors still stop the team. State is appended only when changed.
Both schedulers explicitly report rejected premature leader finals and then wait
for events rather than polling for another answer.

Controlled scheduling and async execution share this contract. Shutdown waits
for in-flight provider/tool/snapshot operations; it cannot forcibly cancel remote
requests or undo tool side effects. Adapter-managed background processes are
outside this join guarantee; native environment validation must address them.
No paid run or native benchmark evaluation is authorized by this protocol.
