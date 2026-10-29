# Information-level Feedback

The feedback unit is a **decision requiring a fact with qualifiers**, not an
entire failed task and not a cited document id. Independent labels must record
the required fact, original observation/event, owner, intended recipient,
decision call, relevant sender/recipient quotes, uncertainty and reviewer.

## Evidence Ladder

1. Acquisition: did an executable tool actually return the needed correct fact?
2. Sharing: was it intentionally sent to the relevant recipient?
3. Transport fidelity: did encoding preserve the value, qualifier and intent?
4. Availability: was the message included in a model request before the decision?
5. Retrieval: for references, was original text returned by a successful read
   and subsequently included in a model input? A grant/ID is not a read.
6. Use and action: was the decision consistent with available evidence, and did
   the requested tool operation execute successfully?

Items 2/3/5 are the primary communication-policy targets. Delivery/scheduling
errors are substrate bugs, not evidence that a learned policy is needed.
Bad initial decomposition, inconsistent task/scorer specifications, acquisition
failures, reasoning after arrival, and execution failures remain separate.

`analysis/information.py` reconstructs decision-time inputs and correlates
queued/encoded/delivered/model-input receipts. It excludes the final answer from
its own input, future evidence and encoder contexts from worker knowledge.
Receipt evidence is deterministic. Semantic arrival, truth, correct use and
causal effect are deliberately NOT inferred from receipts or success/failure.
The `attribution` helper requires reviewed semantic fields and an explicitly
decision-relevant fact; missing data stays
unknown. It is a rule mapping for annotations, not an automatic semantic judge.
An available partial clue plus an incorrect final answer is not sufficient to
label post-arrival reasoning failure: require reviewed information sufficiency
or specific misuse of the fact. Otherwise use `available_but_failure_unresolved`.

Structured packets also include `excerpt_checks`: whether the claimed verbatim
text occurs in an earlier cited tool observation. Unresolved IDs, absent excerpts
and non-exact excerpts remain distinct. A mismatch may be formatting/paraphrase;
an exact match does not prove the claim or causal use. Semantic support stays
unknown until reviewed. Never count these flags as a semantic loss rate.
Document/tool-call IDs resolve only to earlier recorded observation windows.
JSON escapes are decoded, separate windows never joined, and failed tools excluded.
No hidden document read repairs provenance. Transport status distinguishes queued,
encoded, delivered and included in a model input; FYI non-reactivation is not
automatically a bug. See the [BCP cases](bcp-pilot-results-20261029.md) for acquired
facts that reached Leader before an abstention and resource-limited delivery.

`scripts/feedback.py OUTPUT --report-dir NEW_DIRECTORY` creates independent review
packets without paid calls. Complete and incomplete trajectories are distinguished.
The existing legacy loss-judge entry point is not used for these annotations.

## Pilot Example, Not a Causal Claim

In `paid-pilot-20261029-02`, validation-2 / Summary:

- DataAnalyst's handoffs at events 222 and 264 include Day 3 dinner
  `Chopsticks, Buffalo ($14, 3.6)`.
- At event 413 the audit again suggests this meal but also says leaving dinner
  blank is acceptable. That advice is conditional on a correctly encoded travel
  day, whereas the final `current_city` is merely `Atlanta`.
- Final Day 3 dinner is `-`; native grading fails `is_not_absent` with
  `No meal in day 3 is not allowed.` The final city representation also disagrees
  with the requested travel-day output convention.

Thus a missing dinner is NOT evidence that the restaurant fact never reached
the leader. Review the decision-input receipt before labeling; likely issues
include reconciliation of conditional advice and final representation. No
fact-restoration intervention has established causality.

Verified provenance: native observation event 46 (`e6`, DataAnalyst) contains
`Name=Chopsticks, City=Buffalo, Average Cost=14`. Messages m8/m9/m14 were delivered
at events 226/266/417 into leader contexts of lengths 13/17/22. The final decision
call is event 539, input length 32: these messages preceded that actual input.

A deterministic **grader-only** check (no extra LLM calls) compared three final
artifacts without modifying the original run:

| Artifact | Native and supplemental audit | Failing check |
| --- | --- | --- |
| Original | Fail | Missing Day 3 meal |
| Only correct Day 1/3 current_city to the existing transport's from/to route | Pass | None |
| Only fill Day 3 dinner with the already supplied Chopsticks, Buffalo | Fail | Dinner not in declared current city |

This locates the scoring failure in the final representation, not missing
restaurant evidence. It is not a stochastic model replay or a demonstration
that changing a communication policy would change the model's decision.

The same run includes DSML call syntax in encoder output at events 97 and 501.
That is a serializer/protocol failure, not a successful domain tool invocation.
Encoding now has a stable pure-serializer system prompt, no executable tool
schemas, and quoted source context. Requests must remain requests. Single fenced
JSON and optional null excerpts are normalized without changing factual fields.
Raw responses remain in traces; no invisible semantic repair is performed.

## Before Policy Updates

Build a reviewed set of positive and negative cases. In particular include
facts that arrived but were misused, tool failures, and task-specification
mismatches so a detector cannot label every failure as communication loss.
Report unknown cases and precision/recall against independent review. A suggested
policy change must reference the observed edge and failure category; one failure
does not authorize a general prompt rewrite.

Annotate only **decision-relevant** facts, with the task constraint/decision that
requires them. Do not count every omitted search row as loss. Keep three claims
separate: an edge omitted a fact; the fact was unavailable at the decision through
all paths; restoring the fact changes the outcome. Redundant direct tool reads
can erase the second effect even when the first is real. Model-input inclusion
does not reveal attention or establish correct use; verbal reasoning alone is
not causal proof. State/version and the artifact reviewed also matter: approval
of draft v1 does not validate a modified final v2.

Test a candidate on disjoint tasks with the same roles, tools and model. For
causality compare missing-fact restoration with unchanged-context repeat and a
matched irrelevant/control supplement, charging all calls. No updater or paid
judge is launched by this module. Runtime adaptation is not cross-task learning.

## Current Pilot Scope

At the user's request Full Context is excluded from further paid tests. The
completed frozen pilot used the same six tasks and four arms (24 runs). All received the same
explicit published benchmark-wide conventions, including round-trip completion,
travel-day city syntax and meal/lodging requirements. This is a disclosed task
clarification, not a scorer change. Old five-arm runs remain engineering evidence
only and must not be pooled with the clarified four-arm experiment.

See [verified results and reviewed cases](paid-pilot-20261029-03.md). The batch
had 18 correct, 2 incorrect and 4 incomplete runs. One wrong restaurant identifier
propagated across peers despite correct original observations also reaching the
Leader; another failure exposed an omitted cuisine-scoring convention. These
are different diagnoses and neither proves that needed information never arrived.
Two incomplete runs already contained passing drafts but did not finalize.

RSI should propose a change only after this diagnostic separation, then test on
disjoint tasks with the same controls. Do not train the updater to repair every
failure by increasing communication. More reports can consume the finalization
budget or reinforce a wrong value. Receipt extraction is implemented; reliable
semantic attribution and causal intervention remain research work.
