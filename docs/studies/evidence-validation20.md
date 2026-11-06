# MAS Evidence Workspace: Validation20 Pair

Authorized 2026-11-05: remove the temporary three-question experiment code and
results, integrate the current mechanism into existing workflows, and run the
original 60 frozen questions under both Observation and Full with no dollar cap.
This means 120 solver attempts and at most 106 paid grading calls, not 60 combined.

## Frozen Scope

- Same Validation20 v1 manifest: 20 DataClaw, 20 HDR and 20 Krama questions.
- Manifest SHA256: fc39ad8539e2af0b140a6b9a8b3144d241742b2c3b2424b6d74ae03f1829e0a5.
- Observation and Full are opt-in conditions on ordinary Claude Code subagents.
  Original Single/Structured/Native results and frozen baseline prompts remain.
- Claude Code 2.1.286; deepseek-flash[1m]; high effort for lead/workers; Teams off.
- Global solver concurrency 6, grading concurrency 2; isolated per-attempt state.
- Timeouts: DataClaw 1200s, HDR 1800s, Krama 3600s. Web cap 4 where enabled.
- No dollar cap, no project output-token cap. Native offline requests use the
  default max_tokens=32000; this is not an unlimited context/output guarantee.
- One solver attempt per question/mode; no automatic retries or replacements.
- Original host-side evaluation contracts; at most 106 paid judges, no new judges
  for deterministic tasks. Timeouts score zero; other unknown grades stay unknown.
- Raw HDR questions, gold SQL, answers and evaluation logs stay private on server.

## Integrated Ownership

`harness/evidence_mas/integration.py` owns shared launch/configuration/proof checks
and workspace audits. Existing common and Krama runners add explicit evidence-mode
options; baseline branches remain unchanged. The existing matrix schedules the
two condition labels and reuses existing graders/report readers. The thin
`run_validation20_evidence.py` entrypoint freezes scope and invokes those workflows.
No second three-task runner, provider client, agent scheduler or solver loop.

Lead-only mode guidance is injected by EvidenceMASCLI once; task/limit rules are
shared with workers and identical between modes. The mode guidance and tools are
intentional differences, so this compares configured collaboration mechanisms,
not isolated storage code or untouched native CLI defaults.

## Preparation And Execution

Source stage: `/home/zhoujunye/mas-stages/20261105-evidence-validation20-01`.
Native fake-provider proofs:
`/home/zhoujunye/mas-data/receipts/evidence-validation20-native-20261105`.
Both modes passed with high effort verified in requests, default max_tokens=32000,
exact image/binary bindings and hashes of the evidence implementation. Zero paid
calls in these proofs; both owned probe containers were removed.

Server test suite: 480 passed in 13.56s, including DataClaw/HDR fake-workflow tests
that keep reference fields out of prompts/mounts, matrix condition paths and
proof isolation, and no-cap native launch configuration. Tests are engineering
verification, not evidence of efficacy or complete runtime safety.

Initial output: `/home/zhoujunye/mas/outputs/mas-evidence-validation20-20261105-01`.
The driver writes source/input/protocol and authorization receipts, private raw
evidence, progress, grading progress, summary, and separate derived public-metadata
reports. Native CLI failures and lifecycle audit exceptions remain in the results.
No worker success, hook event or CLI final alone establishes answer correctness.

### Detached Continuation

The user requested independent background execution. During the switch from the
foreground SSH launch, the initial driver had already dispatched ten model calls
across its first six started slots; stopping that driver interrupted those six.
An earlier preflight-only observation was no longer current. The initial batch
summary retains six interrupted and 114 not_started slots, and is not deleted.

No started slot is rerun. The existing matrix now supports retaining all started
rows from a sealed interrupted batch with the same manifest/protocol and only
dispatching its not_started slots. The continuation has 120 logical rows: six
retained interrupted attempts and 114 new solver attempts, not 126 attempts.
Grading remains within the original maximum of 106 calls. These interrupted rows
must not be described as completed 60-question pairs or silently replaced.

Continuation source:
`/home/zhoujunye/mas-stages/20261105-evidence-validation20-background-02`.
Output: `/home/zhoujunye/mas/outputs/mas-evidence-validation20-20261105-02`.
Log: same prefix plus `.driver.log`; final status: `.driver-status.json`.
Launcher metadata: `.launcher.json`. Launch PID 555166 was independently checked
alive with parent PID 1, its own session, stdin=/dev/null, and stdout/stderr both
redirected to the persistent log. It does not depend on a live SSH/chat connection.
Server regression suite after continuation support: 481 passed in 14.08s.

## Authorized Cleanup

Removed the paid smoke/extended and three-wrong-question runners, synthetic
three-task catalog, their runner-specific tests and five temporary reports. Core
store/MCP/hook/schema/workflow regression tests and native offline probes remain.
Removed five associated server result directories and six paid temporary source
stages by explicit allowlist. No original Validation20 result, input, environment,
credential or unrelated project was removed. Retired migrated active source files
were also removed after verifying their replacements.

Source-only pre-removal snapshots preserve overlapping uncommitted code, not a
second active implementation. Server cleanup receipt:
`/home/zhoujunye/mas-data/receipts/evidence-three-task-cleanup-20261105`.
The three-task result payloads themselves were deleted as requested. No claims or
links to those deleted results should be treated as current experiment evidence.
