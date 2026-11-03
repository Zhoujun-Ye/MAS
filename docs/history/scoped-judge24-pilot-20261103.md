# Scoped evidence-judge pilot, 2026-11-03

## Authorization and frozen design

The user requested one revised Subagents condition on 24 tasks, compared with
the existing Subagents outputs. Run 24 solver attempts, at most one required
semantic answer judge, no retries and no replacement attempts. Do not rerun
the historical baseline. The existing admission gate remains in effect; a
failed canary stops the remainder rather than silently replacing it.

This is a joint prompt intervention: bounded judgment scope, warm-context
production, a provenance-labeled neutral packet, and compact early reporting.
It cannot separately establish the causal effect of each component or prove
that cold-start overhead is absent. User-reported 20/193-second timing and
93%/1.14x/96% diagnostics have no identified analysis script yet and remain
unverified here. Do not use them as measured pilot findings.

The new prompt replaces only the Subagents organization instruction, not the
common task instructions, native CLI, model, tools, permissions or evaluator.
The original default prompt is preserved. The override text, file SHA-256,
source snapshot, task list, data hashes and settings are frozen before launch.
The mechanism remains native Claude Agent delegation; no runtime scheduling
or context-isolation mechanism is implemented by this project.

## Selection

Sort task IDs within each domain/easy-hard stratum by
SHA256(`scoped-evidence-judge-v1|20261103|TASK_ID`), selecting the lowest two.
This gives six domains x two difficulties x two tasks = 24 tasks, without
using answers, scores, timings or previous delegation behavior. Report this
balanced sample descriptively, not as the full-workload accuracy estimate.

Selected tasks:

- archeology-easy-8, archeology-easy-6, archeology-hard-5, archeology-hard-1
- astronomy-easy-5, astronomy-easy-3, astronomy-hard-10, astronomy-hard-8
- biomedical-easy-2, biomedical-easy-6, biomedical-hard-7, biomedical-hard-8
- environment-easy-2, environment-easy-4, environment-hard-16, environment-hard-13
- legal-easy-9, legal-easy-25, legal-hard-7, legal-hard-1
- wildfire-easy-9, wildfire-easy-15, wildfire-hard-10, wildfire-hard-6

There are 18 binary and six continuous-score tasks; legal-easy-25 requires
the existing semantic answer judge. Do not combine continuous scores into
binary accuracy. Original scores and target conventions remain unchanged.

## Runtime and measures

Use Claude Code 2.1.225, deepseek-flash[1m], effort max, 12 concurrent tasks,
3600-second task timeout, 600-second offline replay timeout, 2 CPUs/8 GB per
task, and the baseline image and input lake. Retain native retry=0 and no
adapter retries. Read credentials only from the existing protected .env.
Server source stage: /tmp/mas-scoped-judge-source.EkRgPF.
Run: outputs/current/runs/claude-code-scoped-judge24-20261103-01.
Reports: outputs/current/reports/scoped-judge24-20261103-01.

Primary outcomes: paired binary transitions, continuous scores by metric,
mean/median CLI wall time and per-task time ratios, role-level observed input
and output tokens, token-weighted cache reuse, retained-message cost estimates,
and separately labeled account balance intervals. Count failures; never
silently restrict comparisons to successful attempts. Historical timing and
provider variability prevent a randomized causal speedup claim.

Mechanism checks: number of native agents, actual received prompt size and
packet provenance fields, tool calls per child turn, return words and runtime,
observed parent handling of verdicts, source searches versus repeated
production, and whether useful evidence arrives before final commitment.
Do not equate an early matching numeric token with a complete valid solution.
Do not equate unchanged final answers with anchoring or confidence gain.

The one-agent, three-tool-call and 250-word limits are prompt instructions,
not enforced native quotas. A single targeted follow-up to the same child is
allowed; report actual compliance and any wider scans. Common project context
may still be visible to native children; a fresh context is not hard isolation.
No performance target is assumed. The prompt may increase producer work,
miss unlisted alternatives, or lose accuracy through premature stopping.
