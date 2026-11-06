# Native Baselines And Research Benchmarks

## Claude Conditions

The new benchmark runner supports `claude-code-single-agent` and
`claude-code-subagents` using the installed Claude Code 2.1.286. Single removes
and denies delegation; Subagents permits the native Agent tool, including background
agents that notify the lead on completion (2.1.286 has no TaskOutput tool), with
Agent Teams disabled. Interactive Agent Teams is retired, including the KramaBench adapter.

The Subagents baseline uses the fixed current lead prompt in
`harness/runtime_support/runtime.py`. Only native Claude Single and Subagents are active.

Both conditions receive the same shared task rules, ending with a run-limits line:
the wall-clock timeout and, for web tasks, the request budget shared by every agent
and process. The web helper puts `web_budget` (used, limit, remaining) first in each
JSON response. When the budget is gone it prints one final message and exits with
status 3; it never retries.
The organization prompt is not placed in shared worker-visible rule files. Admission
requires observed delegation and completion; non-delegating attempts are retained
as unverified conditions, not silently retried. Task, data-access and submission
requirements are supplied by the benchmark adapter. This is a prompted
Subagents baseline, not an entirely unprompted observation of Claude Code.

Benchmark-specific web permissions replace the original KramaBench-only `/data`
restriction. Historical result artifacts were deleted by user authorization on
2026-11-04; retained source documentation is not a current result. Deep Agents
has been removed from active execution at the user's request; see [retention](archive.md).

## Source Contracts

