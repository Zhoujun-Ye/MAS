# Retention And Cleanup

The user authorized deleting obsolete results, source and offline iterations
without result backups on November 7, superseding earlier retain-all-history
instructions. Later run-specific authorizations below remain protected.

## Paid Evidence

All output prefixes below live under `/home/zhoujunye/mas/outputs/`; frozen
sources live under `/home/zhoujunye/mas-stages/`.

| Output Prefix | Frozen Source | Retained Scope |
| --- | --- | --- |
| `krama-cpu8-paired-20261106-03` | `20261106-krama-cpu8-paired-repaired-03` | 40 original attempts, original failures and primary effective report/export |
| `krama-cpu8-paired-20261106-03-upstream-recovery-01` | `20261106-krama-upstream-recovery-01` | Three once-only upstream-503 replacements, original accounting and claims |
| `krama-infra-smoke4-20261107-01` | `20261107-krama-infra-smoke4` | First eight-attempt comparison, reports and accounting |
| `krama-infra-smoke4-20261107-02` | `20261107-krama-infra-smoke4-02` | Second eight-attempt comparison, reports and accounting |
| `threebench2-engineering-20261107-01` | `20261107-threebench2-engineering-01` | Twelve attempts, timeouts, grades and accounting |
| `hdr2-network-20261107-01` | `20261107-hdr2-network-01` | Four-attempt networking retest and receipts |
| `threebench2-20261109-01` | `20261109-threebench2-01` | Eighteen attempts; original SQL grading failures and separate deterministic regrades |
| `full-infra-paid4-20261110-01` | `20261110-full-infra-01` | Four FULL attempts in three benchmark directories, two paid grades, no retries |
| `fdabench-single-structured-smoke4-20261110-01` | `20261110-fdabench-single-structured-smoke4-01` | Eight completed choice attempts, offline grades, actual 2-CPU/thread1 diagnostic profile; no retries or paid judges |
| `fdabench-single-structured-smoke4-20261110-02` | `20261110-fdabench-single-structured-smoke4-02` | Eight CPU8/thread4 attempts and offline grades, including two missing-SessionEnd audit exceptions; no retries or paid judges |
| `threebench-infra-20261111-01` | `20261111-threebench-infra-01` | Twelve authorized Single/Structured slots across three benchmarks, including any failures/incomplete results; no retries or paid judges |
| `threebench-infra-20261111-01-unstarted-01` | `20261111-threebench-infra-01` | First dispatch of the one zero-call TLS-blocked slot from the same twelve-slot authorization; no started attempt replay or paid judge |
| `krama-random20-20261111-01` | `20261111-krama-random20-fixed-01` | Sixty finished solver slots, including seven timeouts and three native audit exceptions; five semantic judges, no retries; thinking off, temperature zero, reviewed shared tool surface; preserve every attempt and frozen source |
| `krama-random20-20261111-02` | `20261111-krama-random20-02` | Newly authorized sixty-slot Single/Native/Structured run from commit `642a6dd`, same frozen twenty questions, concurrency sixteen, CPU8/thread4, at most six semantic judges and zero retries; independent detached run, not replacements for `-01` |
| `krama-loop-pilot-20261111-01` | `20261111-loop-guard-pilot-01` | Nine authorized Structured solver slots: three fixed questions times observe/warn/worker-stop, 900s each, concurrency three, CPU8/thread4, no retries or paid judges, CNY50 planning budget; preserve all attempts, source/proof/input bindings and incurred accounting, including any budget stop |
| `krama-temperature1-pilot-20261112-01` | `20261112-temperature1-pilot-01` | Three authorized Structured solvers, thinking off/T=1.0, loop observation only, 900s, concurrency three, CPU8/thread4, no retries or paid judges, independent CNY20 budget; preserve all attempts, frozen source, admission proofs and accounting |

Preserve raw attempts, submissions, ledgers, incurred costs, frozen settings,
admission proofs, source and result reports, including failed/incomplete work.
Use authorized upstream recovery as the same task's primary replacement, never
best-of selection; retain both attempts' costs. A lifecycle failure alone does
not authorize a retry. Retired FULL/OBS artifacts are read-only history; their
runtime is removed from active source, not from frozen paid provenance.

Keep current trajectory/diagnostic summaries and the latest native, credential,
container, resource, manifest and transport verification receipts. The November
10 paid stage remains on web-v4; later web-v5 DNS/read repairs are not retroactive.
The current review-fix receipts are `review-fixes-20261111-01/`; see the
[verification record](studies/infra-review-fixes-20261111.md). The retained source
target is not itself evidence of a paid launch: use its output authorization,
driver status and host request ledgers for actual dispatch state.

## Protected Runtime

Datasets/checkouts, the evaluation environment, existing environments and required
Docker images, mode-0600 credentials, frozen Validation20 IDs/hashes and unrelated
user work are not cleanup targets. FDABench preparation inputs/receipts stay
protected. Never touch `/home/zhoujunye/agent-team` or rewrite Git history.

