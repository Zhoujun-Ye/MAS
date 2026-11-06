# Repository Ownership

This is the current source map, revised 2026-11-05. Historical receipts and study
documents retain the paths used when they were produced.

| Owner | Contents |
| --- | --- |
| `common/` | Domain-independent JSON persistence and canonical fingerprints |
| `harness/` | Native adapters, hooks, Shared Evidence Workspace, containers, tools, credential transport and execution provenance |
| `benchmarks/` | Task loading, references, grading contracts and benchmark policy |
| `analysis/` | Read-only evidence interpretation and aggregate statistics |
| `scripts/<benchmark>/` | Benchmark execution entrypoints and workflows |
| `scripts/common/` | Shared experiment workflows and frozen prompt composition |
| `scripts/studies/` | Research experiment protocols and matrices |
| `scripts/probes/` | Offline/native integration verification entrypoints |
| `scripts/server/` | Server/source/data provisioning and operational entrypoints |
| `tests/` | Behavioral tests, fake runtime fixtures and ownership checks |
| `docs/` | Current architecture/operations; `docs/studies/` holds study designs and receipts |
| `outputs/`, `archives/`, `.retired_sources/` | Ignored results and retained historical evidence, not active imports |

## Dependency Rules

- `common` cannot import harness, benchmarks, analysis or scripts.
- Harness cannot import benchmark implementations or scripts. Experiment prompt
  functions are imported by runners directly, not re-exported from runtime.
- Benchmarks cannot import executable scripts.
- Scripts compose libraries and experiment policy; general-purpose implementations
  are not copied into multiple runner directories.
- Existing frozen solver prompt paths and text remain unchanged. Prompt selection
  is experiment policy, not a runtime feature.

`tests/test_benchmark_layout.py` checks these import boundaries and checks that
relocated modules have one owner, with no obsolete forwarding copies.

## Relocations

| Previous source | Current owner |
| --- | --- |
| `benchmarks/_io.py` | `common/io.py` |
| `scripts/common/runtime.py` | `harness/runtime_support/runtime.py` |
| `scripts/common/timeouts.py` | `benchmarks/policy.py` |
| `scripts/common/{tools,credential_gateway,gateway_bridge,proof}.py` | `harness/runtime_support/` |
| `scripts/server/benchmark_matrix.py` | `scripts/studies/benchmark_matrix.py` |
| `scripts/server/offline_benchmarks.py` | `scripts/probes/offline_benchmarks.py` |
| `scripts/server/offline_gateway.py` | `scripts/probes/offline_gateway.py` |

Imports, executable commands, package discovery and source sync include the new
owners. No baseline model settings, budgets, scoring semantics or prompts change.
The pre-cleanup working source was preserved at
`/tmp/mas-before-repo-classification-20261105.tar.gz` before edits. No historical
outputs, assets, credentials, environments or retained source stages were deleted.

Validation takes place in the isolated server source stage
`/home/zhoujunye/MAS-information-stages/20261105-repo-classification`, not by
silently deploying over the active server repository.

Verification: 448 server tests passed in 12.87 seconds. Native Claude 2.1.286
full/observations-only probes both passed using a fake provider (19/14 synthetic
requests, zero paid calls); receipt:
`/home/zhoujunye/MAS-information-data/receipts/shared-evidence-classification-20261105/summary.json`.
Probe containers were removed. Frozen baseline adapters and Lead prompt were not
changed. Results establish relocation/integration correctness, not accuracy gains.

## Cleanup And Deployment

On 2026-11-05, the current working source (including explicit decision FULL/OBS
studies) was backed up locally at
`/tmp/mas-before-cleanup-20261105-source.tar.gz`. The previous active server source
was backed up at `/tmp/mas-before-cleanup-20261105-server-source.tar.gz` on the
server before source-only synchronization to `/home/zhoujunye/mas`.

The active server tree passed all 546 offline tests in 15.79 seconds. No paid
benchmark, judge or native-provider validation was run in this cleanup. Generated
Python/pytest caches and empty legacy `configs`/`.cache` directories were removed;
the active source inventory had no server-only files. Historical outputs, retired
source snapshots, datasets, environments, package metadata and Docker images were
preserved. This verification does not establish FULL/OBS accuracy improvements.
