# BCP Agent-Team Pilot

## Authorization and Selection

The user authorized six official test questions x four forms (24 team runs) and
six initial Leader planning calls, one per question. No paid judge, simulator,
extra planner repair, sample expansion or automatic replay is authorized.
Full Context remains excluded. The earlier engineering commit is `eca47f2`.

New adapter, not the retired star/relay implementation. Read-only reuse of the
verified 830-question official test copy and BM25 index under agent-team; no
files in that project are modified. Preparation hashes all 15 index files and
checks test IDs against the pinned evidence qrels. Data SHA256:
`44b80cc9fcd9dd5a44aa09292c2165364b0c0e9df26c9cd6c11846165a0916b7`.

Selection is frozen before inference: public query length 150-1600 characters,
exclude previously run IDs in this project's old BCP outputs, rank by
SHA256(`bcp-team-20261029:` + query_id), take six. Selected IDs:
**1214, 268, 233, 53, 769, 351**. Answers, relevant-document counts and outcomes
were not selection inputs. A public-query review found multiple biographical,
temporal, relational or event clues in all six. This is not proof that each
requires multiple documents or that the sample is cheap/non-saturated.

These are a diagnostic subset of the official test split, not a new official
split and not necessarily unseen by other projects or model training.

## Frozen Execution

Leader sees the complete public request and fixed role descriptions, not the
answer or qrels. One call selects 2-3 complementary workers and Leader, assigning
specific clue groups and verification dependencies. System prompts/capabilities
are fixed. Each saved TeamSpec is reused verbatim across the four conditions.
Invalid planning stops without an extra paid repair. All roles get the full
public request. No cross-condition transcripts are shared.

Arms: Summary, Structured, Document Retrieval, Adaptive. Common settings:
`deepseek-flash`, high thinking, 32768 maximum completion tokens; 50 shared
domain calls, 64 total model calls including encoders, 28 messages, 12 evidence
reads, 800000 input characters, two calls reserved for finalization. Three runs
in flight with rotated form order. No monetary ceiling; this does not remove
the frozen resource caps. Cache reuse is telemetry, not a stop condition.

An incomplete/error execution stops new paid work for inspection; already active
calls are logged and interrupted cooperatively. Existing results/traces remain
immutable. A different setup requires a new directory and explicit replay scope.

## Tool Adaptation

- BM25 uses the pinned Anserini implementation and index; JVM calls are serialized.
- `search` returns default three, maximum five hits, each with the first 1500
  characters and explicit continuation offsets/total length.
- `open_document` reads a document window (default 6000, maximum 12000 characters).
- `find_in_document` locates literal text and returns at most five contextual
  windows with offsets. No semantic retriever or hidden LLM summarizer is used.
- Domain tools and permissions are identical across conditions. Agents can
  independently retrieve a document even in Summary; this is not artificially
  prevented to create communication loss. Cached handoff evidence reads differ
  from a new domain document read and are accounted separately.

This is an adapted tool interface, not a claim of exact reproduction of the
official search-only/token-truncation setting. Bounded tool windows are common
to all arms; agent contexts themselves remain append-only and untruncated.

## Evaluation and Diagnosis

Final output is explicit JSON: short answer, reasoning and docid/claim/quote
citations. A normalized exact answer match is a positive automatic check, not
an official LLM-judge score. Nonmatches remain `needs_review`, not automatically
incorrect. Any manual grading must be stored separately with provenance.
No answer, qrels, grading feedback or repaired final answer enters inference.

Record normal versus budget/message-limit finalization, unfinished assignments,
delivery/read receipts, retries, all call usage, cache and account balance.
Planning costs are outside the `runs/` aggregate and must be added explicitly.
Completion does not mean correctness; exact matches do not prove valid evidence.
Quote provenance checks are not semantic or causal loss judgments.

Review decision-relevant facts across acquisition, sender intent, encoded
handoff, recipient input and final use. Keep correct facts available by another
path separate from edge-level distortion. Missing retrieved evidence is an
acquisition failure, not loss in communication. No causal replay is included.

## Server Commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/browsecomp_plus/prepare.py
.venv/bin/python scripts/browsecomp_plus/offline.py --output outputs/browsecomp_plus/NEW_OFFLINE
# Only within the explicitly authorized scope:
.venv/bin/python scripts/browsecomp_plus/run.py --authorized-6-plans-24-runs --output outputs/browsecomp_plus/NEW_PAID
```

Sources: [official code](https://github.com/texttron/BrowseComp-Plus),
[official test data](https://huggingface.co/datasets/Tevatron/browsecomp-plus).

## Verified Preflight

Server: 55 tests passed (exit 0); all 24 scripted team/native-index executions
completed with matching per-task controls and valid traces. Latest offline
artifact: `outputs/browsecomp_plus/offline-team-20261029-02`, source digest
`3ae17f9a0f58ecd3`. No provider calls in preflight. Planning is launched separately
with `--plan-only` for inspection, then the same directory resumes using saved
plans without another planning call. Balance intervals distinguish both phases.