On November 11 the user conditionally authorized retirement of unused old MAS
images after validating their SQLite/PDF-capable replacement. This supersedes
old-image retention only. Keep historical image IDs, build receipts, frozen
sources and paid traces; never prune other projects' images or required shared layers.
The accepted November 11 replacement is the `20261111-sqlite-v2` shared image.
Six obsolete MAS tags (four image IDs) were removed; no old image had a container
reference. `threebench-infra-20261111-01/old-image-retirement.json` records the
exact tags, IDs, retained layers and Docker results. Regenerable SQLite source
expansions and current project bytecode/test caches were also removed: 2,440 files,
156,746,045 logical bytes. The official source archive, Dockerfiles, build logs,
package/environment receipts and paid sources/results remain. Exact paths and
hashes are in that receipt root's `cleanup.json`; no global Docker prune was used.

Keep the local `io.mas.web-tunnel` launch agent, installed private runner/VPN/DNS
helpers, control directory and owned live server sockets. Runtime caches are
not interchangeable with disposable project bytecode.

## Disposable Material

- Retired executable workflows/readers and tests solely for those retired formats.
- Superseded offline source stages, synthetic workspaces, duplicate logs/test XML
  and regenerable source caches, once current replacements are verified.
- Duplicate generated metadata outside environments, after checking ownership.

Do not create backups of deleted result payloads. Snapshot overlapping uncommitted
source before removing it; Git alone does not preserve that work. Keep a bounded
source snapshot separately, not another copy of old results.
Source sync uses `scripts/server/sync.sh`, never `--delete`. Remote source removal
uses an explicit reviewed path list and cannot follow symlinks into protected data.
Frozen paid stages/outputs are not modified to match current source.

## Maintenance Receipts

Receipts under `/home/zhoujunye/mas-data/receipts/` record exact paths, byte counts,
hashes and scope rather than deleted payload copies.

| Maintenance | Evidence | Historical Verification |
| --- | --- | --- |
| November 7 retirement/infra cleanup | `maintenance-20261107/`, `local-web-pipeline-20261107/cleanup.json` | Exact deleted paths and protected-file digests in receipts |
| November 9 deep cleanup | `maintenance-20261109/cleanup.json`, `post-test-caches.json` | 1,539 files / 17,295,393 bytes removed; 31,906 protected entries unchanged |
| November 10 deep cleanup | `maintenance-20261110/` | 2,006 files / 35,056,138 bytes including the post-test sweep; 34,355 protected entries unchanged; 905 tests passed |
| November 10 FDABench completion/final cleanup | `fdabench-infra-20261110/background-mirror05/final-audit.json`, `maintenance-20261110-final-cleanup/cleanup.json` | 7,549 entries / 293,023,135 bytes removed; 34,581 protected entries unchanged; 936 tests passed |
| November 11 authorized repo/server cleanup | `maintenance-20261111-cleanup/` | Server: 19,026 entries / 853,059,024 bytes removed, 38,343 protected entries unchanged. Local temporary copies: 153 entries / 26,944,152 bytes removed, 168 protected entries unchanged |
| November 11 random20 preparation cleanup | `krama-random20-preparation-20261111-01/cleanup.json` | Removed five byte-identical generated report copies (304,578 bytes) and the superseded unpaid two-condition stage/receipts; 35,521 protected regular files rehashed unchanged |
| November 11 release cleanup | `maintenance-20261111-release-cleanup/` | 9,631 entries / 385,739,781 regular-file bytes removed; all 37,133 protected entries unchanged; 897 tests, nine synthetic workflows and sixty task preflights passed, zero paid calls |

Historical receipts retain failed checks and successful replacements. The first
random20 cleanup verifier mistook sixteen special paths for regular files; the
replacement rehashed 35,521 regular files and checked the special paths remained.
Their target identity was not hash-compared. The earliest superseded random20
preparation lacked per-tree deletion counts; these remain unknown.

Generated report JSON was removed only where byte-identical canonical exports
remain. Local `outputs/` contains small retained paid reports without exact
duplicates. Raw paid evidence and frozen paid source were not deleted. Earlier
Krama pages are consolidated in [Krama history](studies/krama-history.md); old
host request-reservation code was unused and removed, not replaced by a scheduler.

Current cleanup consolidates no-model container preflight under one runtime
owner and removes active reconstruction of retired decision-gate scores. Read-only
historical analysis remains. Superseded unpaid max-profile stages and synthetic
workspaces were removed after the thinking-off replacement was verified. The
120 repeated preflight source archives were content-checked against their source
manifests; one latest archive remains alongside the recorded source stages,
plans and checks. Latest proof, workflow, CPU and preflight evidence and source
provenance remain. The two feasibility probes keep their proofs and host ledgers,
not their superseded synthetic workspaces. Production runtime source was not
deployed or rewritten, and no paid experiment was launched. Exact
paths, hashes and verification are recorded in
`/home/zhoujunye/mas-data/receipts/maintenance-20261111-release-cleanup/`.

Historical test counts and retired-condition probes are not present-day admission
or speed claims. Current contracts live in [Repository Layout](repository-layout.md)
and [Active Infra](studies/evidence-infra.md).
