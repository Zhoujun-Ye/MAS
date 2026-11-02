# KramaBench

## Scope And Runtime

Pinned upstream: `mitdbg/Kramabench`, revision
`b2e0d77540263f8b6119f977fe79a8c4386b5a02`. The six domain workloads contain
104 tasks; tiny and quick-start duplicates are not included. Only public task IDs,
domains and questions enter solver contexts, never references or answer types.

Conditions are Single, coordinator Team (no Leader domain tools) and full-tool
Team. Each has an independent workspace and the same domain-tool ceiling. The
current Team catalog is `kramabench-team-v8`; membership is adaptive, not a fixed
roster. See [the implemented protocol](agent-team-design.md).

Single and Team submit a saved pipeline path. Freeze/export hashes bind the exact
file, not its correctness. Artifact execution, answer correctness and semantic
method validity remain separate claims.

## Answer Scoring

The host-only evaluator validates both upstream metrics.py and the answer-type
fixture against the pinned Git revision. Future runs freeze these hashes and the
scoring policy before dispatch. No unsafe eval or submitted pipeline execution is
part of answer scoring, and no alternative is extracted from evidence to repair
an answer or its units.

| Answer Type | Tasks | Upstream Metrics | Primary Score |
| --- | ---: | --- | --- |
| numeric_exact | 54 | success | binary success |
| string_exact | 20 | success | binary success |
| numeric_approximate | 6 | MAE, MSE, RAE score | continuous RAE score |
| list_exact | 12 | F1, precision, recall | continuous F1 |
| list_approximate | 2 | approximate F1 (numeric entries, 1% relative match) | continuous F1 |
| string_approximate | 10 | LLM paraphrase | binary, pending explicit judge |

Ninety-four tasks can be scored offline. Numeric approximation is **not** a
made-up success tolerance: RAE score = 1 / (1 + abs(pred-target)/abs(target)).
Relative error at a zero target is explicitly undefined; MAE/MSE remain available.
Nonfinite/boolean numeric predictions are rejected. Upstream's metric-specific
percentage parsing differs: Success strips `%`, error metrics treat `%` as a
fraction. Preserve that contract, not a universal post-hoc unit conversion.
List matching is unordered and can receive partial credit. Safe literal parsing
replaces upstream's unsafe eval fallback.

Semantic text cases remain `pending_judge`, score null, unless the explicitly
authorized launcher selects `--judge-model deepseek-flash`. Exact text agreement
is not silently substituted for the paraphrase metric. Judging begins only after
all solver jobs drain, using a separate one-call context, no tools and retries=0.
The adapted judge compares candidate and reference meaning and emits a strict JSON
boolean; this is not a replication of the upstream GPT judge/model/prompt. Invalid
verdicts and provider failures remain ungraded errors, not false failures or retries.
Original grades stay immutable; bound overlays/receipts/traces are written under
`semantic-grades/` and read explicitly by the auditor. The authorization cap is
30 calls, with at most three concurrent judgments. Judge tokens/cache/costs are
separate from solver budgets/accounting.
Official pipeline/subtask judging is separate and is not implemented by this
offline answer scorer. A full native-metric result therefore needs a separately
configured and authorized semantic judge for up to 30 text results in three arms.

Receipts retain per-metric values, score_kind, status, judge counts, source hashes
and exact submission hashes. Invalid submissions get explicit zero-score receipts;
unstarted/preflight-failed attempts are not imputed as model failures. The audit
reports binary success separately from continuous scores and pending judging,
grouped by answer type/metric rather than calling every non-one score a failure.

Offline rescoring writes a fresh namespace, never overwrites original evidence:

```sh
.venv/bin/python scripts/kramabench/score.py \
  --upstream benchmarks/kramabench/upstream \
  --runs outputs/RUN --output outputs/RUN-answer-scoring
```

## Budgets And Parallelism

Current diagnostic defaults: 600 shared model calls, 300 domain calls, 3,600
execution seconds and 120 audit seconds per attempt; retries=0. Team uses up to
8 identities, 64 activations, 4 Worker slots and 16-call scheduling slices.
The generous model ceiling is informed by Appendix A of
[Same Context, Different Agents](https://arxiv.org/html/2610.20959v2#A1), which
uses 300 steps and 600 calls. Our domain calls are not identical to its steps;
this is not a replication or an empirically optimal production allowance.

Default question concurrency is 12, selectable from 1 to 32. Arms remain serial
within each question. With 12 active questions, at most 36 containers are
precreated, with 144 GiB combined memory quotas; active-arm CPU quotas total 24
CPUs, and up to 60 model requests could overlap. These are ceilings, not measured
usage. The server has 128 logical CPUs and approximately 1 TiB RAM; other users'
load must still be inspected before launch. More CPU does not remove provider
rate limits. Do not raise concurrency mid-run to chase speed.

Every container sets OMP/OpenBLAS/MKL/NumExpr/vecLib thread limits to 1. The smoke
probe checks these values; the frozen launch contract records them. This avoids
128-core host detection spawning excessive numerical threads in 2-CPU containers.
No new image, environment, Docker service or cloud resource is provisioned.

## Preflight And Authorization

Run tests only on the server, after inspecting processes. Tests prohibit network
connections. The pinned workload self-score and differential tests exercise all
94 offline references and compare representative outputs with reviewed upstream
metric definitions without importing their paid interfaces.

The full scope is **104 tasks x 3 conditions = 312 solver attempts**, plus up to
30 semantic text evaluations. On 2026-11-02 the user authorized one full run with
DeepSeek Flash for both solvers and semantic judging. That authorization applies
only to `outputs/kramabench-full-20261102-01`, not future repetitions or retries.

```sh
.venv/bin/python scripts/kramabench/batch.py \
  --upstream benchmarks/kramabench/upstream --image EXISTING_IMAGE_ID \
  --all-tasks --concurrency 12 --dry-run --output outputs/FULL-preflight-NEW
```

Dry-run validates workload/scoring coverage and prepared input directories, then
writes the scope/resource plan. It does not read credentials, start containers,
probe a provider or call a solver/judge. It is not a live runtime/load test.
Actual dispatch requires replacing --dry-run with --execute-paid **and** explicit
run-specific authorization for the frozen size/settings. Fatal key/balance errors
stop further admission; no retries or replacement attempts are made.

Keep all future failed attempts and errors. See [archive policy](archive.md) for
the narrowly authorized removal of four obsolete six-question pilot outputs.
