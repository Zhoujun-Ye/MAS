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
automatically a bug.

`scripts/feedback.py OUTPUT --report-dir NEW_DIRECTORY` creates independent review
packets without paid calls. Complete and incomplete trajectories are distinguished.
The existing legacy loss-judge entry point is not used for these annotations.

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
