# Retention

Only current fixed-configuration documentation and comparison reports are active.
Older prompt studies, mixed-condition publications and their dedicated tools were
removed at the user's request. Git retains committed source history; do not
restore retired runtime adapters, launch choices or prompts.

## Current Evidence

Keep the original 120 assigned attempts and the 60 Native Subagents attempts,
including failures, their frozen plans, gateway
accounting, original scores, artifact-only HDR recovery inputs/verdicts and the
current timeout-zero report. Original paths may contain historical identifiers;
renaming or overwriting them would break provenance.
Retain subsequent OBS/FULL study attempts, including interrupted or failed runs,
their frozen source/settings, intermediate measurements and shadow grades.
Keep original and accounting-audited reports separately. Code cleanup does not
authorize deleting superseded exports or changing frozen run source.

Current comparison: [current-results.md](current-results.md).
Current fixed questions: [studies/validation20.md](studies/validation20.md).

## Protected Resources

Credentials, environments, datasets/checkouts, required Docker images, frozen
current-run source and unrelated work are protected. The retired local
MASBench checkout was moved intact to external project data under
`/Users/zhoujun/Desktop/MAS-information-data/retired/masbench-removal-20261031`.
No paid execution, retries or provisioning is authorized by cleanup.

## Superseded Evidence Documentation

The current FULL/OBS mechanism is decision-v3, documented in
[Intermediate Results](studies/intermediate-full.md). Older designs and repair
reports were removed from the active tree, not merged into current claims:

- `del-protocol.md`, `subagents-evidence-design.md`: original design drafts.
- `evidence-mas-offline.md`, `shared-evidence-native.md`: initial integration receipts.
- `evidence-engineering-fix.md`, `evidence-runtime-repair.md`,
  `evidence-review-repair.md`: superseded implementation/repair receipts.
- `decision-full.md`: historical decision-v1 design and replay conclusions.

Their full text remains in Git commit `003c053` under `docs/studies/`. Before
removal, these files and the previous harness README were also saved as
`/tmp/mas-superseded-docs-20261105.tar.gz` on both local and server hosts. Temporary
snapshots are not durable archives; Git and retained server receipts preserve
the history. Original private source stages, outputs and receipts remain untouched.
Historical Structured composition, old API contracts and replay measurements must
not be presented as current decision-v3 configuration or efficacy evidence.
