# Script Ownership

These are execution workflows and entrypoints, not a home for reusable runtime
implementations. See `docs/repository-layout.md` for the full dependency boundary.

| Directory | Purpose |
| --- | --- |
| `<benchmark>/` | Catalog, run, score, preparation and benchmark-specific replay |
| `common/` | Shared experiment workflow composition and frozen prompt selection |
| `studies/` | Frozen manifests, bounded matrices, journal recovery and current reports |
| `probes/` | Explicit offline/native runtime verification commands |
| `server/` | Source sync, environment/data preparation and server operations |

Do not put storage engines, MCP services, tools, gateways or container lifecycle
implementations here. They belong to `harness/`; generic I/O belongs to `common/`.
Server preparation and probes are operational exceptions to "experiment scripts":
they are executable workflows, not library ownership.

Paid smoke work uses the same explicit `studies/benchmark_matrix.py` admission,
claims, limits and accounting as other runs; there is no second fixed-budget
paid smoke launcher. `probes/offline_gateway.py` checks credential transport and
native modes; `offline_benchmarks.py` adds mounted-data/native-budget checks using
the shared standalone `native_transport.py` fixture. `external_workflow.py`
exercises the complete benchmark runner. These complementary checks are synthetic,
not paid solver launch options or evidence of benchmark quality.
