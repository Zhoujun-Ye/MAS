# Active Evidence Infrastructure

Authorized on 2026-11-07: generic observation/decision repairs, offline validation,
and deletion of older results/retired compatibility code. No paid experiment,
judge or retry is authorized. This source is the future infrastructure, not a
retroactive change to the retained decision-v3 CPU8 results.

## Mechanism Repair

Bounded native hook deltas bring other contexts' newly executed observations
into the lead/worker context without a polling loop. Structured final/intermediate
summaries expose results even when a long tool output places them after the
preview. Full input/output remains available through explicit observation reads.
Compact-delta-v2 updates are capped at three records and 1800 characters (6000
including one-time tool guidance), per-recipient cursors are
transactional, same-worker session changes do not re-deliver its own work, and
overflow is retained for subsequent hooks. Exact input/output/status duplicates
are announced once per recipient but all raw observations remain readable. Parsed
result previews do not also repeat the raw output preview. No background model or custom native
agent scheduler is introduced. Hook emissions and explicit reads have separate
accounting; neither proves understanding.

Decision-v4 exposes typed intermediate contrasts and paginated source evidence.
Conflicting candidates require lead execution-evidence access before selection;
worker reads and previews cannot satisfy that check. New target interpretations
or method variants invalidate old review even if the numeric answer is unchanged.
Duplicate computations do not vote or invalidate a selection. Failures are
audited as sanitized metadata, not silently absent from successful-call counts.
Candidate execution reads count as evidence access in audits; hook previews do
not. Missing comparable evidence is labeled `coverage_unknown`, not a completed
semantic verification.
See [full contract](intermediate-full.md).

Generic guidance asks for actual executed target/unit/population/method contracts,
preserved alternatives and explicit capability gaps. It does not name any task,
answer or reference-specific transformation. No automatic semantic choice or
submission occurs. Singletons retain the no-selection-ceremony behavior; missing
candidate coverage and semantic validity remain unknown. The Structured baseline
text, frozen question IDs and evaluator are unchanged.

## Compute and Admission

The Krama runner and matrix expose `--compute-threads`, bounded by container CPU
quota, frozen alongside source/settings and checked when executing a saved plan.
It controls per-process OpenBLAS/OMP/MKL/NumExpr/Accelerate limits. Library defaults
remain unchanged for existing callers; future CPU8 comparisons should explicitly
record eight CPUs, four compute threads and eight solver jobs total (not eight
jobs per condition), subject to fresh capacity/provider/memory checks and user
authorization. Each native worker is a process; four threads is not a global
container thread budget, and concurrent workers can still oversubscribe.

The canonical explicit profile is [cpu8-infra-protocol.json](cpu8-infra-protocol.json),
used with the generic matrix's matching CLI flags and `--protocol-settings`.
It binds current prompt hashes and resources, not task IDs or answers. Keep
planning nonexecuting; a profile file is not paid-run authorization.

Use repeatable `--require-module NAME` to declare top-level Python module
requirements. Requirements are deduplicated, validated and frozen; missing
requirements fail no-model preflight before paid dispatch. No benchmark-specific
package list, installation, import-based guessing of task needs or environment
mutation is performed. Required modules must now import successfully, not merely
have a discoverable spec. Import failure types are recorded without exception payloads.
For actual model/data functionality, repeat `--capability-probe /absolute/check.py`:
explicit Python assertions run in the no-network preflight container with mounted
inputs and no provider key. Source and digest are frozen in matrix/task plans,
changes invalidate execution admission, and failure/timeout receipts are preserved.
Each check has a 60-second deadline. A probe is operator-supplied executable code,
not inferred from task answers; it must be an offline check, not an installer.
Passing imports alone still does not establish functional model/data availability.

## Follow-up Engineering Boundaries

Batch order remains unchanged. Decision access now requires contiguous full input
and output coverage of at least one execution per conflicting candidate, for the
current lead and candidate review token. Global snapshot changes still invalidate
selection, but do not invalidate complete reads of unchanged candidates. Changed
candidate interpretations/variants require fresh access. Exact `next_read` arguments
and completion status are exposed in view/read and errors. Repeated one-character reads, overlapping pages and
reads from different executions cannot be combined to bypass this requirement.
This proves evidence delivery only, not comprehension or independent premises.

FULL/OBS recognize standalone sleeps and literal sleep-plus-echo placeholders.
They reject a lead placeholder wait described explicitly as waiting for agents
only after native SubagentStop events cover all observed workers and no Agent/Task
launch is pending. Unknown or running workers, compute/polling loops, unrelated
resource waits and worker commands are not blocked. A once-per-context advisory
remains for recognized completed sleep commands. Native scheduling remains external.
No command is shortened, replaced or retried; Structured prompting is unchanged.

