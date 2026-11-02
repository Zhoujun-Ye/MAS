# Team Review V5

2026-11-01. Review response relative to `ce124543a3f605cb05fc529c68d5be06c44de2bf`.
The user selected a future full-tool versus coordinator Leader comparison, not a
paid launch or an automatic switch of the default condition.

## Applied Decisions

**Explicit task claims.** `finish_task(status, summary)` ends a live assignment
with completed, partial, blocked or failed. It is a sole-call control, not a new
model turn, paid judge, rigid report template or mandatory verification workflow.
Only a normal returned assignment with an explicit completed claim releases its
dependents. Plain final text is retained as an unclaimed handoff, including text
that merely sounds successful. Acceptance cannot turn a partial/unclaimed report
into completion. Forced closing remains partial; reopen clears the prior claim.
Runtime outcome, member claim and evaluator correctness are separate facts.

**Dependency-waiting mail.** A member whose assignment is queued behind unfinished
dependencies can process incoming messages with its unchanged grants. The message
activation receives its own pending local brief and mail, not the full root task.
It does not start, complete or overwrite the pending assignment. On return the
member goes back to assigned, or idle if the pending assignment was cancelled.
This resolves the A-needs-B's-interface/B-waits-for-A scheduling cycle. A pending
message activation is not mistaken for consumption of a dependency during reopen.
Member invocations remain serialized; budgets and activation admission still apply.

**Leader comparison.** `--leader-mode coordinator|full` remains available for one
Team. `--mode leader-pair` explicitly selects `team_coordinator` and `team_full`,
each once, with separate workspaces/evidence and matched common preflight settings.
It rejects an additional Leader-mode override. Existing `team`, `single` and `both`
launch sizes are unchanged. Both Team conditions share the coordination-first,
meaningful specialist-decomposition policy. Their actual tool grants and capability
descriptions differ, and manifests retain actual prompts/grants and claim protocol.
The default remains coordinator; neither condition is declared superior in advance.
The runner requires an existing image (`--pull never`), has zero automatic retries,
and stops subsequent arms after a fatal key/balance error.

**Evidence linkage.** `activation_usage` now includes pending/previous task links,
assignment revision, triggering sender/task/message IDs, newly exposed mail,
domain-call event references, declared paths, before/after audit references,
observed file/hash deltas and overlapping activation IDs. Leader domain usage is
separate. Shared-interval changes are not exclusive write attribution, causal
reasons for edits or verified conflicts; missing audits are null, not no changes.
Original trace arguments/messages retain the underlying evidence. No additional
audits or per-tool Docker exec calls were added for these derived statistics.

## Deliberately Unchanged

- Four fixed specialist templates, adaptive membership and Leader-only task authority.
- Direct peer communication and unchanged grants after every message wakeup.
- No forced minimum team size, automatic reviewer panel or semantic success judge.
- Explorer's no-write policy and assigned write scopes remain advisory coordination
  rules, not a shell security sandbox. Existing snapshots cover tracked/nonignored
  files, not arbitrary writes outside that audit scope or transient writes between snapshots.
- Path submission, selected-file frozen-hash binding, final drains and shared budgets.
- Historical attempts, failed receipts and the known archeology reference disagreement.

## Verification

Fresh evidence is in
`/home/zhoujunye/MAS-information/outputs/team-review-v5-20261101-01`.
Source digest: `f842bd4948e02d34`. JUnit receipts, representative traces, comparison
manifests and a source snapshot are retained separately from all prior versions.

- Full server suite: **218 passed, 5 skipped**. The five skips are Docker opt-ins.
- Existing-image container tests: **5 passed**, including unchanged unsafe/stale
  artifact rejection and selected export after 130 intermediates. Both Leader
  conditions complete a scripted producer/verifier execution workflow
  with explicit completed claims, a valid trace and zero Leader domain actions.
  The full condition permits domain actions; this fixture chooses delegation.
- Team/review/coordinator/v4/v5 suite: **102 passed in each of 10 repetitions**.
  Tests cover all four claim statuses plus unclaimed prose, dependency-waiting peer
  messages with original domain grants, no premature task start, mixed-control
  refusal, cancelled claims, reopen during pending-message work, audit deltas and
  matched Leader-condition preflight. Mocked pilot dispatch checks one attempt per
  selected condition, identical limits and stopping after a fatal provider error.
- CLI Single/Team fixture pair: both done, valid traces and no infrastructure impact.
  Single uses 4 scripted calls/3 domain calls; Team uses 9/1.
- CLI coordinator/full Team fixture pair: both done, matched common contracts,
  valid traces and no infrastructure impact, each using 9 scripted calls/1 domain
  call. Manifests distinguish empty versus full Leader grants and record
  `task_completion_policy=explicit_claim_v1`. These identical fixture counts are
  not real-model efficiency or delegation evidence.
- No real provider, paid judge, automatic model retry, image pull/build or package
  installation. Fixture actual cost is $0; synthetic prompt/token/cache fields do
  not measure provider cache reuse. Owned disposable test containers were removed.

Scripted completion and permission checks establish protocol behavior, not
spontaneous delegation, independent verification quality or benchmark gains.

The future Leader comparison is an adaptive permission-policy experiment: task
decomposition and actual teams may change between conditions. It is not a fixed-team
communication ablation, and equal ceilings do not mean equal realized compute.
