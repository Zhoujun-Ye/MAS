# KramaBench Pilot Failure Analysis

2026-11-01. Offline investigation only; no new model, judge or balance requests.
Evidence root on the server:
`/home/zhoujunye/MAS-information/outputs/kramabench-failure-analysis-20261101-01`.
`failure-analysis.json` binds the calculations, source hashes, original trace/report
hashes, reference replay and real-XLSX smoke. Historical paid artifacts are unchanged.

## Single: Estimand Mismatch, Not Interpolation Arithmetic

The original Single trace identifies 14 Malta records, years BP 6005 through 6412,
and correctly interpolates K at 6.005 and 6.412 ka: 8228.130402544642 and
8466.246945147157. It averages those **two endpoints**, giving **8347.1887**.
Trace events 42/48 show the selected dates and brackets; event 66 records the
saved pipeline execution. Independent offline recomputation matches these numbers.

The public query says "from the first and last time", which is ambiguous. The
hidden reference steps instead average annual interpolated values across the
interval. Single did not calculate that estimand. However, replacing endpoint mean
with interval mean is not sufficient to reproduce the gold answer:

| Convention on the original, unrounded time axis | Value |
|---|---:|
| Endpoint mean | 8347.1887 |
| Piecewise-linear time-weighted interval mean | 8477.8648 |
| Integer-year mean, both endpoints included | 8477.5473 |
| Integer-year mean, right endpoint excluded | 8478.1602 |
| Unweighted in-range sample mean | 8498.8555 |
| Published gold | 8577.5298 |

The pinned reference `solutions/archeology/archeology-hard-1.py` first rounds
`Age_ky.1` to an integer **before** multiplying by 1000. This loses sub-millennium
precision and creates duplicate years. Around the requested interval, its two
bracketing years have 5 and 13 tied rows. It sorts and takes the first row without
specifying a stable tie policy, then averages the half-open annual range of 407 years.
`Age_ky.1` and `Age_ky` themselves are identical in these inputs: choosing that
duplicate column is not the numerical cause.

The actual pinned reference was reviewed and replayed in the existing isolated
image, changing only the input path and appending diagnostic printing. With
pandas 2.2.3 it returns **8665.5244**, not the published gold. Explicit first/last
tie policies yield **11472.2999 / 8825.5533**, demonstrating sensitivity. We have
not established which historical environment or selection rule produced the gold.
Do not silently rewrite the answer key or credit Single as correct; equally, do
not treat this score alone as clean evidence of a model arithmetic failure.

## MAS: Submission Protocol and Shared Assumptions

The final leader call has `finish_reason=stop`, a 33,191-token prompt and a nonempty
12,137-character response. The run used 42/64 model calls and about 371/1800 execution
seconds. It did not hit a token/call/time ceiling. Its system prompt contained the
strict JSON requirement, but the request path had no API `response_format` setting.
The final response starts with prose and wraps its JSON object in a Markdown fence;
the strict parser correctly raises `JSONDecodeError`. The fenced object is valid
JSON when examined diagnostically and contains the same **8347.1887** answer.
This diagnostic extraction is not an accepted submission or a revised score.

We can establish the missing request constraint, not why the model chose this
presentation. Child prose may influence style, but that causal claim is untested.
Correcting the wrapper alone would not solve the answer mismatch.

MAS did consider an interval alternative. A reversed-bound integral initially
dropped all interior knots (event 152); the leader fixed it at event 164, yielding
8477.8648, but still selected the endpoint interpretation. The reproduction brief
(event 172) explicitly prescribed endpoint averaging and labelled alternatives
"NOT the answer". Agreement therefore checked the implementation of a shared
method, not the validity of the interpretation. Child findings did catch other
issues; this was not simply a failure to delegate or execute parallel checks.

## Confirmed Reader Defect

`inspect_file` advertised a first-ten-row XLSX preview but exposed an `offset`
argument that it silently ignored for XLSX. MAS events 36, 90 and 91 requested
later rows and received the first page again. The requirement analyst explicitly
reported this limitation. Shell-capable Single was not blocked by it; its effect
on the final MAS answer cannot be established from this one run.

## Repairs and Verification

- Generic harness/client: optional per-agent JSON response mode, passed on every
  root request, logged in `llm_attempt`, and not shared with child contexts.
  Session-specific final-format reminders also survive forced final calls.
- KramaBench adapter: identical JSON mode for Single/MAS roots, a fixed JSON shape
  example, explicit submission-validation failure classification, and unchanged
  strict parsing. No extraction, repair completion, retries or extra calls.
- Shared v3 guidance: distinguish estimands, time precision, interval direction,
  endpoint inclusion and duplicate-time policies; distinguish same-method
  reproduction from independent validation. No answer, reference steps or task-
  specific numerical constants were added to model prompts or tools.
- Generic XLSX reader: bounded row/column paging, dimensions and next offsets;
  oversized previews are flagged as errors. No shell permission was added.
- Server tests: **167 passed in 2.50s**. New tests cover JSON transport with thinking
  and tools, root/child separation, equal final-call budgets, unchanged reasoning,
  invalid/blank/truncated/fenced output with no retry, paging/EOF/window limits,
  and synthetic endpoint-versus-interval/reversed-bound counterexamples.
- Real XLSX smoke in the pinned image read all 14 Malta rows via two later windows,
  reached EOF, and selected a climate column window. The reference replay and all
  diagnostic containers used no network or credentials and were removed afterward.
- Paired scripted smoke: `outputs/kramabench-postpilot-offline-20261101-01`.
  Both arms completed with matching output contracts and no trace-integrity errors;
  Single used 4 scripted calls, MAS 15 including a child resume. This is transport
  verification, not a new task score or cache measurement.

The JSON option is documented by the [provider](https://api-docs.deepseek.com/guides/json_mode/).
It can still return whitespace-only content; this remains an explicit failure,
not a reason for an automatic retry. Live provider compliance and whether the new
guidance improves model reasoning remain unverified because no paid rerun occurred.
This inspected task is now a diagnostic case, not held-out acceptance evidence.
