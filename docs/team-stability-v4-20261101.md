# Team Stability And Specialist Policy

2026-11-01. Implemented v4 revision following review of the coordinator-only v3
baseline. Current protocol: [agent-team-design.md](agent-team-design.md).
This document retains historical v4 evidence. V5 adds explicit completion claims,
dependency-waiting message activations and matched Leader-condition entry points;
see [the v5 review](team-review-v5-20261101.md).

## Review Decisions

Both reproduced submission-loss issues were accepted and fixed.

1. **Repeated indefinite waiting.** The scheduler now identifies a stalled episode
   only when there is no in-flight/ready operation, runnable assignment, deliverable
   mail or finite waiting deadline. A finite Worker timer no longer produces a
   false deadlock notice. The first stall notifies the Leader; another indefinite
   wait without any intervening progress source initiates draining. Partial Worker
   reports and the reserved final submission remain possible rather than idling
   until `session_time_limit`. Explicit finite waits and genuinely slow work still
   obey the session deadline; there is no hidden model polling or semantic repair.
2. **Selected-file export.** Freeze records the workspace inventory and hashes, not
   every file body. Both Single and Team export only `pipeline_path` at submit and
   check the exported bytes against the frozen hash. The 128-file/16-MiB eager
   capture limits are removed. Unrelated CSVs/binary files no longer consume the
   pipeline's export quota or cause one Docker exec per unselected file. A changed
   Team artifact is rejected, not silently submitted. Single takes a fresh snapshot
   for each submission attempt, without falling back to a previous attempt's bytes.

The remaining applicable suggestions were also accepted:

- Default activation capacity inherits the shared model-call ceiling; the pilot
  explicitly uses 64 instead of 16. Message activations retain their original
  permissions and still spend shared model/message/domain budgets. There is no
  read-only-wakeup policy or variant.
- `activation_usage` distinguishes assignment and message activations, counts
  model/domain usage, and records triggering message IDs. Message activation rows
  have no assigned `task_id`; the former assignment is only `previous_task_id`.
  Old results are not overwritten. Cancelling that old task does not cancel an
  independent message activation; team closure stops new actions. These counters
  describe execution cause, not semantic productivity or exclusive file writes.
- Full-tool Leader prompts use a neutral capability description rather than the
  experiment label. The explicit configuration/manifest ablation label remains.
  Team-only submission language stays out of shared Single instructions.
  Weighting/interpolation checklist hints were removed rather than sourced from
  the known archeology failure. Generic checks remain in shared `PROJECT_CONTEXT`.
- The missing v3 document and failed-container receipt observations were stale by
  the time of this review response: the document and final clean v3 `...-02` receipts
  already existed. Earlier failing receipts remain intact. V4 has fresh evidence
  below rather than relabelling v3 results.

## Default Team Design

The main Leader still has **zero domain tools**, including readers. It actively
looks for meaningful multi-member decomposition before assigning work, instead of
preferring one end-to-end owner. It selects complementary fixed specialists, gives
each a distinct deliverable, specifies interfaces/dependencies, overlaps independent
work and asks members to exchange needed information directly.

The versioned `kramabench-team-v4` catalog contains:

| Template | Responsibility |
|---|---|
| explorer | Source discovery, schemas, coverage and evidence locations |
| analyst | Requirements, source meaning, assumptions and scoped analytical questions |
| worker | Implementation and integration of assigned components |
| verifier | Focused execution/artifact/claim checks, discrepancies and unchecked scope |

These are reusable fixed templates, not four mandatory members or a fixed pipeline.
Several instances may own independent partitions. One member remains possible when
no useful split fits the task/capacity, with the reason requested in its brief.
Artificial splitting, duplicate full-task work and a compulsory review panel are
not introduced. This policy is prompt-directed; permission enforcement is runtime-
directed. Scripted tests cannot prove spontaneous real-model decomposition.

## Verification

Server evidence:
`/home/zhoujunye/MAS-information/outputs/team-stability-v4-20261101-01`.
Source digest: `cec18097da92bf9b`.

- Full offline suite: **203 passed, 4 skipped**. Skips are explicit existing-image
  container opt-ins, not skipped pure-runtime regressions.
- Team/review/coordinator/v4 regression repeated ten times: **87 passed** in every
  repetition. Independent JUnit receipts and logs retain each run; the first run's
  scripted traces and workspaces are retained under `scripted-evidence`.
- Existing-image container suite: **4 passed**. Both arms successfully submit a
  pipeline sorted after 130 CSVs and a binary file, with exactly one export.
  Other checks cover exact bytes and unsafe/stale paths, plus a real saved pipeline
  produced by a scripted Worker and executed by a separate `verifier` before freeze.
  The coordinator has no domain calls or submission source code in its context.
- A four-specialist scripted integration covers overlapping explorer/analyst work,
  two direct peer-message exposures, dependent implementation, a verifier handoff
  and path-only submission. It checks a synthetic artifact/output using trusted
  fixture operations, not arbitrary host-code execution or benchmark grading.
- A message regression completes 17 idle-message wakes and then another assignment;
  separate usage accounting identifies message-driven domain work without inventing
  a task record. Stall regressions preserve submission after both empty-team and
  blocked-Worker repeated waits, while finite timers remain runnable progress sources.
- Default CLI Single/Team transport pair: both complete with matching output
  contracts, valid traces and `infra_affected=false`. Single uses 4 scripted calls /
  3 domain calls; Team uses 9 / 1. This deliberately small one-Worker transport fixture
  is not evidence for the new multi-member policy; the separate specialist fixture
  tests that workflow. Counts are wiring observations, not an efficiency comparison.
- No paid model, judge, model retry, image pull/build or package installation.
  Fixture costs are $0; prompt-token/cache fields are synthetic, not measurements.

## Remaining Boundaries

`hash_recorded` means a regular file's hash was observed, not that its content is
readable UTF-8, valid Python, executed or correct. The 1-MiB selected-file limit,
path containment, no-symlink/nonregular protections, UTF-8/nonempty checks, hash
binding and audit/time limits remain. The workspace snapshot still hashes all
audited files once, so an arbitrarily large workspace can still exhaust audit time.
Freeze is not an OS-level write lock; a later mutation is detected at export.

No real-model v4 run was authorized or executed in this change. Before calling the
research baseline empirically validated, separately authorize a small protocol
pilot with fresh non-archeology tasks, exact settings and an explicit cost/call
scope. Check path selection, waits, wakeups and actual division of work; do not
infer scientific correctness or collaborative advantage from these offline tests.
