# Coordinator-Only Team Baseline

2026-11-01. User-directed v3 baseline, superseding the v2 full-tool default.
Current protocol: [agent-team-design.md](agent-team-design.md).
This is historical v3 evidence. V4 replaces eager file capture, hardens stalled
waiting and changes the specialist/decomposition policy; see
[v4 stability verification](team-stability-v4-20261101.md). V3 receipts below remain unchanged.

## Contract

1. **Tool-enforced coordination.** Team defaults to `leader_mode="coordinator"`.
   The Leader's registered tool table and model schemas contain only spawn/assign/
   update/finish, messaging, team-state, wait and submit controls. All six domain
   tools, including readers, are absent; forged calls are denied before execution
   or domain-budget charging. Single keeps domain tools. An explicitly selected
   `full` Leader remains an ablation, never the default or an automatically run arm.
2. **Freeze-time file capture.** After admitted work drains, runtime snapshots the
   workspace and captures bounded, regular UTF-8 files matching their hashes.
   Closing includes `frozen_files` with paths, hashes, types and capture status,
   not file contents. Both arms submit `pipeline_path`; Single performs the same
   freeze at its sole submit call. Team submit selects already-captured bytes and
   does not reread the workspace. Later file changes cannot alter that export.
   Model-visible submit receipts carry only metadata; native `pipeline_code` is
   a separate runtime export, not code copied into/out of the Leader's context.
3. **Worker verification.** Execution checks, repairs and rechecks belong to Workers
   while the team is open. The Leader can assign a Worker to run a named pipeline,
   check its observed output and return evidence before `finish_team`. This does
   not add a compulsory review panel or an automatic correctness verdict.
4. **Shared domain checklist.** `PROJECT_CONTEXT`, received by Single and all Worker
   templates, contains generic units/precision, coverage/missingness/types, joins,
   weighting/denominators/interpolation and reproducibility checks. `LEADER_SYSTEM`
   has no separate domain checklist. Implementation instructions are scoped to
   implementation assignments; explorers are not required to save new artifacts.
   The task-tuned archeology estimand guidance remains inactive.

All-message wakeup with original grants, direct peer communication, completion-based
dependencies and shared budgets remain unchanged. There is no read-only wake variant.
Single and Team now also account freeze-only I/O identically: it consumes the audit
allowance and is excluded from the execution clock only when no model/domain work
overlaps it. Submission itself does not masquerade as concurrent domain execution.

## Verification

Final server evidence is in
`/home/zhoujunye/MAS-information/outputs/team-coordinator-v3-20261101-02`.
Source digest: `f319e0ced289763e`.

- Offline full suite: **192 passed, 2 skipped**. The skips are explicit Docker opt-ins.
- Existing-image container suite: **2 passed**. One checks byte-exact file export
  and unsafe/stale file rejection. The other runs a real pipeline created by one
  scripted Worker and executed by a second Worker, then checks closing inventory,
  path-only Leader submission, zero Leader domain actions and valid trace history.
  The synthetic workflow uses no provider. Its trace/workspace is retained under
  `container-fixture`; its disposable containers are removed.
- Team/review/coordinator regression repeated ten times: all passed. JUnit receipts
  and logs are retained independently for every repetition.
- Default CLI Single/Team pair: both completed with matching output contracts,
  empty integrity-error lists and `infra_affected=false`. Manifests record all
  Single domain grants and an empty Team Leader domain grant list. Single uses
  4 scripted calls / 3 domain actions; Team uses 9 / 1. This is wiring, not an
  efficiency comparison. Worker verification is demonstrated by the separate
  real-container workflow, not inferred from this paired average fixture.
- No paid model, paid judge, model retry, image pull/build or package installation.
  Fixture cost is $0; synthetic token/cache fields are not provider measurements.

The earlier `...-01` directory is retained, including the initial integration-test
receipt that failed because the fixture omitted its required final trace event.
That fixture was corrected and rerun. A subsequent shared-clock accounting fix
is covered by the final `...-02` source/tests; earlier evidence is not relabelled.

## Boundaries

File capture is bounded to 1 MiB per file, 128 regular-file attempts and 16 MiB total
retained bytes, inside existing audit/time limits. Skipped/rejected files remain
visible in closing metadata but cannot submit. Outside-root paths, traversal,
symlinks, nonregular/empty/non-UTF-8 files and snapshot mismatch remain rejected.
Runtime capture is not code execution. Worker reports are not trusted benchmark
judgments; actual scientific validity and spontaneous delegation remain unmeasured.

This is a coordination-focused research baseline, not an exact product clone.
No-domain-tool grants do not stop a Worker explicitly sending code in a message;
they enforce who may perform domain actions, not strict information isolation.
The existing paid archeology evidence and unresolved reference disagreement are
unchanged. No new paid benchmark result is claimed for v3.
