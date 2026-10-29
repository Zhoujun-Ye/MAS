# Information Exchange and Communication-policy Evolution

The fixed pool, bounded peer runtime and five static handoff forms now exist.
This document's richer message kinds, supersession/deduplication, causal replay
and updater remain a research design. No real-model efficacy result is claimed.

## Research contract

With a fixed capability pool and a frozen per-task TeamSpec, test whether agents
fail to deliver decision-relevant local findings, whether this causes errors,
and whether reusable communication-policy updates improve held-out outcomes at
controlled total cost. Task-adaptive team selection is NOT self-evolution.

Runtime asking, sending or choosing an excerpt is task-time adaptation. A policy
update creates a persistent version used on subsequent tasks based on permitted
historical feedback. Do not claim recursive improvement of the updater itself;
the operational RSI object here is the agents' reusable communication strategy.

## Fixed substrate versus learnable behavior

| Fixed substrate | Candidate policy decisions |
| --- | --- |
| Pool prompts, capabilities and permission profiles | Which local discoveries are worth sharing |
| TeamSpec, roles, initial assignments and allowed graph | Which allowed recipient needs a finding |
| Message schema, evidence ACL and scheduler | Whether/when to send proactively or ask |
| Model, context safety and resource limits | Which qualifiers/evidence to include in an encoding |
| Evaluator, task split and scoring rules | When a delivered message is insufficient; whether to read/request evidence |
| Routing policy and initial composition | When to suppress redundant notices or issue a correction |

Policy cannot expand the allowed graph, change domain access, alter roles,
increase budgets, edit grading or read hidden contexts. Choice of a permitted
recipient changes actual message traffic, not permission to communicate.

## Message contract

The proposed stable envelope includes sender, recipient, message kind, payload,
evidence references and an optional reply/supersession reference. Kinds cover
discovery, request, reply, conflict, correction and completion. The payload can
carry facts, qualifiers, uncertainty, state/version, an explicit question and
next-action dependencies. These are communication records, not new role prompts.

Use stable task-local message/evidence identifiers. Keep timestamps, random run
ids, storage paths and tracing metadata outside model-visible prompts. An evidence
reference is not a delivered fact; count available, delivered, read and used
states separately. Access only evidence allowed by the explicit communication
edge/protocol, not an unrestricted global observation database.

Send only queues delivery; receipt does not assert agreement. Deliver at safe
context boundaries and log exact recipient inputs. Requests have bounded waits
and explicit unresolved status, not recursive agent invocation. Route unresolved
conflicts to the leader without making the leader relay every ordinary peer message.

Deduplication must account for recipient, factual content, qualifiers and state
version, not just matching words. Never suppress a new recipient's first notice,
a failed-delivery retry, a correction or a superseding tool result. An invariant
delivery ledger belongs to the harness; semantic choice to omit a redundant
message belongs to policy and is auditable.

## Two axes, not one ambiguous ablation

The five initial forms (Full Context, Summary, Structured, Document Retrieval,
Adaptive) are STATIC communication baselines. Adaptive is a task-conditioned
policy; its label alone does not imply evolution. Keep composition and the
allowed graph fixed for every paired comparison. Retrieval permissions and
read costs are explicitly part of the treatment.

For end-to-end motivation, sender/recipient/timing decisions may diverge under
different communication policies. This measures a policy effect, not pure
serialization loss. To isolate encoding, replay the same frozen sender snapshot,
recipient, message boundary and downstream starting state, changing only the
encoding/access treatment. Prespecify whether additional reads are allowed in
that replay and charge them; otherwise a retrieval condition has changed too.

Do not compare an evolved Adaptive policy to an unevolved Summary policy and
attribute the whole difference to evolution. Evolution requires comparisons
within the same substrate and access regime, including an adaptive-but-frozen
baseline with matched model/budgets.

## Staged study

1. Motivation: freeze pool, router, per-task TeamSpec and all communication
   policy versions. Characterize insufficient sharing, transport loss and
   coordination errors. Judge semantic facts/qualifiers, not citation presence.
   Use independent human checks on a sample and keep ambiguous cases unknown.
2. Causal checks: at matched decision points, compare supported fact restoration,
   unchanged-context repetition and an appropriate matched control. Preserve
   tools, budget and stochastic replication rules. Observe whether restoring
   a missing fact changes the decision, not just whether full context scores higher.
3. Communication updates: only if earlier stages show a meaningful recoverable
   problem, generate reusable policy revisions from training-task feedback and
   compare to frozen and task-adaptive non-evolving baselines on disjoint tasks.
4. Routing comparison: optionally compare rule routing, LLM routing and fixed
   teams separately, holding the selected communication policy constant. Include
   planning/selection costs and solo-task coverage. Do not fold these gains into
   the communication claim.

## Update and validation protocol

Keep one policy version fixed through a collection batch. Collect traces and
outcome/constraint, semantic-arrival, redundant-communication, latency and cost
feedback. Trace labels must distinguish environment/provider errors, insufficient
task information, poor initial decomposition and missing communication. An opaque
scalar reward or a self-judged persuasive report is not enough diagnosis.

An offline updater may inspect approved TRAINING feedback and propose a versioned
prompt/rule artifact. It cannot mutate execution code, scheduler, permissions,
pool, TeamSpec or benchmark definitions. Runtime inference never sees gold answers;
any evaluator-derived training signal stays inside the declared training split.
Separate task identities and related task families to reduce leakage into transfer.

Validate candidate and incumbent on the same held-out validation tasks and frozen
TeamSpecs. Preregister acceptance criteria: quality improvement at an acceptable
total cost, or cost reduction under a quality non-inferiority constraint; include
uncertainty and constraint failures. Do not accept on semantic loss alone if task
quality worsens. Preserve every candidate, rejection reason and parent version;
no silent overwrite. Freeze a selected version before the untouched final test.

Policy selection uses validation data, so validation improvement is not final
test evidence. Count updater/feedback/judge/validation costs separately and report
both inference-only and training-amortized totals, with the amortization workload
stated. Do not hide a costly search behind cheap final inference.

## Necessity is falsifiable

Compare: a simple fixed policy, a carefully specified fixed policy, a policy
that adapts only to the current task, and feedback-updated versions. A one-shot
revision and a compute-matched static-tuning control test whether repeated
feedback is doing more than extra prompt engineering. All proposals/tests require
separate paid-run authorization; none are launched by this design document.

Evidence AGAINST the evolution hypothesis includes: no meaningful transmission
failures under adequate tasks/plans; fact restoration does not rescue errors;
a simple fixed policy closes the gap; gains vanish with matched budgets; or
updates improve seen tasks but not held-out families. In those cases, retain
the simpler policy or report a negative result. Architecture adaptation and
cache improvements do not by themselves demonstrate communication self-evolution.
