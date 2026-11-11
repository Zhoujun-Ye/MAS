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

Preserve raw attempts, submissions, ledgers, incurred costs, frozen settings,
admission proofs, source and result reports, including failed/incomplete work.
Use authorized upstream recovery as the same task's primary replacement, never
best-of selection; retain both attempts' costs. A lifecycle failure alone does
not authorize a retry. Retired FULL/OBS artifacts are read-only history; their
runtime is removed from active source, not from frozen paid provenance.

Keep current trajectory/diagnostic summaries and the latest native, credential,
container, resource, manifest and transport verification receipts. The November
10 paid stage remains on web-v4; later web-v5 DNS/read repairs are not retroactive.

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

The November 11 sweep removed reviewed obsolete temporary source/test trees,
one unused offline stage, superseded synthetic payloads and current-source caches.
It retained valid tests/docs, every paid output and frozen source, active data and
environments, credentials, the current image and private web-tunnel state. Local
temporary FDABench release copies were hash-matched to canonical server inputs
before removal. No paid calls, result backups or global Docker pruning occurred.
The server's complete offline suite passed (838 tests in 44.02 seconds); its XML
is retained in the maintenance receipt root. Newly generated test workspaces and
current-source caches were then removed separately, without counting them toward
the pre-existing material removed above. All 31 tracked Markdown files passed a
relative-link check. No executable behavior or baseline prompt was changed.

The later random20 preparation removes only duplicate `*-report/summary.json`
files whose byte-identical canonical top-level exports remain; the report Markdown,
CSV, comparison data, raw paid attempts and frozen paid stages stay intact. The
local small retained reports have no exact duplicate files and are unchanged.
The superseded `20261111-krama-random20-01` source stage and
`krama-random20-20261111-01` receipts were unpaid preparations, not interrupted
solver attempts. Their seed and exact selection were verified against the new
committed manifest before deletion. Per-tree byte/file counts were not persisted
before removal and remain unknown, not reconstructed estimates.
The first cleanup verifier incorrectly treated sixteen recorded special paths as
regular files. Its error is retained; subsequent verification rehashed all 35,521
regular files and confirmed the sixteen special paths still present. Their target
identity was not hash-compared by the original snapshot. None was a deletion target.
New synthetic task preflights stay under the preparation receipts, not `outputs/`;
there is no paid random20 output or new model charge. Current runtime resources,
Validation20, credentials and the installed private tunnel are not cleanup targets.

The subsequent requested deep source cleanup consolidates four overlapping
historical Krama pages into `studies/krama-history.md`, removes stale executable
contract instructions from active docs, and keeps the frozen paid originals.
Current-result summaries link to that authoritative history rather than repeat
its ledgers. Generic request/timing analysis is shared by current and historical
reports. The unused host `RequestBudget` reservation module and its gateway
callbacks/tests are removed; no active runner supplied it. Native CLI budget
flags, balance/reserve admission and the shared web-call limits are not removed.
Superseded unpaid synthetic/test payloads are disposable after final validation;
latest proof/workflow/preflight summaries and current source provenance remain.

Receipts retain original failed checks as well as successful replacements: the
November 10 web probe first failed closed, and the final cleanup's first test run
hit Unix-socket path-length limits before a short-path run passed. Historical test
counts and retired-condition probes are not present-day admission or speed claims.
Current ownership and operational contracts are in
[Repository Layout](repository-layout.md) and [Active Infra](studies/evidence-infra.md).
