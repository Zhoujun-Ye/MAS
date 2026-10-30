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
  `harness/communication.py` holds the shared handoff contract. A bounded paid
  pilot driver requires explicit authorization; do not expand or replay it
  automatically. Historical comparisons describe removed implementations.
- Generic agent/client/trace/accounting/cache infrastructure remains. Explicit
  telemetry now separates leader, worker and handoff calls.
- Generic Leader decomposition and frozen-plan persistence live in
  `harness/planning.py`; Leader has no domain tools. `harness/information.py`
  provides private-by-default evidence, artifacts, memory/state revisions, ACLs
  and integrity-checked workspace recovery. Shared storage is not shared context.
- BCP adapts this generic architecture. TravelPlanner source, launchers, optional
  dependencies and tests are retired; historical evidence and outputs remain.
  Semantic-loss judging, causal replay and the updater are still pending.

## Design

- [Architecture audit and cache-aware target](docs/leader-led-team.md)
- [Information Harness and hard boundaries](docs/information-harness.md)
- [Information exchange and evolution protocol](docs/communication-policy.md)
- [Benchmark screening and admission gates](docs/experiment1.md)
- [Benchmark directory status](benchmarks/README.md)
- [Historical engineering evidence](docs/engineering.md)
- [Decision-level information feedback](docs/information-feedback.md)
- [Common completion protocol](docs/completion-protocol.md)
- [BCP tool adaptation and evaluation](docs/bcp-adaptation.md)

Current candidate: BCP; DSBench remains deferred. TravelPlanner is retired. Offline
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
.venv/bin/python scripts/browsecomp_plus/offline.py --output outputs/browsecomp_plus/NEW_OFFLINE_RUN
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

Extract decision-time evidence, delivery/read receipts and excerpt checks without
model calls (semantic attribution stays unknown until reviewed):

```bash
.venv/bin/python scripts/feedback.py EXISTING_RUN --report-dir NEW_FEEDBACK_DIR
```
