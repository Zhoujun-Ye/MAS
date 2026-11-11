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

| Maintenance | Evidence |
| --- | --- |
| November 7 retirement/infra cleanup | `maintenance-20261107/`, `local-web-pipeline-20261107/cleanup.json` |
| November 9 deep cleanup | `maintenance-20261109/cleanup.json`, `post-test-caches.json` |
| November 10 deep cleanup | `maintenance-20261110/` |
| November 10 FDABench completion/final cleanup | `fdabench-infra-20261110/background-mirror05/final-audit.json`, `maintenance-20261110-final-cleanup/cleanup.json` |

The November 10 cleanup removed 1,989 server files / 34,929,886 logical bytes:
retired source, three obsolete offline stages, source caches, generated root
metadata and superseded zero-paid synthetic payloads/test XML. Proof summaries
and XML suite/failure metadata remain; fresh raw native proofs replace disposable
offline workspaces. All 34,355 paid-output/frozen-source files and symlinks
matched their original path/content hashes afterward. No paid call was made.
The post-test bytecode sweep removed another 17 files / 126,252 bytes: 2,006
files / 35,056,138 logical bytes removed in total.
That source passed 905 server tests; native data/budget, gateway and FULL/OBS
probes passed. The first free web probe failed closed with `proxy_unavailable`;
subsequent direct fetch and complete HTML/JSON probe passed without changing
VPN/Clash/tunnel configuration. This does not establish long-term availability.

The November 9 cleanup removed 1,539 files / 17,295,393 bytes; all 31,906 protected
files had identical path/content hashes afterward. Earlier offline summaries
remain historical verification, not present-day admission or benchmark gains.
Current ownership and operational contracts are in
[Repository Layout](repository-layout.md) and [Active Infra](studies/evidence-infra.md).

The final cleanup followed completed FDABench download/index/catalog audits.
It removed 7,549 disposable cache/synthetic-test entries / 293,023,135 logical
bytes, while all 34,581 protected output/frozen-source entries retained identical
path/content hashes. No paid output, FDABench input/receipt, environment or live
tunnel was removed. Obsolete downloader argument plumbing and repeated preparation
history were consolidated; behaviorally distinct tests and retained reports remain.
The full server suite passed 936 tests. The first invocation's long temporary
directory caused 23 Unix-socket path-length failures; the corrected short-path
invocation passed without suppressing tests. Both invocations' logs/XML remain
in the final cleanup receipts; disposable test workspaces were removed afterward.
