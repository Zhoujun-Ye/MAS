# Validation20 v1

Adopted by the user on 2026-11-04 for small-sample idea development and validation.
This is not an independent held-out final test. Repeated tuning on these questions
must be disclosed; final claims require separate data and an appropriate design.

## Current Status

The user subsequently authorized a fresh rerun on 2026-11-04: all 20
frozen questions per benchmark, both conditions, one attempt each (120 total),
with native output defaults and no retries. The original manifest remains
byte-identical; `validation20-final-protocol.json` records the changed prompt
hash separately. Solver concurrency remains 6, grading concurrency 2, effort high.
Use the full-matrix reporter rather than the historical two-slice merger below.
The preceding deletion remains historical; no old paid result is reused.

### Prior Cleanup

The user requested stopping experiments and deleting all current paid results on
2026-11-04. The initial and partial extension results were deleted, along with
their current summary reports. The fixed public task IDs/hashes below remain;
there is no retained scored baseline to reuse. The output-default rerun discussed
after the extension launch was not started. Do not resume or replace any attempt
without fresh run-specific authorization. The run names/protocol below describe
selection provenance and the previous plan, not retained results.

## Frozen Questions

`validation20-v1-manifest.json` contains exactly 20 public task IDs per benchmark,
their SHA-256 public-task identities, category/domain strata and batch membership.
It contains no questions, reference answers, gold SQL or evaluation logs.

The first 10 IDs exactly match `claude-matched10-v4-high-01-443a5f0` in both
conditions. The additional 10 are the next IDs under the same outcome-blind,
seed-42 SHA-256 round-robin ordering. No result-driven replacement or reroll is
allowed. Preserve failures and native-condition audit failures.

The manifest SHA-256 is
`fc39ad8539e2af0b140a6b9a8b3144d241742b2c3b2424b6d74ae03f1829e0a5`.
Changing any question requires a new named set version; do not silently edit v1.

## Baseline Protocol

- Claude Code 2.1.286; DeepSeek Flash; all lead/worker effort `high`.
- Strict Single vs native Subagents, then-adopted prompt, Teams disabled.
- One attempt per task per condition; zero retries or replacement attempts.
- Solver concurrency 6, grading concurrency 2, isolated outputs/workspaces.
- DataClaw 1200 s, HDR 1800 s, Krama 3600 s; web-enabled tasks share four
  search/fetch requests across all agents/processes in an attempt.
- Original batch: 60 attempts. Extension: 60 attempts; up to 52 paid judge calls,
  with SQL/numeric evaluation otherwise. No new authorization for future runs
  is implied by adopting this validation set.

Both original batches explicitly set `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16384`.
The user subsequently requested removing that project-defined single-response
cap and rerunning HDR `sql2s_047` / Single. That separate attempt uses the native
CLI/model default, not unlimited output. Preserve the original failure and
distinguish the new configuration from the uniform original baseline; do not
silently mix its result into the original 120-attempt comparison.

Native audit failures remain in raw assigned-condition summaries and are marked
separately. They are not evidence of the intended native organization. Missing
grades or accounting remain unknown. DataClaw process metrics are unavailable.

## Reuse

The native matrix accepts `--task-manifest docs/studies/validation20-v1-manifest.json`.
For the extension use `--task-offset 10 --tasks-per-benchmark 10`; for all 20 use
offset 0 and count 20. Planning is free of model calls. Execution requires matching
runtime-bound offline proofs, `--execute`, exact attempt/judge authorization and a
fresh output directory. The runner verifies all frozen task hashes before dispatch.
Baseline settings remain fixed; new idea interventions must be separately labeled
and explicitly authorized rather than silently changing the baseline.

Use `scripts/studies/matched_matrix_report.py` for the current full-20 report.
The obsolete initial10 freeze/two-slice merger required the deleted original
batch and was retired during cleanup. The public task manifest is unchanged.
Reports retain scores, timing, costs, role accounting and audit exceptions.
Questions, answers, SQL and private evaluation logs stay on the server.
