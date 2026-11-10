# Benchmark Contracts

Current ownership and verification boundaries, 2026-11-07. These contracts do
not authorize paid execution, judge calls, environment installation or provisioning.

| Benchmark | Task source | Solver inputs | Evaluation |
| --- | --- | --- | --- |
| KramaBench | Pinned 104-task workload | Read-only public data lake | Versioned numeric/string/list metrics, exported pipeline replay; explicit semantic judge when required |
| DataClawBench | Pinned upstream QA IDs/rubric | Selected read-only database, no QA/gold mount | Adapted tool-free per-part rubric; process metrics remain unavailable |
| HybridDeepResearch | Encrypted 380-task release decoded host-side | Selected read-only SQLite/optional KB, no reference fields | Pinned official SQL evaluator and text judge contract |
| FDABench | Pinned Full release, filtered to local databases and public scoring references | Selected SQLite and separately verified raw corpus/index; no gold or frozen search answers | Exact-set choice accuracy; explicitly authorized adapted report rubric |

Each benchmark owns `tasks.py` and `evaluation.py`, with executable
`scripts/<benchmark>/{catalog,run,score}.py` entrypoints. Shared grading/workflows
belong in `scripts/common/`; runtime/container/proof libraries in
`harness/runtime_support/`; persistence in `common/`; native evidence readers in
`analysis/`. See [repository ownership](repository-layout.md).

## Isolation And Scoring

- Claude Code Single and ordinary Subagents use the pinned external CLI, not a
  vendored runtime. Structured lead organization remains frozen; shared limits
  are stated identically across conditions. FULL is a separate opt-in condition.
- DataClaw/HDR reference answers, gold SQL and decrypted task releases remain
  host-side. Exporting a public manifest exposes IDs and hashes, not those fields.
- Live containers have network none; fixed provider/search destinations use the
  host credential gateway. Credentials never enter solver mounts/environments.
  Same-UID access remains a limitation, not a claimed security boundary.
- Final submissions, grading artifacts and evaluator/source hashes are bound.
  Unknown outcomes and unavailable charges are not zero scores or zero costs.
  Continuous answer metrics are not binary accuracy or scientific-method validity.
- Semantic judges require separate authorization; no implicit replay, unit repair,
  automatic semantic choice, extra solver retry or hidden grading call is allowed.

## Current Readiness

Server assets, environment locations and provisioning receipts are documented in
[server preparation](server-preparation.md). The old pre-provisioning checklist
and deleted temporary-stage verification are no longer active documentation.

The retained paid evidence is the Krama CPU8 pair and two four-task engineering
checks, described in [current results](current-results.md). It does not establish
full-benchmark or cross-benchmark correctness. Offline full manifests verify 104
Krama, 492 DataClaw and 380 HDR tasks without running them.

[Full-scale infrastructure](studies/fullscale-infra.md) owns frozen ordering,
durable crash/grade recovery, balance admission, concurrency and memory/OOM
verification. No document or successful fake-provider check is a paid-run grant.

Benchmark-specific details: [KramaBench](kramabench.md),
[DataClaw/HDR](research-benchmarks.md), [CLI policies](cli-adapters.md),
[timeouts](timeout-policy.md), [retention](archive.md).
