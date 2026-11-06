# MAS Evidence Workspace Engineering Fixes

Date: 2026-11-05. No new paid calls or attempt retries in this repair.

## Changes

- MCP now validates nested references, typed arrays, enums and numeric bounds
  before storage mutations. Valid tool calls with invalid arguments return
  `isError` with the exact argument path and recovery guidance, rather than an
  opaque protocol error. Reference-kind and dependency checks remain strict.
- Explicit reference shapes and descriptions distinguish source snapshots,
  observations, EvidenceLinks and Candidate/Selection dependencies. Regression
  cases cover wrong source enums, whole-object references, missing revisions,
  boolean revisions, invalid trace directions/bounds and invalid dependency kinds.
- Lead and worker prompts in the opt-in evidence condition clarify API use and
  checking task-required operations before claiming completion. Frozen baseline
  prompt and adapter files remain unchanged.
- A reusable read-only workflow audit checks successful recorded methods by role.
  Paid smoke verification uses it to report missing required steps, including
  provenance tracing. It does not execute missing tools, retry a model, take over
  lead decisions or pretend to guarantee instruction compliance.

## Naming

The package and current project title are `mas` / MAS. Active script defaults,
container labels and image tags use `mas`. Server data and stage directories were
renamed to `/home/zhoujunye/mas-data` and `/home/zhoujunye/mas-stages`; old absolute
paths are compatibility symlinks for historical artifacts and environment scripts.
Existing image IDs were retagged, not rebuilt. Old tags and historical evidence
were preserved; credentials and unrelated projects were not changed.

## Verification

Source stage: `/home/zhoujunye/mas-stages/20261105-evidence-engineering-fix`.
Final server suite: **470 passed in 13.52 seconds**, including naming regression.
Includes malformed-input recovery, rejected writes leaving no objects, failed
calls not completing requirements, missing trace detection and role separation.

Native fake-provider receipt:
`/home/zhoujunye/mas-data/receipts/evidence-engineering-fix-native-20261105/summary.json`.
The probe uses the renamed existing image and tests both full and observations
modes on Claude Code 2.1.286. Raw evidence and owned-container cleanup receipts
remain on the server.
Both modes passed, with 19/14 synthetic requests, no degraded capture, and both
owned containers removed. No real provider calls were made.

The earlier paid smoke remains 2/3 strict pass. Fixes have not received another
paid real-model run. Schema improvements and accurate missing-step reporting do
not prove a real model will never submit invalid arguments or omit a requirement.