- [DataClawBench](https://github.com/GTML-LAB-sysu/DataClaw/tree/32e138750ceba41b47290211403ad1781d5e1971),
  pin `32e138750ceba41b47290211403ad1781d5e1971`.
  Read sorted `assets/qa_raw/**/*_result.json`, preserving upstream task IDs,
  question and output guidelines. Generated task markdown contains the gold
  rubric and must never be mounted. Only `assets/database` (or explicitly
  `database_clear`) is mounted read-only. Git LFS pointers are rejected.
  Only `international_comparison` permits web access.
- [HybridDeepResearch](https://github.com/Snowflake-AI-Research/HybridDeepResearch/tree/3523f1da83a0470cdea742ea8b7426e7af6ca89b),
  pin `3523f1da83a0470cdea742ea8b7426e7af6ca89b`.
  Use the [encrypted release](https://huggingface.co/datasets/Snowflake/HybridDeepResearch),
  not the sparse patch or preview unless reproducing historical results. The
  adapter decodes in memory and checks SHA-256, canary and task identity. Only
  final question, optional hint and database name enter the question prompt.
  Gold answers, SQL and search chains remain host-side. Do not publish decrypted
  prompts, submissions or logs. Local evidence directories are private.

HybridDeepResearch databases come separately from
[LiveSQLBench](https://huggingface.co/datasets/birdsql/livesqlbench-base-lite-sqlite).
Expected layout: `DB_ROOT/NAME/NAME_template.sqlite`, optional `NAME_kb.jsonl`.
Only that task's database and knowledge file are mounted, not the surrounding
release directory. This is public SQLite development, not held-out Snowflake
evaluation. Assets/checkouts are external, ignored and never synced as source.

## Planning And Execution

Use the server's existing Python, installed CLI pins and a previously provisioned
image. No automatic downloads, installations, image pulls or environment changes
are performed by these entry points. Current model configuration intentionally
reuses the project's DeepSeek Flash settings; changing provider/model requires
a separately frozen study configuration.

```sh
python scripts/dataclawbench/run.py \
  --upstream /path/to/pinned/DataClaw \
  --data /path/to/pinned/DataClaw/assets/database \
  --backend claude-code-subagents \
  --task-id task_001_comprehensive_decision_easy_easy001 \
  --image EXISTING_IMAGE --output outputs/FRESH-DATACLAW

python scripts/hybriddeepresearch/run.py \
  --upstream /path/to/pinned/HybridDeepResearch \
  --tasks /path/to/hybrid_ds_release.jsonl --data /path/to/sqlite_databases \
  --backend claude-code-single-agent --task-id s2sql_000 \
  --web-search deepseek --image EXISTING_IMAGE --output outputs/FRESH-HYBRID
```

These commands only print plans; they do not create output directories, run
containers, read credentials or invoke models. They validate local inputs and
record source, task, asset, evaluator and rendered-prompt hashes/lengths, native
environment and the exact ordinary condition prompt. Pinned evaluator/QA Git
blobs and inventories must match, not merely the checkout's HEAD label.

Execution additionally requires `--execute --authorized-attempts N
--offline-proof PROOF.json`, exact selected task count and run-specific user
authorization. Proof validation is shared with KramaBench: `passed=true`,
`paid_calls=0`, `network="none"` plus backend-specific native observations.
Single requires delegation denials; Subagents requires observed worker starts
and no Team events. A supplied backend label must match; old proofs without a
label are checked through their backend-specific audit. Solver key comes from the existing mode-0600
credential file. Live web runs use `--web-search deepseek` through the host
credential gateway. The legacy `tavily` choice remains available for planning
and offline fixtures only; paid execution is explicitly rejected because its
credential isolation is not implemented. Search-provider costs are not included in native
model token accounting. `--max-web-requests` bounds paid helper requests and
`--max-budget-usd` forwards the native CLI limit; it is not an invoice guarantee.

Each attempt has a fresh workspace/profile/container. Native policies and
observers are read-only mounts. No permission bypass is added. SQL uses SQLite
read-only mode, query-only, denied ATTACH/extension loading and an operation cap.
Data mounts are read-only. Web restrictions on arbitrary shell commands are
instructions, not an adversarial network sandbox: provider traffic still needs
network access. The explicit helper provides search/fetch with no hidden fallback.

Execution is sequential, one attempt per task, zero adapter retries. A failed
attempt stops later dispatch; skipped tasks remain in `predictions.jsonl` with
empty answers. CLI exit alone is insufficient: native condition evidence and a
valid submission are required. Raw CLI logs/native profiles and submission
hashes are retained; available native usage is read with existing evidence tools.
Unavailable usage/cost is unknown. No solver or judge is dispatched by default.

## Evaluation

```sh
python scripts/hybriddeepresearch/score.py \
  --run outputs/FRESH-HYBRID --upstream /path/to/pinned/HybridDeepResearch \
  --tasks /path/to/hybrid_ds_release.jsonl --output outputs/FRESH-HYBRID-EVAL
```

Default behavior only exports private evaluator inputs, verifies frozen task,
submission and evaluator hashes, and retains every selected ID including failures.
It never treats a missing judgment as a zero cost or a successful grade.

- Hybrid S2SQL: add `--execute-sql --db-root PATH` for the pinned official
  read-only execution-match evaluator, including its column alignment/tolerance.
  Evaluation must use the exact frozen database assets. Requires the upstream
  evaluator's dependencies in the chosen Python; never installs them silently.
- Hybrid text answers: official judge prompt/parser. After separate paid
  authorization, use `--execute-judges --judge-limit N --judge-model MODEL`.
  `N` must equal the number of nonempty text predictions. An independently
  installed `openai` package and `JUDGE_API_KEY` (optional `JUDGE_BASE_URL`) are
  needed. The client has `max_retries=0`, no tools and temperature zero.
- DataClaw outcome: same CLI; no `--tasks` required. Scalar answers use binary
  semantic equivalence; list answers use the mean of aligned binary parts,
  not a fabricated overall binary accuracy. This is an adapted upstream rubric
  with a tool-free judge, **not** the upstream OpenClaw judge transport with its
  automatic retry loop. Invalid judgments stop further calls and remain unknown.
- DataClaw process metrics (EE/GPR/TPE) are **not reported**. Native hierarchical
  traces do not yet have a validated mapping to upstream OpenClaw assistant
  steps/milestone attribution. Steps/milestones are exported host-side for later
  analysis, raw native evidence is retained, and these metrics stay null rather
  than being inferred from CLI call counts.

## Verification Boundary

Server-only offline tests cover mode separation, prompt translation, task input
allowlists, encryption/integrity, ID coverage, read-only SQL, LFS rejection,
evaluation schemas and no-retry judgment failure handling. The real public
Hybrid release parsed all 380 tasks (58 S2SQL, 203 SQL2S, 119 Parallel), and a
pinned DataClaw source sample passed parsing/export checks without printing gold.

See [the current readiness audit](benchmark-adaptation.md) for outstanding work.
The initial adapter audit did not provision environments or run paid experiments.
Subsequent explicitly authorized data/dependency preparation, real-data checks
and bounded connectivity/smoke status are in [Server Preparation](server-preparation.md).
