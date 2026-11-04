# KramaBench

## Claude Single Addition (2026-11-03)

`run.py --backend claude-code-single-agent` plans the new strict native Claude
Single condition. Use its native denial proof, not the Subagents proof. Model,
CLI pin, task data, V3 scoring, common instructions, container limits, concurrency,
timeout and one-request judge policy remain aligned with the current comparison.
The native tool surface/permission guard and condition instruction differ.

`scripts/studies/compare_claude_single.py --baseline outputs/current/comparison-3way/summary.json
--single-run FRESH-RUN --output FRESH-COMPARISON` joins completed 104-task results.
It checks matched task sets, exact scoring/artifact hashes, strict Single
observations and zero member transcript messages, without new model/judge calls.
The retained Team arm still has the 99-original/5-repair protocol limitation.

Pinned upstream: `mitdbg/Kramabench` at
`b2e0d77540263f8b6119f977fe79a8c4386b5a02`, 104 tasks in six domains.
The task loader exposes only public IDs/domains/questions to solvers, never
references, private subtasks or reference code.

## External Data Layout

The upstream checkout is an external data/evaluation dependency, not adapter source.
It need not live inside `benchmarks/kramabench/`. Pass its location through
`--upstream`; the loader still verifies the pinned revision and input content.
Local checkout location: `/Users/zhoujun/Desktop/MAS-information-data/kramabench/upstream`.
The server checkout is now `/home/zhoujunye/MAS-information-data/kramabench/upstream`;
its old path remains a compatibility symlink for historical commands.

Use the same convention for all three benchmarks outside the source repository:

```text
MAS-information-data/
  kramabench/upstream/
  dataclawbench/upstream/          when explicitly provisioned
  hybriddeepresearch/upstream/    when explicitly provisioned
  hybriddeepresearch/data/        DB/KB assets, separately provisioned
```

Only the existing local KramaBench checkout was relocated; no other datasets were
downloaded. Do not delete it if local task loading or scoring is needed. For server
offline integration tests, set `KRAMABENCH_UPSTREAM` to the existing server path;
tests no longer require a checkout or symlink inside the source tree.

## Conditions And Execution

`scripts/kramabench/run.py` is the active launch entry point. Select one backend
and optional repeated `--task-id` arguments. Its default freezes a plan; only
`--from-plan --execute` plus run-specific authorization dispatches models.
The default judge limit is zero; at most ten explicit semantic verdicts per
backend are supported. No automatic retries or replacement attempts are made.

Claude Single removes and denies native delegation tools, with observed policy
and zero-delegation checks. Missing evidence is not a pass. Deep Agents is retired;
its historical 500-turn results remain evidence, not an active execution choice.
The native tool policy is not an adversarial shell/network sandbox.

Agent Teams is retired as an execution condition; historical results remain readable.

`claude-code-subagents` uses the separate print-mode adapter and explicitly
disables Agent Teams. Native SubagentStart/Stop and root SessionEnd, no Team
configs/TeammateIdle events, actual delegation counts and artifact replay are
recorded separately. Enabled tools are not evidence that delegation occurred.

Plans bind source/data/scoring/CLI hashes, native arguments, timeout and concurrency.
Each task has an independent profile/workspace and disposable existing-image
container. Offline replay runs after solver drain in a fresh no-network,
credential-free copy. Actual native messages/usage and failures remain evidence.

## Versioned Scoring

The local evaluator verifies reference definitions/fixtures against the upstream
pin. Default `scale_aware_v3` intentionally corrects the upstream binary numeric
absolute-epsilon defect. `upstream_v2` preserves the original behavior explicitly.

V3 binary numeric success uses target-relative error <= 1e-4 (0.01%), no absolute
epsilon, and exact zero for a zero reference. Integer-pair equality and parsing
are retained. This prevents near-1e-13 references from accepting zero, wrong signs
or large relative errors merely because absolute difference is below 1e-6.
It is a corrected local score, not an unchanged official score.

| Answer Type | Tasks | Primary Metric |
| --- | ---: | --- |
| numeric_exact | 54 | binary success, scale-aware V3 |
| string_exact | 20 | case-insensitive success; numeric inputs use V3 |
| numeric_approximate | 6 | continuous RAE |
| list_exact | 12 | continuous F1 |
| list_approximate | 2 | continuous approximate F1 |
| string_approximate | 10 | explicit semantic verdict, otherwise pending |

Other metrics are unchanged. Continuous scores are not binary accuracy. Neither
matching answers nor successful replay certify scientific-model methodology.
The ten semantic verdicts are explicitly authorized, one request each, without
tools/retries and with separate accounting. Existing artifact-bound verdicts
can be reused for offline rescoring; no new judge is called implicitly.

## Reporting

- `catalog.py` and `prepare.py`: validate public task/input provenance; provisioning
  remains separately authorized. `prepare.py` plans by default; an image build
  additionally requires `--execute`.
- `scripts/probes/`: offline native transport/policy probes shared by benchmarks.
  The Single/Subagents probes use only a loopback fake provider and dummy key.
- `score.py`: versioned offline scoring of historical attempt layouts.
- `rescore_native.py`: reproduce original grades and write a fresh V3 overlay,
  retaining exact source-summary/submission hashes and reused semantic verdicts.
- `results.py`: publish matched 104-task snapshots with explicit replacements.

```sh
.venv/bin/python scripts/kramabench/results.py \
  --single-audit outputs/SINGLE-V3/summary.json \
  --team-audit outputs/TEAM-ORIGINAL-V3/summary.json \
  --repair-audit outputs/TEAM-REPAIR-V3/summary.json \
  --output outputs/FRESH-PUBLICATION
```

The publisher replaces the entire specified repair set, even when a new answer
scores lower. It rejects changed artifacts/references, duplicate/missing task
IDs, mismatched scoring versions and an unverified Single condition. Each
replacement records its old and new source, score and artifact hash. It never
modifies raw runs or chooses a best-scoring answer after seeing scores.

The historical publication and run artifacts were deleted at the user's request
on 2026-11-04. There is no current four-condition result table. The publishers
below remain reusable source tools, not evidence that their old input paths exist.
Future per-case USD estimates cover observed usage only; overlapping shared-account
balance intervals cannot be allocated or summed as backend bills.

`retain_current.py` plans cleanup by default. On explicit execution it copies and
hash-checks the selected 208 raw attempts into `current/evidence/`, relocates old
namespaces to an archive outside outputs, and records a relocation map. Frozen
logs and source summaries are not rewritten. Local reports-only retention does
not pretend remote raw evidence is present locally. `scripts/studies/compare_subagents.py`
joins a finished 104-task native Subagents run with these retained baselines;
it rejects mismatched task/scoring sets, changed artifacts and evidence of Team
mode in the Subagents condition. Comparison/reporting makes no model calls.

All tests/experiments run on the server. Historical pilot versions, failed probes,
the old delegated dcode study and detailed audit receipts remain in
[archives](archive.md), not active
study defaults. No old authorization carries over to future paid work.
