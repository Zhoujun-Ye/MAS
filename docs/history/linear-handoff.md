# Superseded: Linear Handoff Candidate Study

Historical note only. Replaced by the Leader-led Agent Team direction. Referenced
benchmark adapters and entry points were removed; commands below are not current
instructions. Recorded outputs remain untouched.

## Decision (2026-10-29)

**ToolHop is the first main-study candidate, NOT yet an admitted main benchmark.**
BFCL Multi-Turn Base is retired from the main experiment: later requests can
introduce new applications/tools, so a first-turn plan is not a decomposition
of the complete task. Its paid CLI is disabled; offline fixtures and historical
outputs are preserved. Never expose future dialogue and call it native BFCL.

No matching public ToolHop result was found for the configured `deepseek-flash`
backbone/checkpoint/settings. **Current-backbone headroom is unknown.** Older
model results and scripted tests do not establish non-saturation. No paid call,
including planning, judging or simulation, was made during this revision.

| Candidate | Task / tools | Decision |
| --- | --- | --- |
| ToolHop | Complete query; generated Python functions actually execute; no user simulator | First candidate for short dependency-sensitive tasks. Synthetic environment, not live services. Solvability and schema leakage require audit. |
| AppWorld | Initial autonomous task; stateful app APIs and environment tests | Strong-constraint backup. A short subset requires separate reference-length and headroom checks; not the cheap whole-suite choice. |
| AgentHop | Initial scientific question; seven-tool paper sandbox | Information-rich backup. Published API-model average input is 65K-169K tokens before five-arm overhead, so not the cheap first choice. |
| BFCL multi-turn, tau2, ToolSandbox | Evolving requests or simulated dialogue | Not the complete-initial-task main protocol. |
| WorkBench | No new current-model saturation evidence gathered here | Not selected, consistent with the user's concern; no new saturation claim. |

