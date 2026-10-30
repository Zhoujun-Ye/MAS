# Exploratory Collaboration Pilot

## Research Question

Observe failures of a fixed Agent Team before choosing which Harness mechanisms
to improve. Do not presume that information loss is the dominant bottleneck.
This pilot contains no RSI updater or post-outcome policy tuning.

Fixed: member identities/templates, private feature assignments, domain tools,
workspace isolation, async event-driven scheduler, transport reliability,
resource allowances and evaluator. Autonomous: when to communicate, whom to
contact, message contents/form, follow-up questions, clarification and disagreement.
A fixed scheduler does not freeze these agent decisions.

## Observation Categories

| Category | Evidence to inspect | Possible later intervention, not predetermined |
| --- | --- | --- |
| Information loss | Relevant local observation absent from the recipient's input | Selection or handoff support |
| Communication delay | Discovery/send/consumption times relative to dependent actions | Proactive notifications or event triggers |
| Information misuse | Correct sufficient information included before an incorrect action | Confirmation, referencing or validation |
| Coordination failure | Conflicting responsibility, interface or progress assumptions | Protocol and state synchronization |
| Communication overhead | Repeated discussion, tokens/time and lack of code progress | Redundancy handling or communication allocation |

Labels can co-occur. Keep transport delay separate from a sender's late decision
to communicate. Code bugs, task ambiguity and environment failures are separate
alternatives. A failed code test alone proves none of these categories.
Description is not causality; later controlled interventions are needed.

## Authorized Scope (2026-10-30)

User authorized three fixed feature pairs, one attempt each, no automatic paid
retry or expansion, and preparation of isolated local Docker environments.
No aggregate monetary cap was requested. This is NOT an unlimited run.

Choose the first listed pair in official lite.json for each of three
dependency-light Python repositories, before seeing model outcomes:
- pallets_click_task / task2068 / features 1,4
- pallets_jinja_task / task1465 / features 1,7
- samuelcolvin_dirty_equals_task / task43 / features 2,3

Mark these tasks as observed motivation samples, not untouched final-test data.
The sample is convenience-stratified, not representative of all CooperBench.

## Current Authorized Run (2026-10-30)

The user requested deletion of historical results, source cleanup/push, and one
new paid attempt for each of the same three pairs. Historical output directories
and their result documents are removed, not reused as evidence. These tasks remain
previously observed samples; deleting outputs does not make them unseen test data.

New output: outputs/cooperbench/isolated-pilot-20261030-03/.
New native gates: outputs/cooperbench/native-gates-20261030-03/.
No automatic paid retry, replacement task or expansion is authorized.

All members start runnable (all-members-ready-v1). token_budget=null disables
the cumulative-token stop. Retain 100 domain calls per worker, zero for the leader,
a 1,200-second active-run deadline, provider timeout 120 seconds/retries=0,
max_input_chars=800000 and the configured per-response max_tokens. Token/cost
telemetry remains enabled. There is no aggregate monetary cap or independent
communication-round cap. Prompts, policy, evaluator and limits are fixed before
launch; no tuning while the three attempts run.

## Admission and Resource Semantics

New worker preparation must pass base-history-only-v1 checks including unreachable
object pruning and an empty evaluator patch directory. Read-only verification and
artifact-grant protocol friction are now separated from communication failures.
Tool output is bounded independently of code snapshot export. Context/output
overflow is member-local; one truncated-output recovery turn is allowed.
The tool/time limits remain unchanged, with no cumulative-token cap. For future
policy comparisons, preregister a compute allowance such as model-call counts
alongside the wall-clock safety limit; do not choose it retrospectively or silently
reintroduce a cap for this run. Nontransferable member tool allowances prevent
one agent spending its peer's allowance. Reads and communication still consume
model tokens and wall time. Deadlines stop new work and refuse late actions;
joining in-flight calls and capturing terminal artifacts adds cleanup time.
These are operational resource limits, not an extra monetary stop condition.

## Gates Before Payment

1. Validate pinned source and official image identity; no hidden tests/gold in workers.
2. In isolated evaluator containers, require genuine base test failures and
   gold feature/joint success. An environment error is not base failure.
3. Run server regression tests and record resolved source, model and limits.
4. Only launch the three admitted attempts. A failing gate is reported, not
   silently replaced with another sample or an altered evaluator.
5. Retain all started attempts, including deadlock and resource failures.
   Independently merge/test frozen explicit or terminal code.
6. Report outcomes, member usage, cache telemetry, estimated costs, account-wide
   balance deltas and evidence-backed collaboration observations.

No efficacy, causal mechanism or best evolution target is established in advance.
