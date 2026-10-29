# MAS Information: Leader-led Agent Team Study

Target: **Reusable Agent Pool -> Task-Adaptive Selection -> Agent Team ->
Information Exchange -> Task Solution**. Eight worker capabilities plus Leader
are fixed templates. Selection changes members/assignments, not role
prompts or permissions. A leader coordinates multi-worker tasks and workers can
communicate directly. Simple tasks may use one worker without a meta/leader call.

Research focus: information exchange and, only if supported by motivation
evidence, feedback-driven communication-policy updates. Selection is not
self-evolution; team architecture/Blueprint search is outside this study.

## Current Status

- **No main benchmark approved.** Current-model headroom, meaningful team
  dependencies and actual cost must all be established first.
- All old BFCL, ToolHop, BrowseComp-Plus and tau2 adapters/configs/launchers are
  removed. Historical outputs, native assets and server environments remain.
- `harness/pool.py` implements eight worker templates, the Leader template,
  capability bindings, immutable TeamSpec validation and zero-call rule selection.
  `harness/agent_team.py` implements independent persistent contexts, queued peer
  delivery, leader synthesis and five controlled handoff forms. Scheduling is
  bounded round-robin, not simultaneous threads. It does not evolve policies.
- Legacy star/linear runtimes and their obsolete tests have been removed.
  `harness/communication.py` holds the shared handoff contract. No paid launcher
  is enabled. Historical design comparisons describe the removed implementations.
- Generic agent/client/trace/accounting/cache infrastructure remains. Explicit
  telemetry now separates leader, worker and handoff calls.
- TravelPlanner has an active **candidate adapter**, pinned native data/tools,
  direct-JSON native scoring and an unpaid five-arm integration driver.
  Its 60 three-day/single-destination validation tasks are not approved main-study
  evidence: current-backbone headroom and actual model cost remain unmeasured.
  LLM selection, semantic-loss judging, causal replay and the updater are pending.

## Design

- [Architecture audit and cache-aware target](docs/leader-led-team.md)
- [Information exchange and evolution protocol](docs/communication-policy.md)
- [Benchmark screening and admission gates](docs/experiment1.md)
- [Benchmark directory status](benchmarks/README.md)
- [Historical engineering evidence](docs/engineering.md)

Current candidate: short TravelPlanner tool-use tasks; DSBench remains deferred.
See [adapter and server evidence](docs/travelplanner-adaptation.md). Offline
fixture success is not evidence of model success, non-saturation or cache savings.

Motivation freezes one selected TeamSpec per task across five handoff forms;
different tasks may use different teams. Policies stay static during this study.
Routing comparisons and cross-task communication updates are separate experiments,
with full selection/update/inference cost accounting.

## Offline Work

Tests run on the server after process inspection and scoped source sync:

```bash
scripts/server/sync.sh
scripts/server/remote.sh '.venv/bin/python -m pytest -q'
# On the server, after pinned data preparation; use a new output directory:
.venv/bin/python scripts/travelplanner/offline.py --output outputs/travelplanner/NEW_OFFLINE_RUN
```

`scripts/server/setup.sh` installs core dependencies only. The explicit
`scripts/server/retire_bench_sources.sh --apply` archives retired source files
on the server without touching assets/outputs. Sync never uses `--delete`.

Read existing flags/traces/cache telemetry without benchmark imports or grading:

```bash
.venv/bin/python scripts/analyze.py EXISTING_RUN --report-dir NEW_REPORT_DIR
```

This never invents semantic-loss scores or regrades answers. Cost aggregates
cover latest result files only, not additional planning/judges/retry attempts.