Primary sources inspected:
- [ToolHop dataset/code](https://huggingface.co/datasets/bytedance-research/ToolHop)
- [Author-maintained leaderboard](https://huggingface.co/spaces/Junjie-Ye/ToolHop)
- [ToolHop paper](https://aclanthology.org/2025.acl-long.150/)
- [AppWorld implementation](https://github.com/StonyBrookNLP/appworld)
- [AgentHop paper and resource accounting](https://arxiv.org/html/2609.34428v1)
- [BFCL multi-turn definition](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)

The ToolHop leaderboard's Free column reports DeepSeek V3.2 57.49%, GPT-5.4
55.38%, Claude Opus 4.6 66.53%, and o3 75.68%. These motivate investigation;
they are not our backbone's results or results under our stricter scorer.

## Data and execution

Pin ToolHop to `b439d7279af359fda46e8117ae4f0245b75f5c6b`, with official LFS SHA256
`0a51f71a44b7025645e452123af3caf2e348301922af91778e268db0188a7fab`.
The optional download mirror is transport only; the hash must match.

Static filters: 3-6 advertised tools, query <=3000 characters, schema JSON
<=24000 characters, implementation <=120000 characters, supported function
layout and matching schema/function names. These are cost proxies, **not proof
of 3-6 calls or sufficient cross-agent dependence**. No model outcomes or gold
answers enter selection. Of 995 entries, 889 are candidates: 20 reserved for a
possible future pilot and 869 remaining in the candidate main pool. Forty fail
the tool-count filter; 66 have unsupported function layouts. These are adapter
exclusions, not proven dataset defects. No final main sample is selected.

Planner and workers receive the entire question, answer-format rule and schema
VALUES. Mapping keys are gold subquestions and are not exported. `sub_task`,
`answer`, function code and hidden state remain evaluator/environment-only.
Published schemas themselves can contain entity examples: task 0 names Stanley
Park in a schema while an earlier tool should discover that park. Audit this
shortcut without silently editing the published task.

Functions execute in Linux bubblewrap: no network, project/home/credential
mounts or inherited environment; read-only runtime; temporary scratch space;
CPU, memory, output and time limits. No host-exec fallback. Missing modules and
sandbox failures are incomplete/ungraded. Executability alone does not establish
semantic correctness or solvability of generated tools.

The original scorer permits substring credit and a preceding-tool-output
fallback. Our answer-only normalized equality uses Decimal for numbers, never
eval, substring credit or tool-output fallback. Call this a **ToolHop-derived
handoff study**, not an official leaderboard result. Use this same scorer in
the future screening baseline and every treatment.

## Fixed organization

`harness/planner.py`, protocol `planner-complete-task-v2`:

1. Main agent sees the entire initial task and public schemas once. It produces
   2-4 complementary sequential workers, names, roles, assignments including
   dependencies/completion criteria, and domain-tool allowlists.
2. Persist raw response, exact model settings, usage and input/prompt/plan
   digests. No per-condition planning or silent bad-plan retry.
3. Review coverage, tool sufficiency, dependency feasibility and meaningful
   division before any condition outcome exists. Schema validity is not semantic
   plan validity. Record rejected plans separately rather than fixing one arm.
4. Five forms reuse that artifact and identical initial environments. Every
   worker sees the full task and whole-team plan, its role/assignment and incoming
   handoff. `run_task()` refuses reuse for a later user request.

This is a bounded sequential hierarchical MAS, not every parallel/DAG topology.
The main agent plans and the last planned worker integrates/verifies. Benchmark
turns do not define agent boundaries. Tasks needing future clarification are
outside this protocol, not repaired by revealing evaluator data.

## Handoffs and controls

| Form | Incoming information and communication capability |
| --- | --- |
| Full Context | Complete upstream execution messages including reasoning and tool arguments/results. Flat frames avoid recursive duplication. Information-retention reference, not a performance upper bound. |
| Summary | Compressed natural-language report; no archive reads. |
| Structured | Validated conclusion, sourced facts, exclusions, questions and confidence. Invalid records become incomplete without silent repair. |
| Document Retrieval | Summary and labeled evidence catalogue; id-based reads return original observations. |
| Adaptive | Recipient-aware content selection plus exact-fragment evidence requests and id reads. A simple adaptive baseline, not an optimal learned policy. |

Reports are generated in a **separate copied context**, preserving reasoning
verbatim and leaving sender execution history untouched. All report generators
receive the same next-recipient role/assignment and mapping from their own
observations to stable ids. Catalogues identify agent, stage, tool, arguments
and length. Retrieval recipients see the catalogue, not free observation text.
Reading evidence does not duplicate it in the archive.

First-worker prompts and domain tools are identical: no communication tools
before evidence exists. Subsequent domain permissions are fixed; communication
permissions intentionally differ. Do not claim the whole tool inventory is
identical. Fixed plans also do not fix sampled reasoning or later tool arguments,
trajectories and actual call counts.

Shared settings: same model/effort; 8192 output tokens per call; 20 domain calls;
6 execution turns per worker; 200000-character input guard; no silent truncation.
Retrieval/adaptive each get six communication reads. These are declared caps,
not measured consumption. Budget exhaustion stays visible, distinct from errors.
Planning is charged once per task; execution, report construction, reasoning and
all input tokens from repeated document reads must be included in cost reports.

## Admission and scientific claims

Before a main study:

- Audit tools for solvable chains, unsupported behavior and schema leakage.
  Exclude with preregistered reasons, never based on which condition fails.
- Independently annotate information density, exact constraints and delayed
  reuse. ToolHop is a dependency/precise-value candidate, not established coverage
  of all three strata. Immediate next-hop use is not delayed reuse. Do not induce
  loss by hiding the task or imposing a demonstrably poor decomposition.
- Seek explicit authorization for a disjoint single-context screening pilot
  under the same backbone, schemas, scorer and budgets. Record served model,
  fingerprints, tokens, calls, latency and errors. A separately authorized no-tool
  check can expose parametric/schema shortcuts. Pilot failures must not become
  the selected main sample.
- Approve ceiling/floor and call/token-cost screening rules BEFORE that pilot.
  The reserved 20 tasks are only a small feasibility screen, not a conclusive
  saturation test. No cutoff is retrofitted here.
- Freeze reviewed plans and strata; preregister paired analysis, repetitions and
  semantic loss adjudication. Existing phase-0 P1-P4 thresholds remain unchanged
  and are not transplanted into this new experiment.

Measure loss over decision-relevant facts actually discovered upstream, including
qualifiers, constraints and failed actions. Assess the recipient's decision-time
context, including evidence actually read. Distinguish undelivered, available
but unused, misinterpreted and never discovered. An evidence id is not factual
arrival. Semantic judging/human agreement remain pending; no L score is invented
from string/id matching in the new adapter.

The five-arm end-to-end comparison estimates communication-policy effects under
fixed organization, not causality of an individual missing fact. For that claim,
branch the same frozen checkpoint/decision state and compare supported missing-
fact supplementation, unchanged replay and a matched control, with fixed
downstream tools/budgets and repetitions. No causal replay result is claimed.
Report incomplete/error rates and budget exhaustion alongside success and cost.

## Offline operation and evidence

Run only on the server after scoped source sync and process inspection:

```bash
.venv/bin/python scripts/toolhop/prepare.py --endpoint https://hf-mirror.com
.venv/bin/python scripts/toolhop/run.py --out outputs/toolhop/offline-preflight-v1 --limit 5
.venv/bin/python -m pytest -q
```

The ToolHop CLI deliberately has **no paid execution option**. It exports public
planning inputs and an immutable manifest, verifies supplied plan artifacts
against input and exact model settings, and reports pending admission gates.
`execute_task` is exercised by scripted clients with actual native tools; it does
not construct a client or silently invoke a planner.

Server checks: 95 tests passed, with one upstream invalid-escape syntax warning.
Task 0's fixture executes four actual tools across three workers under all five
forms. Its scripted policy knows the answer: integration evidence only, not
planning quality, information-loss evidence or backbone headroom. The five-task
preflight has 25 hypothetical runs, zero model calls, `ready_to_execute=false`
and `main_benchmark_confirmed=false`. No experiment batch ran.
