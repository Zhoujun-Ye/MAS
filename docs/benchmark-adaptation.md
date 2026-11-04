# Benchmark Adaptation Audit

Updated 2026-11-03. This is an implementation/readiness audit, not a benchmark
result. No paid solver, judge, search request, install or production deployment
is authorized by it.

The later user-authorized provisioning and smoke work is recorded in
[Server Preparation](server-preparation.md). The outstanding list below is the
pre-provisioning snapshot, not the current server installation state.

## Common Structure

```text
harness/                          external Claude CLI adapters only
benchmarks/
  _io.py                          atomic JSON and provenance helpers
  _external.py                    gold-isolated task/export contracts
  kramabench/                      tasks.py, evaluation.py, semantic_judge.py
  dataclawbench/                   tasks.py, evaluation.py
  hybriddeepresearch/              tasks.py, evaluation.py
scripts/
  common/                         shared prompts, containers, proof, run/score/tools
  kramabench/                      catalog.py, run.py, score.py; replay/publication
  dataclawbench/                   catalog.py, run.py, score.py
  hybriddeepresearch/              catalog.py, run.py, score.py
  probes/                         offline native mode probes
  studies/                        retained comparison and pilot analysis utilities
analysis/native_evidence.py        read-only native observations and accounting
```

Shared code no longer imports execution helpers from KramaBench. All three use
the same unchanged ordinary Subagents prompt, Claude environment/container helpers
and backend-specific offline-proof validation. Task loaders and evaluation
schemas have separate files in every benchmark.

Uniform ownership does not mean identical grading protocols: KramaBench preserves
its pipeline submission, offline replay, versioned numeric metrics and historical
result layout. DataClawBench/HDR preserve their final-text submission and outcome
evaluation schemas. We do not rewrite historical runs or turn continuous scores
into binary accuracy to make directories look alike.

## Readiness

| Area | KramaBench | DataClawBench | HybridDeepResearch |
| --- | --- | --- | --- |
| Task loading | Pinned 104-task loader | Upstream sorted QA IDs/rubric | Encrypted release decode, integrity checks |
| Solver gold isolation | Public question/input lake | No task markdown/gold mounts | Selected DB/KB only; no reference fields |
| Baseline prompt | Original ordinary prompt | Same prompt | Same prompt |
| Execution | Existing native run/replay path | Fake-boundary workflow tested | Fake-boundary workflow tested |
| Outcome evaluation | Versioned numeric/string metrics; explicit semantic judge | Adapted upstream per-part rubric | Official SQL evaluator invocation and text prompt/parser |
| Process metrics | Native trace/accounting | EE/GPR/TPE mapping not implemented | Native trace/accounting only |
| Real end-to-end evidence | Retained full runs, not rerun here | Not completed | Not completed |

Pinned primary contracts checked during this audit:
[DataClaw task builder](https://github.com/GTML-LAB-sysu/DataClaw/blob/32e138750ceba41b47290211403ad1781d5e1971/dataclaw/build_tasks.py),
[DataClaw grading](https://github.com/GTML-LAB-sysu/DataClaw/blob/32e138750ceba41b47290211403ad1781d5e1971/dataclaw/utils/grading.py),
[HDR SQL evaluation](https://github.com/Snowflake-AI-Research/HybridDeepResearch/blob/3523f1da83a0470cdea742ea8b7426e7af6ca89b/evaluation/s2sql_eval.py),
[HDR text judge](https://github.com/Snowflake-AI-Research/HybridDeepResearch/blob/3523f1da83a0470cdea742ea8b7426e7af6ca89b/evaluation/llm_judge.py).

## Fixed During Audit

- Removed the shared runtime's dependency on the KramaBench package; moved
  native evidence to analysis and study-specific scripts out of active entry points.
- Removed remaining active-doc references to the retired Deep Agents condition
  and deleted probe path; historical source/results remain archived.
- New runners retain progress/predictions after each task, initialize all selected
  IDs, record interruption/cleanup failures, and stop later dispatch on failure.
  A failed container stop never produces an accepted final answer.
- Successful predictions require a frozen submission hash at scoring time.
  Evaluation outputs cannot overlap original evidence, database or source paths.
  Judge failure yields an incomplete receipt and nonzero exit, not a success code.
- Native proofs now check actual mode-specific observations, not only a generic
  `passed` flag. Legacy mode-specific proofs remain usable without manual relabeling.
- New plans retain native environment, exact condition instruction, CLI executable
  hash on execution, and source archive. Task/evaluator files are checked against
  pinned Git blobs, catching modified or partial checkouts with unchanged HEAD.
- Source snapshots prune ignored output/archive/cache directories before walking
  them; historical archives no longer accidentally enter source inventories.
- KramaBench image preparation now plans by default and requires `--execute` for
  separately authorized provisioning.

## Still Outstanding

1. **Assets and environments.** The production benchmark tree has no prepared
   DataClawBench/HDR checkout or full database installation. Prior temp fixtures
   are not a prepared environment. Full DataClaw Git LFS hydration and HDR SQLite
   DB/KB inventory must be obtained and verified under separate provisioning scope.
2. **HDR SQL dependencies.** Read-only inspection of the project server Python
   found `numpy` and `openai`, but no `scipy` or `sqlglot`. The pinned official SQL
   evaluator requires these. No package was installed; real official SQL grading
   is not yet validated. Do not substitute a handwritten matcher.
3. **Native end-to-end preflight.** New task/asset mounts and helper tools still
   need an existing-image, no-network native CLI smoke for each intended mode,
   then a separately authorized bounded real-provider trial. Fake-boundary tests
   do not establish real provider, permission, async lifecycle or task correctness.
4. **Web access.** Tavily/fetch is wired explicitly, but live provider behavior,
   service cost and complete accounting have not been validated. No search was
   issued here. Shell networking is not adversarially sandboxed.
5. **DataClaw scoring scope.** Outcome scoring uses the upstream per-part rubric
   via a tool-free no-retry client, not the OpenClaw transport. EE/GPR/TPE need a
   separately validated mapping of native hierarchical traces to upstream steps
   and milestone judgments. They remain null, never fabricated from tool counts.
6. **Publication.** New runners export artifact-bound evaluation rows and raw
   grades, not a validated cross-benchmark leaderboard. Dataset/category/type
   aggregation, failed-attempt denominators and budget accounting must be fixed
   before a full study. No existing paid-run authorization is reused.

The benchmark-specific commands and data restrictions are in
[KramaBench](kramabench.md) and [DataClawBench/HDR](research-benchmarks.md).

## Verification Receipt

Fresh server source stage: `/tmp/mas-benchmark-clean.owXBvC`.
`pytest-results.xml` records **189 passing offline tests**, including both new
benchmark plan/fake-execution/export workflows, cleanup failure retention,
submission hash enforcement, pinned Git source checking and layout boundaries.
All nine benchmark `catalog/run/score --help` commands passed.

The ordinary Subagents instruction matched all **104/104** retained full-run
prompts. The existing encrypted HDR release was re-read without printing decrypted
contents: **380 tasks**, 58 search-to-SQL, 203 SQL-to-search, 119 parallel.
These counts do not establish real task execution or evaluation correctness.
No paid provider/search requests, installs or production deployment were performed.
