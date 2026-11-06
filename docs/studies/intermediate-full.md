# Intermediate Results And Decision-v3

2026-11-05. User-authorized local repair, isolated server offline tests and read-only
historical replay. No paid calls, active-server deployment, historical code execution,
environment installs or modifications to old runs.

## Decision-v3 Review Verification

Isolated stage: `/home/zhoujunye/mas-stages/20261105-decision-v3-review`.
Receipts: `/home/zhoujunye/mas-data/receipts/decision-v3-review-20261105/`.
Native fake-provider probes pass for FULL and OBS (concurrency 2), and separately
full-prompt-only (concurrency 1), with no real credentials or paid requests; owned
containers were removed. These verify runtime wiring, not solver effectiveness.

Read-only replay of the same three historical summaries includes 100 Krama runs:
65 correct, 24 incorrect and 11 partial/ungraded. Explicit intermediate records
remain absent. Final-answer conflicts occur in 8/24 incorrect and 1/65 correct
runs; one incorrect submission is absent from captured final candidates. Gold
coverage among incorrect final candidates remains 0/24; weak intermediate hints
cover 3/24 under the recorded numeric tolerance. Those hints are now hidden by
default and never gate submissions. These are review-load/coverage measurements,
not corrected accuracy or independently annotated grouping false-positive rates.
Historical pipelines were not executed or parameterized in this repair.

## Comparable Quantities

Two result types are intentionally separate:

- **Explicit measurement**: quantity, statistic/estimand, population, period, unit,
  and dataset must all be present. Exact whitespace-normalized dimensions define
  the target; analysis options live in `variant`, not in the target. Different
  dimensions never silently merge. Units are not guessed or converted, and names
  are not fuzzily matched. Producers can mark the requested task target explicitly.
- **Possible measurement**: legacy labeled numbers, numeric JSON paths and labeled
  CSV/tabular cells retain their labels and row/column context. They are useful
  retrieval hints, not proof of a common estimand, and NEVER create a submission
  gate. Bare numbers, directory timestamps and answer-list elements are excluded.

`harness/evidence_mas/measurements.py` supplies `measurement` and `emit_measurement`
for parameterized computation code. The code emits each computed value together
with its target and option settings; the model does not hand-enter candidate values
through an MCP tool. The existing capture hook collects these stdout records.
Tests compute both missing-value policies on synthetic data and verify grouping,
while changing each target dimension verifies separation. This demonstrates wiring,
not performance on Krama. Source-declared semantics still need independent scrutiny:
neither a label nor a successful Bash command proves a valid computation.

Views are paginated and anonymous. Repeated identical results do not change a
selection snapshot; any new distinct declared final-answer value invalidates the choice.
Intermediate provenance is retained separately from the decision fingerprint.
All declared answers and answer_target measurements compete in one final decision,
even with different populations, units or other target dimensions. Their original
interpretations remain visible. A singleton requires a matching submission, without
a selection ritual; empty/null remains incomplete. Uncertain coverage
remains unknown, not an inferred successful decision.

## Review Repairs

- OBS/FULL import the exact existing Native (N) prompt. Structured is unchanged.
  Task, rules and organization are now ordered as in N, with workspace guidance last.
  N's native general-purpose worker differs from evidence-worker: N -> OBS is NOT a
  clean mechanism comparison. Primary comparisons must use OBS -> FULL and the
  explicit full-prompt-only control (identical FULL guidance and OBS tools, no gate
  or decision tools). The control is opt-in and does not expand default study budgets.
- FULL exposes all five OBS read/trace tools plus four decision tools. Causal nesting
  takes precedence over advertising only four total tools. It is not gate-only.
- Benchmark workers receive shared task/tool limits without the final file contract.
  Lead-only task rules are not placed in evidence worker-visible rule files.
  Both modes deny worker Write/Edit/MultiEdit and Bash operations mentioning
  submission.json. This is conservative interface enforcement, not an OS sandbox:
  dynamically constructed paths, aliases and same-UID writes are not authenticated.
- Valid final artifacts are copied and scored once even when the protocol rejects
  them. `raw_score` and `compliant_score` share the same grade; protocol rejection
  gives compliant score zero, not a second model call. Unrun paid judges remain
  pending/unknown. Matrix and external scoring exports keep both metrics.
- Numeric values compare against numeric text only for the textual final_answer
  contract. Whole/indented JSON, extra fields and safe Python literal dictionaries
  parse without executing contents. Empty/null answers remain allowed incomplete
  submissions. Task quotations normalize whitespace.
