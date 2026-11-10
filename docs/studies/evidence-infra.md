# Active Evidence Infrastructure

Current contracts, not a chronological repair log. Paid results and their frozen
implementations are listed in [retention](../archive.md); measured quality and
speed must be read separately from engineering validation.

## Conditions And Ownership

FULL uses decision-v4 on ordinary native Claude subagents. OBS provides the same
observation access without decision mutation tools. Both use the existing Native
(N) organization, not the separately frozen Structured baseline. The explicit
prompt-only study mode supplies FULL guidance without its decision tools.
None is an untouched default CLI condition.

- `harness/evidence_mas/` owns storage, capture, bounded sharing and decisions.
- `harness/runtime_support/` owns containers, credential transport, SQL/web tools
  and native proof validation.
- `scripts/common/` composes benchmark workflows and unchanged solver prompts.
- Native contexts, delegation and scheduling stay in the external CLI.

There is no automatic semantic choice, submission, retry or custom worker scheduler.
Same-UID stores, roles and run tokens are not adversarial isolation or attribution
boundaries.

## Observation And Decision Contracts

[Executed evidence](intermediate-full.md) is the canonical API contract.
Hook deltas are incremental, capped at three records and 1800 characters
(6000 with initial guidance), scoped per recipient and exact-content deduplicated.
Raw observations remain accessible; a hook emission is not acknowledgement or
comprehension. Dataset/dataframe caching is not implicitly introduced.

Only successful complete Bash executions create candidates. Native overflow
previews are pointers; bounded immutable snapshots of the original tool-results
file are separately readable. Observation reads support `start/end` or bounded
`start/limit`. Candidate reads require contiguous input/output access by the
current lead. Unchanged candidates retain access; changed interpretations require
fresh review and changed snapshots require fresh selection. Duplicates do not vote.
Consistency is not correctness, and missing candidate coverage remains unknown.

MCP tool failures and failed audit writes do not kill unrelated stdio requests.
Errors expose sanitized metadata, not unexpected exception payloads; process
interrupts still propagate. Capture degradation is explicit, not a successful gate.
Sleep guards reject only explicit lead agent-wait placeholders after observed
worker shutdown, never actual computation/resource waits or unknown running work.

## Compute And Admission

[Full-scale operation](fullscale-infra.md) owns durable claims, accounting,
resource telemetry, recovery and manifest rules. The explicit CPU8/thread4 profile
is `cpu8-infra-protocol.json`; planning remains nonexecuting and is not authorization.
Eight solver jobs means eight total, not eight per condition.

`--compute-threads` is frozen and bounded by CPU quota. It controls per-process
numerical library limits, not a global worker budget. More CPUs cannot supply
missing physical models or shorten provider generation. No model/package installation
is inferred from task content.

`--require-module NAME` requires a successful import, not merely a discoverable
spec. Explicit `--capability-probe /absolute/check.py` assertions run in a
network-disabled preflight container with input mounts and no provider key.
Probe source/digests are frozen; each has a 60-second deadline. These are offline
checks, not installers, inferred task requirements or evidence of solvability.

Web-enabled tasks use [web-v5 transport](web-infra.md): GET and DNS both use the
private Mac/Clash route, with no direct/provider-fetch or server-DNS fallback.
Native model/search/judge APIs remain server-direct.

## Verification And Limits

Current maintenance receipts are under
`/home/zhoujunye/mas-data/receipts/maintenance-20261110/`.
Fresh FULL/OBS raw proofs are in `native-evidence/` under that maintenance root.
The preceding `clash-dns-20261110-01/native-proofs-with-read/` retains proof
summaries only; superseded synthetic payloads were cleaned.
Always validate the requested mode, configuration hashes, effort, image and binary;
a historical passing proof is not admission for changed code.

The [November 10 audit](full-infra-20261110.md) records the paid capture check,
DNS-policy diagnosis, deployed repairs and 900-test pre-cleanup regression.
Synthetic native proofs verify mechanics with fake provider responses, not model
uptake or benchmark-wide gains. Latest regression/probe receipts and frozen paid
sources are retained; superseded offline workspaces and duplicate logs are disposable.
