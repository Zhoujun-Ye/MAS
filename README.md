# MAS Information

Research workspace with four adapters for two external CLIs, not an embedded agent runtime.

## Active Conditions

- **Single:** `deepagents-code==0.2.2` (`dcode`), with native delegation denied,
  MCP/interpreter/extensions disabled, and an explicit 500-turn limit.
- **Agent Team:** Claude Code `2.1.225`, using an interactive terminal, native
  named teammates and native messaging. Print-mode subagents are not this baseline.
- **Subagents:** the same Claude Code `2.1.225`, using native print-mode Agent
  subagents, with Agent Teams explicitly disabled in settings and environment.
- **Claude Single:** Claude Code `2.1.225` in print mode, with delegation tools
  removed/denied, a native permission guard, and zero-worker evidence checks.
- **Scoring:** scale-aware V3 final-answer metrics. Original upstream scores
  remain available for reproduction; frozen experiments are never rewritten.

All conditions use externally installed CLIs. No upstream runtime is cloned,
vendored or imported as an SDK. Deep Agents subagents from older studies are not
the current Single condition. See [CLI contracts](docs/cli-adapters.md).

## Code Layout

- `harness/`: native CLI arguments, hooks, version checks and process transport.
- `harness/claude_code_agent_team/` and `harness/claude_code_subagents/`: distinct
  native Claude modes, sharing only argument/recording helpers.
- `harness/claude_code_single_agent/`: isolated native strict Single adaptation.
- `benchmarks/kramabench/`: pinned task data, versioned metrics and explicit judge.
- `scripts/kramabench/run.py`: one plan/freeze/execute entry point per backend.
- `scripts/kramabench/cli_runtime.py`: benchmark container/artifact/evidence helpers.
- `scripts/kramabench/rescore_native.py`: immutable offline scoring overlays.
- `scripts/kramabench/results.py`: checked 104-task publication and replacements.
- `scripts/kramabench/native_evidence.py`: read-only native transcript/checkpoint readers.
- `analysis/`: generic utilities and read-only historical-schema readers.

Old six-task, dual-backend and one-off continuation launchers have been retired.
Their exact sources remain in archives and frozen run snapshots, not active
imports. The custom Single/Team runtime, provider relay, role catalog and custom
agent scheduler remain retired. [Retention details](docs/archive.md).

## Plan A Benchmark

Run from an explicitly synced source checkout on the server, not locally.
Existing data, images and CLI installations must already be available.

```sh
.venv/bin/python scripts/kramabench/run.py \
  --backend deepagents --upstream benchmarks/kramabench/upstream \
  --output outputs/FRESH-RUN --offline-proof SINGLE-GUARD-PROOF.json \
  --judge-limit 10
```

Use `--backend claude-code-agent-team` with its offline terminal proof for Team,
or `--backend claude-code-subagents` with its offline native Subagents proof.
Use `--backend claude-code-single-agent` with its offline native denial proof
for the new Claude Single condition. It is not an alias of Subagents.
Repeated `--task-id` selects a subset; otherwise all 104 pinned tasks are selected.
Default judge limit is zero. Each selected task gets one attempt, with no automatic
retries. Only a separately authorized study may use `--from-plan --execute`.
Preflight may inspect native versions/help and existing containers but makes no
model calls. Planning does not read provider credentials.

The runner requires native/artifact admission evidence before parallel dispatch.
Agent tools, contexts, communication and scheduling remain the native CLI's job.
CLI exit, native Stop or enabled flags alone do not establish task correctness.

## Results

Completed four-condition snapshot (2026-11-03):
[`outputs/current/comparison-4way/REPORT.md`](outputs/current/comparison-4way/REPORT.md),
with artifact-bound rows and provenance in its `summary.json`.
Each condition selects the same 104 KramaBench tasks, uses DeepSeek Flash and
local `scale_aware_v3` scoring. Binary accuracy covers 84 tasks; the other 20
retain continuous metrics and are not folded into an overall accuracy.

| Metric | Deep Agents Single | Claude Single | Claude Subagents | Claude Agent Team |
| --- | ---: | ---: | ---: | ---: |
| Binary success | 55/84 (65.48%) | 60/84 (71.43%) | 59/84 (70.24%) | 61/84 (72.62%) |
| Easy binary success | 28/35 | 31/35 | 30/35 | 31/35 |
| Hard binary success | 27/49 | 29/49 | 29/49 | 30/49 |
| Normal CLI exit | 104/104 | 104/104 | 104/104 | 104/104 |
| Matching offline replay | 104/104 | 104/104 | 104/104 | 104/104 |
| Mean CLI seconds | 161.1 | 248.7 | 435.6 | 914.3 |
| Median CLI seconds | 103.1 | 142.6 | 322.3 | 798.1 |
| Token-weighted cache reuse | 97.61% | 97.28% | 96.10% | 95.60% |
| Solver USD estimate, off-peak / peak | 1.563706 / 3.127412 | 2.974133 / 5.948266 | 8.593499 / 17.186998 | 18.560251 / 37.120503 |

| Answer Type / Metric | Tasks | Deep Agents Single | Claude Single | Claude Subagents | Claude Agent Team |
| --- | ---: | ---: | ---: | ---: | ---: |
| numeric_exact / success | 54 | 0.611111 | 0.648148 | 0.629630 | 0.648148 |
| string_exact / success | 20 | 0.750000 | 0.850000 | 0.850000 | 0.850000 |
| string_approximate / semantic verdict | 10 | 0.700000 | 0.800000 | 0.800000 | 0.900000 |
| list_approximate / approximate F1 | 2 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| list_exact / F1 | 12 | 0.805556 | 0.930556 | 0.930556 | 0.930556 |
| numeric_approximate / RAE score | 6 | 0.918708 | 0.958317 | 0.917294 | 0.917282 |

Both Single conditions have native zero-subagent evidence for all 104 selected
attempts. Subagents used native workers in 104/104 tasks, with 180 starts and
104/104 lifecycle checks passing. Lifecycle checks and successful replay do not
establish scientific-method correctness.

**Limits and accounting:**

- Team is **99 original + 5 repaired**, not a fresh uniform 104-task rerun.
  All five specified repairs replace their predecessors, not best-of selection.
- Costs above cover retained solver messages for selected artifacts, exclude
  semantic judges and superseded attempts, and are estimates, not invoices.
  Linked solver attempts are 105 / 104 / 104 / 109 in table order. Each condition
  also used ten semantic judges. Failed and superseded expenditure is retained
  in the source receipts and three-way accounting report.
- Claude Single's account-wide solver interval was CNY 39.45; its ten-judge
  interval displayed CNY 0.00, which does not establish free judging. Account
  intervals may include other use; overlapping intervals cannot be summed or
  attributed as backend bills. Missing request/helper accounting is unknown.
- Native contexts, prompts and tool policies differ. These are descriptive
  results, not evidence of causal architecture superiority or significance.

Raw selected evidence remains on the server under `outputs/current/`; historical
failed runs and frozen sources remain in archives. The local four-way report is
a copy of the completed server publication, not a new evaluation.

[Benchmark scoring and reporting](docs/kramabench.md) |
[CLI contracts](docs/cli-adapters.md) | [Historical retention](docs/archive.md)

## Verification And Operations

Tests run on the server with offline fake CLIs and existing dependencies. Inspect
CPU/process ownership first. Use `scripts/server/sync.sh` for scoped source only,
never `--delete`, credentials, outputs, environments or assets. Local edits do
not deploy or clean production server source. New installs and paid runs require
explicit authorization; old no-cap permission is not continuing permission.
