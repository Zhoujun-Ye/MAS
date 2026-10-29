# BCP Pilot: Results and Repairs

## Verified Completion

Server directory: `/home/zhoujunye/MAS-information/outputs/browsecomp_plus/paid-team-20261029-01`.
Frozen inference: commit `1e203cf`, source `3ae17f9a0f58ecd3`, three concurrent
experiments, six once-only Leader plans and 24 team runs. Execution lasted
2026-10-29 14:16:56 to 15:12:32 UTC (55m36s). Exit: 0.

24/24 submitted: 22 `workers_completed`, two `budget_finalization`, zero
incomplete/error results, zero retries. All trace integrity checks passed. Every
planning trace contains one call; each task has one identical plan/control digest
across its four forms. No paid judge, replay or extra planning call was used.

## Outcomes

All four forms produced the same coarse outcome per task:

| Task | Outcome in all four forms | Review |
| --- | --- | --- |
| 1214 | Irrfan Khan with expanded birth name | Identity equivalent; reference spelling differs |
| 268 | Sheikh Mohammad Abdullah | Exact match |
| 233 | Chris Jericho | Exact match; some supporting clues remain unverified |
| 53 | Norman Naimark | Exact match |
| 769 | `unknown` | Abstention, not incomplete execution |
| 351 | `unknown` | Abstention, not incomplete execution |

Original grades remain **12 exact matches, 12 needs-review**: four name variants
and eight abstentions. Manual identity review: task 1214's reference says
`Sahabzade Irrfan Ali Khan`; documents 7433/2945 say `Sahabzade Irfan Ali Khan`.
The single-r spelling was already in the source, not corrupted by handoff.
Summary evidence: e17/t93 and Leader's e23/t117. This review does not silently
change strict grades or claim an official judge score.

## Resources

| Form | Model calls | Prompt tokens | Output tokens | Weighted cache hit | Estimated USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Summary | 301 | 7,736,816 | 352,085 | 78.47% | 0.4794 |
| Structured | 314 | 8,433,196 | 379,769 | 79.63% | 0.5057 |
| Document Retrieval | 311 | 8,879,215 | 380,032 | 79.30% | 0.5249 |
| Adaptive | 294 | 8,095,082 | 359,446 | 77.97% | 0.5021 |

Teams cost an estimated USD 2.012049; planning adds USD 0.005676: **USD 2.017725**.
Balance decreased CNY 13.15 (227.59 to 214.44); shared-key activity/billing delay
prevent exclusive attribution. These are alternative accounting views, not
additive costs. Retrieved evidence is counted in subsequent measured inputs.

23/24 runs used all 50 shared domain reservations; one used 41. There were 258
refused over-budget attempts. Five malformed calls consumed old reservations
without retrieval. The shared cap remains 50 after repair, not per-agent quotas.
210 encoder calls had 47.98% cache reuse, versus 87.32-88.74% for worker/Leader
roles. This cost concentration is not proof of a cache defect or parallelism
penalty. No C0 comparison or paid six-way concurrency comparison was performed.

## Information Attribution

- **769:** No form retrieved any of the six annotated evidence documents.
  Recorded excerpts/reports also show no verified institution. This supports an
  acquisition bottleneck, not a demonstrated acquired-then-lost fact. Qrels alone
  cannot prove every unannotated document irrelevant.
- **351:** Adaptive hit no annotated document. Structured/Retrieval saw a leading
  window of 7874, not the required award evidence. Summary did acquire a partial
  clue in 50448: Adichie's statement that dissatisfaction is necessary for a writer.
  Its path is e39/t183 -> queued t347/m7 -> encoded t358 -> delivered t374 -> model
  input t377, before final decision t396. Leader acknowledges it at t379. This
  fact arrived; the award year/category remained unverified. Candidate exclusion,
  date interpretation and missing evidence are not proof of handoff omission.
- **233/Retrieval:** Finalization t453 leaves researcher unfinished and solver's
  m10 (queued t445) unencoded. Leader nevertheless answers correctly from prior
  information. This is resource-limited transport noncompletion, not demonstrated
  harm. We do not inject pending raw reports as a hidden Full Context fallback.
- **769/Retrieval:** Finalization t495 has no unfinished workers or pending
  messages. Its unknown answer is not an old termination deadlock.

Of 210 queued messages, 197 entered a later recipient input, 12 were delivered
without another call and one was unencoded. Completed workers intentionally stay
idle on FYI messages; these are not automatically 13 harmful omissions.

After source-resolution repair, 473 structured fact entries contain 281 exact
observed-source excerpts, 109 absent excerpts, 53 unresolved primary sources and
30 non-exact excerpts. Some unresolved references cite teammate messages instead
of native observations. These are provenance flags, **not semantic loss rates**.
An exact quote does not establish entailment, relevance or correct use.

## Systematic Repairs

| Observed issue | Repair |
| --- | --- |
| Leader misused worker completion 12 times | Remove tool from Leader; clarify role-specific completion |
| Five `k=10` calls spent budget | JSON Schema validation before reservation; explicit range error, no clamping |
| Five ungranted-ID sends/completions | Expose authorized observation IDs; distinguish docids from grants; actionable rejection |
| Shared budget mistaken for individual/per-tool | Append current shared state and explicit global exhaustion notice |
| Requests could silently default to FYI | Require explicit `requires_reply`; no prose-based intent inference |
| Failed tool outputs became evidence | Exclude failures and legacy failed observations from evidence audits |
| Legal docids/tool IDs unresolved in diagnostics | Resolve earlier decoded observation windows only; no full-document fetch or snippet stitching |
| Partial grading looked like 100% overall | Report coverage/graded-only rate; leave overall rate/CI unset until complete |
| One arrived fact implied sufficient task information | Require reviewed sufficiency or specific fact misuse for reasoning attribution |
| Experiment concurrency hardcoded to three | `--concurrency 1..16`, default six; freeze it in manifest and test parallel native tools offline |

Denied reads/empty queries no longer consume evidence-read allowance. Contexts
remain append-only with stable role/tool prefixes. No timestamps, run IDs or
other workers' private facts enter the operational state. ACLs remain enforced;
invalid grants are not silently dropped or granted.

These changes address confirmed interface/accounting/diagnostic defects, not all
possible model mistakes. No gold aliases, test-specific search hints, index
changes, higher limits or learned communication policy were added. Better paid
accuracy/cache/cost is **not measured**. This pilot neither establishes harmful
information loss nor proves its absence.

## Verification Artifacts

Original paid artifacts are unchanged. Separate server reports:
`outputs/browsecomp_plus/audit-20261029-02-summary/0-runs.json` and
`outputs/browsecomp_plus/audit-20261029-02-feedback/` (24 review packets).
Final server verification: **63 tests passed**, exit 0, 15.40s. Native BM25 plus
scripted models completed all **24/24** cases at concurrency six, with matching
per-task controls and valid traces; paid calls: **0**. Artifact:
`outputs/browsecomp_plus/offline-team-20261029-05`, source digest
`d91a885189cd48ca`, verified against the deployed source. The latest paid-artifact
mtime remains the original execution end, 15:12:32 UTC.
Scripted tests establish engineering behavior, not model efficacy.
New paid work requires authorization and a new directory; these six tasks are
development evidence, not a held-out validation set for this repair.
