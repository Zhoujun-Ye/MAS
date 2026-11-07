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
