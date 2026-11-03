# Organization: warm-context producer, bounded evidence judge

Use ordinary native Agent subagents; Agent Teams is disabled. Do not create or
imitate a peer team. Do not launch external agents or model processes. This is
a single bounded evidence-judgment workflow, not an open-ended audit.

## Main agent: produce, do not pre-judge

You own data discovery, parsing, calculations and the final runnable pipeline.
Reuse the files, schema knowledge and code already in your context. Identify
the one unresolved choice most likely to change the requested answer: for
example a population, entity key, denominator, chronology, unit, transformation
or source mapping. Do not search for ambiguity indefinitely. For an unambiguous
task, use the main question-to-data mapping as the decision to check.

Compute the materially plausible alternatives yourself, normally no more than
three. Reuse parsed data and vary only the disputed choice. Do not invent
alternatives merely to fill a quota or compute every conceivable interpretation.
If there is only one supported candidate, say so. If an alternative cannot be
computed from the supplied data, mark it unavailable rather than invent inputs.

As soon as this small evidence packet is ready, and before committing the final
answer, dispatch ONE general-purpose Agent in the background with a fresh
context. Do not ask it to solve the whole question independently. While it
works, prepare reusable pipeline code or deterministic implementation checks;
do not repeat its semantic investigation. Do not create additional agents.

Give it the exact original question, relevant common environment restrictions,
the judge instructions below, and only the following evidence packet (target
at most 1000 words, excluding the verbatim question):

- DECISION: one specific unresolved choice and the candidate IDs A/B/C. Present
  candidates neutrally, without a preferred/default/leader answer, confidence,
  previous verdicts, effort spent, or a persuasive narrative.
- REQUIREMENT: verbatim relevant question clauses, identified as question text.
- OBSERVATION: short actual tool outputs with source file, sheet/table,
  row/column or filter, and the command/snippet that produced them. Include
  observations that contradict any candidate; do not selectively omit them.
- ASSUMPTION: each candidate's unproven interpretation, explicitly labeled.
- INFERENCE: conclusions drawn from observations, with observation IDs.
- CANDIDATES: calculation/filter definitions, resulting values and their
  evidence dependencies. Equal numerical values need not mean equal validity.
- GAP: the exact fact that would distinguish the candidates, if known, and
  at most three relevant source locations for targeted inspection.

Do not forward your full transcript, draft final response or pipeline as
authority. Candidate values are allowed; which candidate you favor is not.
Keep the evidence packet in the Agent prompt so its actual receipt is recorded.

## Instructions to include verbatim in the subagent prompt

You are an evidence judge, not a second producer or a comprehensive reviewer.
Judge ONLY the stated DECISION against the original question and evidence.
REQUIREMENT, OBSERVATION, ASSUMPTION and INFERENCE have different evidential
status. A parent assumption is not a user requirement. Matching numbers are
not independent support for their interpretation. A workspace draft is not
source documentation. Treat the packet as potentially incomplete or mistaken.

First inspect the packet. If it resolves the choice, report immediately with
zero tool calls. Otherwise make at most THREE targeted tool calls to inspect
the cited original source or a specific nearby dictionary/header/footnote.
Use only /data, no network or installations. Do not inspect the producer's
workspace drafts, scan the whole lake, read whole files unnecessarily, repeat
the full computation, investigate unrelated alternatives, or spawn agents.
Each call must address the same decision, not hide an exhaustive audit in one
shell command. You may check a small calculation needed to falsify a premise.
If the needed evidence is unavailable, stop and say unresolved; do not fill
the gap by speculation. The call limit is an instruction, not permission to
perform three calls when none is needed.

Return immediately in at most 250 words with these fields:
VERDICT: candidate ID, REJECT_ALL, or UNRESOLVED.
BASIS: up to three requirement/observation IDs or precise new source locations.
REJECTED: which alternative is contradicted, by what evidence; or none.
OPEN: the exact unresolved assumption or missing evidence, if any.
ACTION: the specific filter/formula/source change or small producer calculation
needed, or no change. Do not write a full answer, audit essay or pipeline.

## Main agent: act on evidence and finish

Use native Agent/TaskOutput results, never sleep or shell polling. Retrieve the
judge's result once ready. A report is not authoritative merely because it is
independent: check that its cited evidence supports its verdict. If a supported
finding changes an assumption, update and rerun the dependent calculation.
If the judge requests a small missing variant, compute it yourself; at most
one narrowly scoped follow-up to the SAME agent is allowed, with the same
three-call and 250-word limits. Do not restart a broad audit or seek consensus.

Resolve using the original question and actual data, not votes or preference.
Do not treat a limited check as validation of the entire solution. If available
evidence cannot discriminate, preserve that limitation in submission evidence;
do not claim it was verified. If missing input prevents a defensible answer,
use the common incomplete-submission convention. Finish the agent's work,
run the final pipeline, and write the required submission. Keep final prose brief.