- Native lifecycle determines live pending executions. Calls from stopped/unknown
  agents remain orphaned observations rather than permanent locks. After owned
  container teardown, the host ignores stale lifecycle liveness; MCP cannot request
  this override. Lost observations remain visible as missing coverage.
- Neither OBS nor FULL injects per-tool observation IDs. Worker descriptions reference
  intermediate findings, not the retired ledger. Old docs are marked historical.
- Successful local-agent TaskStop responses mark workers stopped; pre-call and
  failed stops do not. This follows the observed native response schema.
- Typed measurement values support finite numbers, strings and lists. Malformed
  records report reasons and counts, never silently become weak hints. Possible
  hints require decision_view(detail=true); the default only shows explicit results.
- Parsed output is cached by content plus parser source hash. Disposable cache
  corruption falls back to parsing; read-only analysis never writes caches. Cache
  digests detect corruption, not malicious same-UID modification.
- `Store(..., readonly=True)` uses SQLite mode=ro without directory creation,
  chmod, schema/index migration, audit writes or blob writes. Host checks and audits
  use it; replay reads original logs directly. Corrupt stores reject the protocol
  without throwing away the raw grading path.

## Historical Replay

Source stage: `/home/zhoujunye/mas-stages/20261105-intermediate-full`.
Replay receipt: `/home/zhoujunye/mas-data/receipts/intermediate-full-20261105/replay-final.json`.
The receipt binds source-summary and artifact hashes, separates T/N batches, and
exports only counts. Gold is consulted only AFTER extraction/grouping, to measure
coverage. Numeric coverage uses the frozen grade's scale_aware_v3 tolerance;
strict exact matching is also retained. The parser was refined on this reusable
validation set; this is not held-out validation.

The three summaries contain 300 slots, including interrupted attempts. Krama has
100 runs: in-run reports label 65 correct, 24 incorrect and 11 partial/ungraded.
No new judge was run to reconcile this with the supplied review's 30-error set.

| Krama condition | Recorded errors | Gold in intermediate hints (official tolerance) | Broad numeric occurrence upper bound | Advisory conflicts in correct runs |
| --- | ---: | ---: | ---: | ---: |
| Single | 5 | 1 | 3 | 4/13 |
| Structured | 4 | 0 | 2 | 10/14 |
| Native | 5 | 1 | 4 | 8/12 |
| FULL (historical) | 5 | 0 | 2 | 10/13 |
| OBS (historical) | 5 | 1 | 3 | 4/13 |

Thus intermediate hints add **3/24** error-run gold occurrences where declared
answer extraction finds **0/24**. Broad number matching sees **14/24**, but this
is only a diagnostic upper bound: incidental occurrences are not verified answer
computations. Exact matching alone misses rounded intermediate values.

Weak grouping produces advisory conflicts on **36/65** recorded-correct runs.
This is review workload, NOT a measured grouping false-positive rate: a correct
final answer can coexist with genuinely conflicting intermediate calculations.
There are no independently annotated same-estimand pairs in these old traces, so
the real grouping false-positive rate remains **unknown**. Calling it zero would
be unjustified. These hints are not promoted into gates.

The historical runs contain no six-dimension explicit measurement records; they
cannot validate that new contract's real-task coverage. DataClaw/HDR shadow-grade
availability in the in-run reports is insufficient for a correctness-conditioned
false-alarm estimate. No accuracy improvement is established. The next necessary
evidence is independently checked target annotations/parameterized calculations,
not a paid run that treats weak labels as reliable targets.

## Verification

- Final isolated-server suite: **533 passed, 2 skipped in 13.88s**. Skips require
  the optional pinned-upstream integration fixture. No local tests were run.
- Real pinned Claude CLI with a strictly fake provider passed FULL and OBS;
  FULL emitted typed intermediate records, grouped both variants and rejected a
  mismatched selected answer. Native condition concurrency was 2; 12/14 synthetic
  requests, no real credentials, network=none, both owned containers removed.
  Receipt: `/home/zhoujunye/mas-data/receipts/intermediate-full-20261105/native-verified`.
- Offline regressions cover same-value reruns, target dimensions, table context,
  numeric/text submission types, empty answers, lifecycle/pending behavior,
  worker submission denial, corrupted/readonly stores and retained shadow answers.
- `git diff --check` passed. The local runtime/workflow source hashes were compared
  with the tested server stage. Active `/home/zhoujunye/mas` was not deployed.
- Replay artifact hashes bind the examined inputs. Subsequent host-check-only fixes
  did not change the recorded extraction algorithm or replay counts.
