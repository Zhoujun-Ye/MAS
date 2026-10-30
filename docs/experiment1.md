# Main-study Admission: No Benchmark Approved Yet

The target is a Leader-led Agent Team with direct peer communication and final
leader synthesis, not a linear handoff chain. See [architecture](leader-led-team.md).

The foundation is **Fixed Agent Roles + Task-Adaptive Team Composition**.
Researcher, Solver, Coder, Reviewer, DataAnalyst, ConstraintAnalyst, Executor and
Synthesizer are stable worker templates; Leader is the coordinating template. Meta
selection chooses members and assignments; it does not generate roles or modify
permission profiles. Communication, not team architecture search, is the research
focus. See [communication study](communication-policy.md).

## Control hierarchy

| Level | Frozen in motivation |
| --- | --- |
| Entire study | Pool/template versions, model, adapter/tool bindings, routing policy, scheduler and grading |
| Per task, across all five forms | Selected members, roles, assignments/dependencies, permissions, allowed graph and limits |
| Per communication arm | A declared static policy version, without learning during evaluation |

Composition may differ BETWEEN tasks, never BETWEEN conditions of the same task.
Routing is not an optimization variable here. LLM selection/planning, when used,
runs once and is persisted; rule/solo routes need no Meta-Agent LLM call. Solo
cases are reported separately, not used to infer handoff loss. Review multi-agent
eligibility before any arm outcome.

The initial five-arm study has NO policy updates. Adaptive means task-time
adaptation, not evolution. Later communication updates freeze the pool/TeamSpecs
and compare against adaptive-but-frozen baselines. Rule/LLM/fixed-team routing
comparisons are separate; do not change both factors and attribute gains to one.

## Mandatory gates

1. Current-backbone headroom: evidence must match checkpoint, tools, split,
   scorer and budget. Old GPT-4 difficulty is not current evidence; a specialized
   system's score is not a raw model score. Missing evidence means UNKNOWN.
2. Motivation validity: complementary useful assignments yield local facts that
   must be combined/reconciled. Identify provenance, recipient, decision and
   consequence. A trivial tool chain or deliberately bad plan does not qualify.
   Tasks must be coverable by the fixed pool without task-specific role creation
   or permission expansion. Poor initial decomposition is a separate failure
   source, not evidence of a communication failure.
3. Cost feasibility: inspect executable reference work, actual calls, tool-output
   sizes and token use. Task days, schema counts and prose length are only
   proxies. Do not truncate long tasks into artificial coordination failures.

No benchmark has passed all three gates. TravelPlanner is now retired; the
discussion below is historical screening, not an active implementation plan.
BCP uses the generic hard-boundary architecture in `information-harness.md`.

## Revised shortlist

### TravelPlanner: retired, historical screening only

The two-stage setting uses executable local database tools for flights, lodging,
restaurants and attractions, followed by constrained planning. It plausibly
supports independent searches and reconciliation of dates, location, minimum
stays and total cost. A flight discovery can invalidate another worker's lodging
or budget choice, providing a meaningful coordination decision.

Inspect native 3-day validation tasks first, not 5/7-day tasks or the whole suite.
Three days is NOT a measured short agent trajectory. Require complete initial
requests and bounded reference work. Use tool-use, not sole-planning with all
answers supplied. Exclude the LLM-backed Planner tool as a purported deterministic
domain tool and avoid a global notebook bypassing the controlled message channel.

The upstream pipeline uses GPT-4 to parse prose plans before rule-based scoring.
The adaptation directly requests its documented output schema, parses
without paid LLMs/eval and discloses the adapted setting. Never expose hidden
structured constraints or reference answers. Respect upstream evaluation rules.
Native tool/output integration has been exercised; real-model calls, token cost
and current-backbone headroom remain UNKNOWN. See [adaptation evidence](travelplanner-adaptation.md).

