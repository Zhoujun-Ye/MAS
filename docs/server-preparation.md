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
- FDABench (opt-in, local/public-reference scope): `fdabench/upstream`,
  `fdabench/release`, `fdabench/data`; see [FDABench](fdabench.md) for asset receipts,
  missing-input admission and local retrieval limitations. Its preparation does
  not enable cloud databases or add it to the existing Validation20 set.
- Current results: [current-results.md](current-results.md).

Claude Code is pinned to 2.1.286. The current solver image is
`mas/research-benchmarks:20261111-pdf-v1`, ID
`sha256:57a1e27dcdcb49b28d7a0c0e38ec4bde624d3baf32ff9bb006184b3521ff1489`.
It extends the retained November 3 image with Poppler for native PDF reading;
the base image is unchanged and remains required for historical paid provenance.
Build/package receipts are under
`fdabench-single-structured-smoke4-20261110-01/pdf-image-03/` in the receipt root.
All four benchmarks default to 8 CPUs and 4 numerical threads per solver.
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

## Offline Tests

Run the suite on the server with the existing evaluation Python. Unix-socket
fixtures need a short, fresh `--basetemp` under `/tmp/` (for example
`/tmp/mas-pytest-UNIQUE`), not under the long receipts path. Keep logs/JUnit XML
under the external receipts root, and clean only the test-owned workspace after
verification. These offline tests use fake providers and do not authorize paid
experiments or replace native-runtime admission proofs.

## Safety

Keep provider keys host-side in mode-0600 `.env`. Solver containers use
network=none and the per-run Unix credential gateway. Current web-enabled tasks
use DeepSeek search and bounded credential-free host fetch, through the gateway
with a shared success/attempt cap (see `studies/web-infra.md`). Never mount real keys,
reference answers, gold SQL or decrypted evaluator inputs into solver containers.

Use source-only scoped sync, never `--delete`. Check process ownership first;
never touch the unrelated `/home/zhoujunye/agent-team` project or its resources.
Paid calls, provisioning and resource deletion need explicit authorization.
