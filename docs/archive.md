# Historical Evidence

CooperBench was retired from active source on 2026-11-01 at the user's request.
Results remain at `/home/zhoujunye/MAS-information/outputs/cooperbench/` on the server.
Observed directories: `team20-20261030-01`, `team20-20261030-parallel-01`,
`lite100-20261030-03`, `lite100-20261030-04`, `repair-20261031-01`, `lite100-current`.
This is an inventory, not a re-evaluation or endorsement of historical scores.

Archive: `/home/zhoujunye/MAS-information/archives/leader-subagent-20261101/`.

- `server-source-before.tgz`: pre-cleanup server source, configs, docs and tests.
- `local-source-before.tgz`: local equivalent, including pre-existing README/AGENTS
  edits. No credentials, outputs, environments, assets or checkouts are included.
- `results-before.sha256`: per-file checksums before refactoring.
- `removed-source.txt`: exact retired tracked paths used for scoped cleanup.

Results are not moved or rewritten. Historical Docker images, containers, ignored
upstream checkouts and prepared assets are not pruned; they can be needed for audit
and overlap shared resources. No active launcher references them. Reproduce old
studies from archived source, not from the new runtime. Retained run readers
describe historical schemas, not the new study's criteria.

Local follow-up cleanup removed `benchmarks/cooperbench/upstream/` (a clean
checkout) and `.cache/cooperbench-images/` (approximately 59 GiB of downloaded
image caches). The retention statement above applies to server resources; local
historical reports and unrelated caches remain untouched.

Analysis follow-up retired `analysis/criteria.py` (old P1-P4 thresholds),
`analysis/loss_judge.py` (unused model-judge helper), and `analysis/information.py`
(retired peer-team transport/evidence schema), together with `scripts/feedback.py`
and their tests. Historical implementations remain in the source archives above.
`analysis/cache.py` and `analysis/stats.py` remain reusable utilities;
`analysis/runs.py` and `scripts/analyze.py` remain read-only historical report tools
for scheduler-based manifests, not Leader-Subagent session outputs. At the user's
request, this cleanup is also synchronized to server source using explicit paths;
archives and experiment evidence remain untouched.

## Refactor Verification

Server regression: 35 scripted/mock tests passed. The foreground delegation demo
at `outputs/subagent-demo-20261101-01/` completed with zero trace integrity errors.
All files in `results-before.sha256` passed SHA-256 verification after cleanup.
No paid model calls, Docker provisioning or benchmark re-evaluation was performed.

After the analysis cleanup was synchronized, the server regression passed all
92 tests. Historical results again passed `results-before.sha256` verification.
No paid calls or benchmark re-evaluation were performed for this follow-up.