Read-only inspection of public validation rows 0-2 found complete 3-day queries
and reference-information strings of 14,662 / 11,794 / 13,496 characters. These
are reference-bundle sizes, not runtime token counts or proof of useful teamwork.
The leaderboard's backing results dataset was inaccessible through its anonymous
dataset API; no matching current-backbone score was verified. Do not infer a low
score from this access limitation.

Sources inspected 2026-10-29:
- https://github.com/OSU-NLP-Group/TravelPlanner
- https://github.com/OSU-NLP-Group/TravelPlanner/blob/main/tools/flights/apis.py
- https://github.com/OSU-NLP-Group/TravelPlanner/blob/main/evaluation/eval.py
- https://huggingface.co/spaces/osunlp/TravelPlannerLeaderboard

### DSBench: secondary bounded-analysis candidate

Instructions and data files can support complementary definition/schema analysis,
computation and cross-checks via Python/table operations. Consider only complete,
text-accessible small analysis tasks; exclude modeling/training, large data,
image-dependent inputs and open-ended pipelines. Do not turn one calculation
into a fake team. The upstream evaluation includes model calls; importing its
notebook is not offline evaluation. Shortness, grading and current headroom need
independent verification. Not downloaded, adapted or admitted here.

Sources:
- https://github.com/LiqiangJing/DSBench
- https://github.com/LiqiangJing/DSBench/blob/main/data_analysis/readme.md

### MARBLE: architecture reference only

MultiAgentBench/MARBLE is relevant to topology, but Research uses live paper/web
retrieval and Database introduces infrastructure/anomaly workloads. A native MAS
label does not establish cheap, short, controlled evaluation. Do not import the
whole suite or replace our frozen organization with its orchestrators.
Source: https://github.com/ulab-uiuc/MARBLE

## Removed and excluded

All old adapters, per-benchmark configs, paid launchers and benchmark-specific
tests are removed: BFCL, ToolHop, BrowseComp-Plus and tau2. Server native sources,
assets, environments and outputs remain untouched. Generic harness tests and
read-only result/cache analysis remain. Historical notes are clearly labeled.

Reasons: BFCL's evolving requests; ToolHop's shallow chains and generated-tool/
scorer complications; tau2's simulator and frontdesk/operator organization;
BCP's historical search/output costs. AppWorld full suite, AgentHop and long
repository/data-lake/game tasks are not added. WorkBench is not selected; no
new unsupported claim about its current-model saturation is made.

## Next evidence, not run authorization

Audit an outcome-independent candidate sample: reference work, tool-output sizes,
subtask opportunities, local findings and the decisions requiring coordination.
Only after explicit authorization for a monetary/call cap, run a disjoint pilot
on the exact backbone and proposed harness. Predeclare ceiling/floor and cost
criteria before observing outcomes. Never select main tasks from pilot failures.

Freeze initial plan, roles, permissions, allowed graph and scheduler across five
handoffs; independently review plan sufficiency. Separate unknown headroom/loss,
environment errors and model failures. Include cold starts, repeated reads,
reasoning, planning, communication, retries and judging in accounting. Historical
P1-P4 thresholds stay unchanged but are not automatically applied to this study.

The need for communication evolution is an open hypothesis. First establish a
meaningful, causally relevant problem not already solved by simple fixed policies.
Then evaluate updates on disjoint tasks, counting updater/judge/validation costs.
Task-adaptive routing is not RSI, and cache savings are not learning efficacy.

## Cleanup verification

This records the PREVIOUS cleanup, not verification of the newly added runtime.

All 37 retired source/config/test files were removed locally and moved to the
server's `.retired_sources/leader-led-team-20261029/` by an explicit file list.
No native upstream/assets, credentials, environments or experiment outputs were
removed. Source sync did not use --delete. Core server tests: 45 passed. Shell
syntax and diff whitespace checks passed. No model API call or new paid pilot
was run. New runtime/data/offline evidence is recorded separately in
`travelplanner-adaptation.md`; those scripted checks do not establish motivation.
