# Repository Ownership

Current source ownership, revised 2026-11-07. The retained paired run keeps its
original artifact paths; obsolete study outputs and compatibility source are removed.

| Owner | Contents |
| --- | --- |
| `common/` | Domain-independent persistence, fingerprints and durable phase claims |
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
| `outputs/` | Retained CPU8 pair and two authorized smoke comparisons; never active imports |

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

## Active Deployment

Canonical source is local `/Users/zhoujun/Desktop/MAS` and server
`/home/zhoujunye/mas`. Reusable runtime code has one owner under `harness/`;
benchmark execution composition belongs to scripts. There are no forwarding
copies for retired module locations. Historical ledger/runtime readers and
study-specific replay/regrading entrypoints were removed.

Source sync is scoped, never `--delete`; retired remote source is removed by
an explicit reviewed path list. See [active infra](studies/evidence-infra.md)
and [retention](archive.md). Environments, current input data and unrelated user
projects are not cleanup targets. Offline tests run on the server; passing tests
or native fake-provider probes are not benchmark quality evidence.
