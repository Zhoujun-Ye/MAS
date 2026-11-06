# Shared Evidence Workspace: Native Offline Verification

Date: 2026-11-05. This supersedes the integration-pending status in the earlier
`evidence-mas-offline.md` report, not its historical measurements.

## Implementation

One opt-in component lives in `harness/evidence_mas/`. One run-bound SQLite store
and content-addressed payload directory serve Observations, Issues & Candidates,
Evidence Links and Selections. The same MCP implementation runs in per-role stdio
processes; these are not independent observation/decision services.

Raw observations are automatically captured and preserve history. Interpretations
are versioned and can be withdrawn; links can be retracted. Unsupported claims
are labelled hypotheses. Execution/outcome references remain optional and typed.
Selection changes transitively invalidate dependent candidates. `workspace.trace`
supports forward and reverse provenance. The native runtime still owns delegation,
context and scheduling; the lead retains final selection authority.

`EvidenceMASCLI` is separate from existing baseline adapters and prompts. It
configures hooks and native evidence-worker MCP tools. `observations` exposes
read/trace tools only; `full` adds claims, evidence and lead-only selections.
Modes bind once per run. No new baseline default or launch choice is installed.

## Server Evidence

Source stage: `/home/zhoujunye/MAS-information-stages/20261105-evidence-native-03`.
Final receipt:
`/home/zhoujunye/MAS-information-data/receipts/shared-evidence-native-20261105-04/summary.json`.

Native Claude Code 2.1.286 used the existing image
`sha256:f940900759fee9d7f9fcdd819f5fc7062d4b1e11b192355b503ce33511bfa14b`.
Binary SHA256:
`fe503f65c6289d59c23e5b21ae44f03583f997dd33a2cbfc75ab4f96fb8fc73f`.

| Condition | Result | Synthetic requests | Worker tool calls |
| --- | --- | --- | --- |
| Full evidence | PASS | 19 | 6 |
| Observations only | PASS | 14 | 3 |

Both conditions ran concurrently in independent network-none containers, two CPUs
each, through a synthetic-only host gateway dispatcher. No real provider keys,
external provider requests, paid experiments, installations or model retries.
Both owned containers were removed after completion; raw evidence remains private.

Verified native lead and background-worker lifecycle, automatic tool observations,
MCP reads by both roles, lead reading the worker's observation, and trace traversal.
Full mode also verified worker proposal/evidence attachment and lead selection of
that candidate. Worker MCP did not advertise the selection tool. Observation-only
mode neither exposed ledger tools nor created ledger objects. No degraded receipt.

Final stage test suite: **446 passed in 12.79 seconds**, using the existing server
evaluation environment and explicit `KRAMABENCH_UPSTREAM`. An earlier invocation
without that path had 444 passed / 2 skipped; the configured rerun covered both.
After scoped migration and deletion, the active server repository also passed
all **446 tests in 13.52 seconds**.

The first native fixture failed because its lead did not refresh an empty view
after native asynchronous worker completion. The fixture was corrected to consume
the native notification and reread; no scheduler was added. Failed evidence at
`receipts/evidence-mas-native-20261105-01` is retained, along with subsequent runs.

## Ownership And Cleanup

Reusable `tools`, `credential_gateway`, `gateway_bridge` and `proof` modules moved
from `scripts/common/` to `harness/runtime_support/`. All affected imports and
container source mounts were updated; the four obsolete local and active-server
source files were removed, with no forwarding copies. Historical stages remain.

Before the scoped active-server source update, all 21 overlapping source files
matched their expected pre-migration hashes and were archived under
`/home/zhoujunye/MAS-information-data/receipts/shared-evidence-migration-20261105/`.
Deletion checked hashes again and verified replacements and affected imports.
No baseline adapter or frozen prompt was changed. Mixed benchmark container
composition remains in `scripts/common/runtime.py`; see `harness/README.md`.

## Limits

Synthetic tool sequences establish integration, not independent exploration,
evidence comprehension, accuracy gains, or how a real model changes its decision.
Native termination accounting and workspace quiescence are not established merely
by lifecycle events. Role configuration is not same-UID authentication. Hashes and
immutable API semantics do not make solver-writable storage tamper-proof.
Arbitrary Bash dependencies are not automatically recovered; source/execution
snapshots require explicit registration. Failure/cancellation and large-output
behavior have component coverage, not exhaustive native-runtime coverage.

No efficacy or paid-provider conclusions follow from these tests.
