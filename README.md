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

Retained current snapshot: `outputs/current/comparison/`.
It uses the fresh 104-task strict Single baseline and replaces all five specified
Claude problem cases with their repaired attempts. Original traces and receipts
are retained. The Team result is **99 original + 5 repaired**, not a fresh full
104-task rerun or causal architecture comparison. Failed/superseded attempts
still count toward actual expenditure. Selected raw evidence is under
`outputs/current/evidence/` on the server; older namespaces are relocated into
the recorded output-cleanup archive, not permanently erased. New Subagents
evidence/comparison stays under `outputs/current/`, rather than mixing historical runs.

Completed three-condition comparison: `outputs/current/comparison-3way/`, with
cost/evidence details at `outputs/current/reports/final-three-way-20261103-01/`.
`compare_claude_single.py` adds a finished, verified Claude Single run to that
exact retained comparison without rerunning or rewriting the other conditions.

[Benchmark scoring and reporting](docs/kramabench.md) |
[Audit and experiment history](docs/native-cli-audit-20261102.md)

## Verification And Operations

Tests run on the server with offline fake CLIs and existing dependencies. Inspect
CPU/process ownership first. Use `scripts/server/sync.sh` for scoped source only,
never `--delete`, credentials, outputs, environments or assets. Local edits do
not deploy or clean production server source. New installs and paid runs require
explicit authorization; old no-cap permission is not continuing permission.
