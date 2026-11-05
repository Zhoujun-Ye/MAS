# KramaBench

## Current Conditions

Use native Claude Single or Subagents; the current comparison uses the frozen
Validation20 manifest. Strict Single requires native delegation denial and audit.
The lead prompt is unchanged; retired mixed-condition publications are not active.

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

- `catalog.py` and `prepare.py`: pinned task/input provenance; provisioning is
  separately authorized and plan-only unless explicitly executed.
- `scripts/probes/`: loopback fake-provider transport and native policy checks.
- `score.py` and `rescore_native.py`: artifact-bound offline grading and rescoring;
  semantic verdicts require separately authorized judge calls.
- `scripts/studies/matched_matrix_report.py`: current matched comparison across
  all three benchmarks; supports an explicit timeout-zero reporting policy.
- `scripts/studies/rescore_validation20_hdr.py`: explicitly authorized two-case
  recovery from existing artifacts, never a solver rerun.

The old 104-task repaired Single/Team publisher, mixed Deep Agents/Claude joiners,
and publication-specific retention tool are retired. Their old input studies
were deleted previously; source is retained in the cleanup snapshot, not as
active commands. Current results and caveats are in [current-results.md](current-results.md).

All tests and experiments run on the server. Source/data/scoring hashes, original
failures, unknown accounting and current raw artifacts remain preserved. Historical
records are in [archives](archive.md); no old authorization permits new paid work.
