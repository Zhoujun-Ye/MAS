# Team Review Decisions

Historical v2 review. Its full-tool default, read-only coordinator, removed generic
checklist and submit-time export were superseded by the user's subsequent
[v3 coordinator baseline decision](team-coordinator-20261101.md). Evidence below
remains an unchanged record of v2, not a claim about the current runtime.

2026-11-01. This revises the v1.1 runtime after the supplied review, not the
historical v1 paid attempt. The goal is a task-neutral, mainstream-shaped Team
baseline suitable for studying failures, not an exact Claude Code reproduction.
The user explicitly rejected keeping a read-only-after-wakeup variant.

## Accepted Changes

| Review issue | Implemented decision |
|---|---|
| Idle info silently did not activate a recipient | All message types may activate an idle recipient; needs_reply only tracks requested replies. Original template grants and history survive; no read-only wake variant. |
| Mandatory acceptance serialized dependencies | Normal completed handoff releases dependencies. Accept/reopen remain optional Leader actions with revision checks. Forced limit/drain reports are partial and do not unlock dependent work. |
| Coordinator-only Leader was called the default | T0 defaults to full domain grants. T1 explicitly selects coordinator-only grants in the same runtime. Selecting one does not launch the other. |
| Task-tuned and asymmetric analysis prompts | Remove ANALYSIS_CONTRACT, root-only scientific checklists and behavioral mitigations from active prompts. Preserve candidate ideas only in non-loaded notes. Keep shared operational/data-integrity rules. |
| Inline code copying and asymmetric submission | Single/T0/T1 all submit pipeline_path. Runtime exports bounded UTF-8 bytes from a regular file, checking snapshot/hash identity. Native exported pipeline_code remains compatible. |
| Explorer paging bottleneck | Retain explorer, grant terminal, omit write_file, explicitly label its no-write rule advisory. No claimed shell sandbox. |
| Lower 20/12 model and 60/24 domain member caps | Default member ceilings inherit the global limits. Remove static budget numbers from both Single/Team system prompts; retain accounting, shared ceilings and last-call notices. |
| Avoidable protocol refusals | Batch update_task, accept workspace-root absolute scopes, remove wait's 120-second maximum, wait indefinitely by default within the global deadline. |
| Repeated stalls and stale blocked state | Re-arm no-runnable notices after meaningful state changes; restore running on progress/wakeup. |

Giving T0 write tools also required the closing barrier to wait for admitted Leader
operations, not only Workers. Added a regression with a root write in flight during
budget-triggered draining. Partial handoff classification prevents a forced final
report from inadvertently satisfying the new automatic dependency condition.

## Qualifications

The official [agent teams documentation](https://code.claude.com/docs/en/agent-teams)
supports the broad lead/member design, direct member communication, automatic
dependency release on completion and leader-assigned or self-claimed tasks.
We keep Leader-only assignment because it matches the chosen research design;
self-claiming is not required merely to resemble a mainstream team.

The official [subagent documentation](https://code.claude.com/docs/en/sub-agents)
describes fixed definitions, optional turn limits and resuming contexts with original
tools/permissions. This supports removing our lower default local caps. It does not
prove that our unrestricted shell plus a no-write prompt reproduces Claude Code's
read-only enforcement or its built-in Explore behavior.

We do not accept the review's inference that a model violating a prompt proves
the instruction is not mainstream or never useful. The reason to remove these
mitigations here is treatment contamination/task neutrality and prompt asymmetry,
not that one observed violation establishes general ineffectiveness. Likewise,
absence from product documentation is not sufficient reason to remove infrastructure
safeguards. Shared budgets, bounded activations/messages, safe-point delivery,
validation, drain/freeze, hashes and immutable logs remain.

All-message wakeup may expose extra calls, redundant work or conversations that
continue without value. We retain those as observable behavior within shared limits,
not suppress them with a special read-only wake policy. Grants are unchanged, not
expanded: an explorer remains subject to its original no-write instruction.

## Verification

Server evidence: `/home/zhoujunye/MAS-information/outputs/team-review-v2-20261101-01`.
Verified source digest: `707ad92072051985`.

- Full offline regression: 180 passed, 1 skipped. The skip is the explicit Docker opt-in.
- Existing-image Docker transport test: 1 passed separately. Checks real snapshots,
  byte-exact export beyond a tool-output page, symlink/FIFO rejection and changed
  file rejection. No image pull/build/install; the test's container was removed.
- Team protocol/review tests: 64 tests repeated 10 times, all passed. Regression
  exposed a redundant stall notice when a result was already queued for the Leader;
  the scheduler now wakes on that result without adding a spurious stall notice.
- Single/T0/T1 independent synthetic fixtures: all completed, no integrity errors,
  no infrastructure impact, same artifact hash and common output contract. Single
  used 4 scripted calls / 3 domain actions; T0 and T1 each used 9 / 1. These policies
  are scripted, so this is wiring evidence, not a cost or coordination comparison.
- Actual and estimated fixture cost: $0. Prompt/cache values are synthetic and do
  not measure provider caching. `verification.json`, source snapshot and JUnit
  receipts retain the exact evidence.

Fixtures are not benchmark accuracy, spontaneous coordination or cache/cost measurements.
No new paid model, judge, retry or matched real-model Single run is authorized by
this review pass. The prior paid evidence remains unchanged in
`outputs/kramabench-paid-team-v1-20261101-01`; its numbers do not describe v2.

## Research Boundary

The review's warning about predominantly sequential pipelines is useful, but one
observed decomposition cannot establish that every KramaBench task lacks useful
parallelism. Select and characterize tasks where parallel work genuinely requires
cross-member information before claiming a peer-communication effect. Do not force
chat or extra Workers merely to increase message counts.

No matched paid Single/T0/T1 comparison has been run for v2. The archeology reference
disagreement is still unresolved; do not modify it to improve a score. Path/hash
binding proves artifact identity only; no trusted pipeline re-execution, semantic
verification, coordination-quality gain or causal conclusion follows from the
engineering regression.
