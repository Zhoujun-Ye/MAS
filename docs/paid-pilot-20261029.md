# Paid Pilot Engineering Stop

Authorization: six tasks x five forms (30 logical runs), no monetary ceiling,
no sample expansion. The pilot uses held-out official validation tasks, not the
official test split: 1, 2, 60, 61, 120, 121. No paid judge was invoked.

Server output: `outputs/travelplanner/paid-pilot-20261029-01`.
The batch was stopped after three results, with three additional executions in
flight. Missing run_end represented interruption, not a wrong answer. The user
subsequently explicitly requested deletion of this stopped batch's raw traces.
Its manifest, three result summaries and balance ledger remain for cost and
engineering provenance, excluded from the rerun. No process from this pilot
remains active.

Observed results on validation-1:

- Structured: incomplete, optional `verbatim: null` rejected by strict schema.
- Full Context: incomplete, recursive handoff envelopes exceeded input limit.
- Summary: completed conversation, invalid-JSON final answer; not native-scored
  itinerary correctness. The model emitted a coordination recap rather than the
  required itinerary array.

These observations establish engineering defects, NOT semantic information loss
or causal attribution. No success rate across the six-task sample is reported.

Recorded account balance: CNY 238.54 at start, CNY 237.72 at engineering stop,
delta CNY 0.82. Shared-key activity and delayed billing can affect attribution;
logged token estimates omit any in-flight response lost on termination.

Fixes after stopping, not injected into the running study:

- Full-context inline DAG frames avoid recursively copying identical ancestor
  frames. All referenced evidence is included inline, without a read tool.
- Optional null verbatim fields normalize to absent fields; mandatory facts and
  qualifiers remain unchanged. Other schema errors still fail validation.
- A common final-format contract rejects non-itinerary prose and requests a
  corrected answer within the existing total model-call cap. No hidden parser
  model or extra uncharged recovery call.
- Premature leader finalization waits for a new report rather than busy polling.

Server offline regression at that stop: 38 passed, exit 0. The fixes had
not yet been verified by a second paid batch. Repeating the same 30 logical runs
in a new frozen output directory was explicitly authorized by the user. Do not
merge old and repaired results or expand tasks silently.

Subsequent update: the user excluded Full Context. A new four-form batch has
finished; see [its separate results](paid-pilot-20261029-03.md). This document is
the original engineering-stop record, not the current completion status.
