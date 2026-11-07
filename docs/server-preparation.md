# Server Resources

## Active Paths

- Project: `/home/zhoujunye/mas`.
- Compatibility symlink: `/home/zhoujunye/MAS-information` points to `mas`,
  preserving historical absolute artifact paths. External data, environments and
  frozen source stages retain their original directories.
- Data and evaluation: `/home/zhoujunye/mas-data`.
- Evaluation Python: `/home/zhoujunye/mas-data/environments/evaluation/bin/python`.
- Datasets: `kramabench/upstream`, `dataclawbench/upstream`,
  `hybriddeepresearch/upstream`, `hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl`,
  and `hybriddeepresearch/data` under the external data root.
- Current results: [current-results.md](current-results.md).

Claude Code is pinned to 2.1.286. The current solver image is
`mas/research-benchmarks:20261103-v1`, ID
`sha256:f940900759fee9d7f9fcdd819f5fc7062d4b1e11b192355b503ce33511bfa14b`.
The existing KramaBench base image is retained for builds.

## Data And Environment Provenance

- DataClaw source: `32e138750ceba41b47290211403ad1781d5e1971`.
- HDR source: `3523f1da83a0470cdea742ea8b7426e7af6ca89b`.
- Encrypted HDR release: `31304784b7aec82f22d59772a8afeb78567fd8b3`.
- LiveSQLBench DB/KB: `0664a2f28555faa0dd2947c8c23288df79bcc06b`.

External `receipts/data-hydration.json`, data verification and
`receipts/evaluation-requirements.lock` describe data/environment provenance,
not disposable cleanup logs. Runtime-bound native offline proofs are needed
for execution admission; current proof requirements are in [active infra](studies/evidence-infra.md).
No installation or environment change is implicit in these instructions.

## Safety

Keep provider keys host-side in mode-0600 `.env`. Solver containers use
network=none and the per-run Unix credential gateway. Current web-enabled tasks
use DeepSeek search/fetch with a shared request cap. Never mount real keys,
reference answers, gold SQL or decrypted evaluator inputs into solver containers.

Use source-only scoped sync, never `--delete`. Check process ownership first;
never touch the unrelated `/home/zhoujunye/agent-team` project or its resources.
Paid calls, provisioning and resource deletion need explicit authorization.