Transparent cross-process input caching is deliberately not enabled: workbook
selection, converters, dtypes, indexes and parser options are part of computation
semantics. Observation parsing caches are not dataset loading caches. There is no
claim that repeated pandas/geospatial reads are fixed. Independent worker premise
formation, environment package/model provisioning and new paid runs remain outside
this engineering change. Fresh native proofs are needed for the changed source;
earlier readiness receipts describe the earlier revision, not current admission.

Follow-up server regression: 599 passed in 16.68 seconds (`pytest-followup.txt`).
Pinned native FULL/OBS checks passed with 13/14 fake-provider requests, bidirectional
observation delivery, zero workspace errors and owned containers removed
(`followup-native/summary.json`). The existing image passed imports and a synthetic
numerical functional assertion; deliberately missing modules and failed assertions
returned nonzero, with actual OpenBLAS threads equal to four
(`followup-capabilities.json`). These receipts are under the current infra receipt
directory below. No provider credentials, installations or paid calls were used.
Those follow-up receipts predate compact-delta-v2. Current speed-repair validation,
including native rejection of a completed-worker placeholder wait, is documented
in [full-speed-repair.md](full-speed-repair.md). Real-model speedup remains unmeasured.

Runtime CPU samples retain actual cgroup use and throttling, not just quotas.
Store kind queries filter in SQLite rather than decoding every unrelated object;
parser source digests are cached per process and parse-cache keys reuse blob
digests while original blob integrity is still checked. Sharing is incremental
rather than repeatedly listing/reading the full workspace. More CPU cannot shorten
provider inference/network time or supply missing data/model coefficients.
The retired Responses gateway route and output-item-ID parser were removed;
only native Anthropic and bounded search/fetch routes remain. Non-frozen matrix
sampling now uses one seeded public-strata implementation, with no old two-task
easy/non-web compatibility branch. Frozen manifest selection is unchanged.

## Verification Boundary

The original offline stage `20261107-evidence-infra-v4` was superseded and removed
in the subsequent cleanup. Frozen paid source stages and the current
`/home/zhoujunye/mas` remain; latest infrastructure validation is documented in
[fullscale-infra.md](fullscale-infra.md).
Current offline receipts: `/home/zhoujunye/mas-data/receipts/evidence-infra-v4-20261107/`.
Synthetic regressions cover concurrency, bounded backlog, own-context exclusion,
source/target staleness, evidence access, read pagination, invalid calls, role
guards, frozen thread/dependency requirements and unchanged baseline prompting.
Native fake-provider checks use the pinned CLI and existing network-disabled
image, synthetic keys only, with a hard synthetic request ceiling. They verify
hook data appearing in both lead and worker provider requests, selection access,
and owned-container teardown. They do not establish real-model uptake or score gains.

Fresh native proof configuration hashes are required before any future paid run;
old proofs cannot silently admit this changed FULL implementation. No new paid
quality/performance claim follows from unit tests or synthetic CPU kernels.

## Measured Checks

Active-server regression passed 586 tests in 16.64 seconds, including the two
pinned-upstream scoring integration checks (no skipped tests). Current native
FULL/OBS fake-provider checks passed with 13/14 synthetic requests, both directions
of hook observation delivery visible in actual native requests, and zero workspace
errors. Single/Subagents native baseline checks and credential-isolation probes
also passed; real keys were not loaded into solver containers.

The existing eight-core image verified four actual numerical threads, a present
module returning zero, and a deliberately absent synthetic module returning two.
Serial matrix-multiply median seconds at 1/2/4/8 threads were
0.40465/0.21157/0.10700/0.06923. Four-thread compute was about 3.78x faster than
one-thread compute, not a measured end-to-end model/benchmark speedup.

A real-image/binary/proof readiness plan for the explicit CPU8 profile passed,
created no solver output directory and dispatched no models or judges. Per-task
container/data preflights remain required for future authorized execution.

## Cleanup Receipt

Server `cleanup.json` records deletion of 101,914 files, 7,976,407,132 bytes of
older results, retired source and obsolete experiment stages/receipts. All 13,470
retained output files have identical before/after aggregate path/content hashes.
Local cleanup removed 33 old result/archive files (2,174,815 bytes); the three
local primary report files are unchanged. No old-result backup was created.
Only the current pair's 40 original attempts and three authorized upstream
recoveries remain as experiment outputs. Runtime inputs, environments, credentials
and unrelated projects were not deleted. Retired remote source files were removed
with an explicit allowlist, not `rsync --delete`.
