# Retention

On 2026-11-07 the user explicitly requested deleting earlier experiment results,
old records and retired compatibility code, without keeping result backups.
This supersedes the previous retain-all-experiments policy.

## Retained Experiments

Keep server output entries belonging to
`krama-cpu8-paired-20261106-03`, including its original 40 attempts, the three
authorized upstream recoveries, primary effective report/export, frozen settings,
source and accounting. Original failures are evidence of this retained run;
replacement results are primary, not best-of selected. Do not change original
scores or silently discard costs.

Subsequent run-specific authorizations added `krama-infra-smoke4-20261107-01`
and `krama-infra-smoke4-20261107-02`. Keep both batches, their comparisons,
reports, accounting and frozen paid source stages. They are the before/after
engineering comparison, not redundant copies of the twenty-question batch.

The user subsequently authorized `threebench2-engineering-20261107-01` (three
benchmarks x two frozen tasks x Structured/FULL). Preserve its raw attempts,
accounting, report and frozen source `20261107-threebench2-engineering-01`.
This authorization does not permit automatic retries. See
`studies/threebench2-engineering.md` for scope and engineering verification.

Keep `hdr2-network-20261107-01`, frozen source `20261107-hdr2-network-01` and its
export in `mas-data/receipts/hdr2-network-20261107-01`. It is the authorized four-
solver same-task networking retest, not disposable offline output. No retries
were authorized. See `studies/hdr2-network.md`.

Retain the current trajectory diagnosis and current infra validation receipts.
Keep latest successful native/baseline/credential proofs, compute and OOM checks,
full manifests and recovery/admission tests. Superseded offline probe traces and
duplicate iteration logs may be removed; a concise failure summary is sufficient
for a superseded synthetic probe, not for a paid failed attempt.
The only old decision-protocol reader is read-only decision-v3 support necessary
to analyze this retained run; it is not a launch option. Historical ledger,
retired adapter readers and old study-specific replay/regrading drivers are not
active infrastructure.

## Protected Runtime Inputs

Keep current benchmark datasets/checkouts, environments, credentials, required
Docker images, the frozen Validation20 ID/hash manifest and unrelated user work.
Never touch `/home/zhoujunye/agent-team`. Result cleanup does not authorize new
paid execution, provisioning, package installation or rewriting Git history.

## Disposable Material

Earlier output batches/reports, retired source trees, obsolete stages and their
experiment-only receipts are deleted rather than moved into new archives.
Source bytecode and parsed-output caches are regenerable. Deletion receipts
record paths/counts/bytes and retained-artifact hashes, not copies of removed
result payloads. Scoped source sync never uses `--delete`; remote retired files
require an explicit deletion allowlist.

## Maintenance Evidence

Earlier retirement/deletion receipts remain under
`/home/zhoujunye/mas-data/receipts/maintenance-20261107/`. Retired grading-recovery,
score-migration and pre-journal continuation workflows are not restored. Active
numeric, journal, crash and unknown-accounting regressions remain useful.

The local-network pipeline cleanup removed 1,387 files / 11,464,666 logical bytes:
three obsolete offline/interrupted stages, superseded synthetic workspaces and
test logs, source caches and the consolidated external-infra document. The unused
Tavily/advisory-ledger and direct/provider-fetch alternatives and their dead-only
tests were removed. The active preflight/cache contract is in `studies/fullscale-infra.md`.

Current receipt:
`/home/zhoujunye/mas-data/receipts/local-web-pipeline-20261107/cleanup.json`.
All 23,450 protected paid/provenance files (1,539,573,641 logical bytes) have the
same aggregate path/content hash before and after cleanup. No result backup was
created. Temporary source-only snapshots preserve overlapping uncommitted work.
The old discarded batch's minimal 97-request audit and input-hash timing remain
in `dc-hdr-infra-20261107`; no deleted paid calls are described as zero-cost.

Keep the installed local `io.mas.web-tunnel` launch agent, its private runner and
control directory, the server's private live proxy socket, and the current
pipeline/probe receipts. These are runtime resources, not disposable caches.
Post-cleanup server regression passed 725 tests in 32.22 seconds without skips.

The subsequent authorized review closure removed the final retired CooperBench
upstream checkout (1,323 files / 15,245,931 logical bytes) and both empty source
parents, without backups or changes to retained paid evidence. The deletion
receipt, current-source FULL/OBS synthetic proofs and refreshed `web-v4` full
manifest are under `mas-data/receipts/infra-review-closure-20261107/` on the server.
See `studies/infra-final-audit.md` for the 756-test regression and scope.
