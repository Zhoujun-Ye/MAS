# Evidence Review Repair

Historical repair receipt. Its Structured composition was subsequently superseded;
current FULL/OBS use the Native (N) prompt and decision-v2, described in
`docs/studies/intermediate-full.md`. Do not treat this receipt as current configuration.

Date: 2026-11-05. Local source repair and authorized isolated server offline tests.
No active-server deployment, paid calls, judge calls, experiment reruns or changes
to historical scores. The review's aggregate numbers were supplied by the user;
this repair did not independently recompute them.

## Implemented

- Benchmark composition injects the exact frozen Structured prompt once, then
  appends mode-specific workspace guidance. Workers receive the same tool guidance
  and shared limits, not lead orchestration instructions. Composition lives in
  `scripts/common/evidence.py`; reusable harness code does not import scripts.
- Removed the replacement collaboration policy, smoke-operation reminders and
  hook instruction to reread each observation. Benchmark audits report lifecycle,
  reads and method counts rather than requiring reads/traces/selections. Store
  availability is explicitly not verified delegation or reasoning quality.
- Operation keys are actor/role-scoped. Exact legacy retries remain readable.
- MCP proposals require explicit dependency completeness. Independent candidates
  can declare an empty complete list. Historical store calls still default to
  unknown; stale/unknown selection disclosure and dependency checks remain strict.
- Observation lists contain compact identity/tool/input/preview rows. Search covers
  both inputs and outputs; bounded original input reads are available. Valid
  observation read spans clamp at EOF and 16000 characters. Citation spans remain
  strict to avoid silently changing evidence references.
- Ledger views default to summaries; full records are available with detail=true.
- Capture uses an indexed native call identity lookup instead of a full object
  scan. Only dependency-changing mutations run cycle checks. Ordinary reads use
  a read snapshot and a separate short audit write rather than reserving the writer
  lock through blob reads. Initialization skips repeated schema writes after setup.
  Explicit idempotent reads still use the serialized path. SQLite reads can still
  delay writer commits; this is not a lock-free implementation.
- Worker MCP processes get distinct instance IDs for write ownership. These are
  process-instance identities, not authenticated native-agent identities. Reconnect
  changes identity, and actual native process sharing/reuse remains unverified.

## Remaining Work And Limits

- Keep the existing 16-tool API for this compatibility repair. Collapsing it into
  3-4 coarse tools needs a separately tested schema and native fixture migration;
  renaming tools alone would not reduce arguments or reasoning cost. Compact
  responses and removal of mandatory operations are implemented now.
- No automatic push, submission gate, multiverse executor or HDR budget allocator.
  These change the research mechanism and require a separate design decision.
- No historical candidate replay was performed. Such analysis must keep private
  payloads server-side and must not count hindsight access to gold as a solver gain.
- Restoring the lead prompt fixes that confound, not all possible differences:
  MCP tools, worker definitions and observation hooks still differ from Structured.
  New proof/configuration hashes invalidate old proofs for new launches. Old results
  must not be relabeled as results of the repaired condition.
- No claim of improved accuracy, latency, native identity binding or real-model
  compliance follows from fake-CLI/offline tests.

## Verification

Source-only stage: `/home/zhoujunye/mas-stages/20261105-evidence-review-repair`.
Used the existing `/home/zhoujunye/mas/.venv/bin/python`; no installs or environment
changes. Inspected server process ownership/capacity before running serial pytest.
Final full suite: **502 passed, 2 skipped in 13.40 seconds**, including two
end-to-end launch-argument regressions for frozen lead prompt composition.
`git diff --check` also passed. No native CLI/fake-provider probe or real-model
benchmark was run in this repair.

Pre-edit source snapshots are `/tmp/mas-evidence-before-review-fix-20261105.tar.gz`
and `/tmp/mas-evidence-before-composition-20261105.tar.gz`. Existing unrelated
uncommitted work was preserved. No source cleanup or active deployment occurred.
