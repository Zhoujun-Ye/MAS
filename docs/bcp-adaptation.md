# BCP Tool Adaptation

BCP is a candidate, not an approved main benchmark. It adapts the generic
Leader planning and Information Harness interfaces. This document does not
authorize paid execution or reuse any previous run authorization.

## Data and Tools

Reuse the verified official test copy and BM25 index under agent-team read-only.
Preparation hashes the index files and checks test IDs against pinned evidence
qrels. Never modify files in the agent-team project.

- BM25 uses the pinned Anserini implementation and index; JVM calls are serialized.
- `search` returns default three, maximum five hits, each with the first 1500
  characters and explicit continuation offsets/total length.
- `open_document` reads a document window (default 6000, maximum 12000 characters).
- `find_in_document` locates literal text and returns at most five contextual
  windows with offsets. No semantic retriever or hidden LLM summarizer is used.
- Tool permissions are frozen per task across communication conditions. Cached
  handoff evidence reads and new domain document reads are accounted separately.

This is an adapted interface, not exact reproduction of the official
search-only/token-truncation setting. Agent contexts remain append-only.

## Planning and Evaluation

Leader sees the public request and fixed capability descriptions, never answers
or qrels. Saved TeamSpecs are reused across conditions; no cross-condition
transcripts are shared. Leader has no domain tools.

Final output is JSON with a short answer, reasoning and docid/claim/quote
citations. Normalized exact matches are positive automatic checks, not official
LLM-judge scores. Nonmatches remain `needs_review`, not automatically incorrect.
Manual grading must be stored separately with provenance. Grading feedback never
enters inference. Quote provenance checks are not semantic or causal judgments.

Report completion separately from correctness, all planning and inference costs,
finalization modes, unfinished assignments, delivery/read receipts and cache use.
Acquisition failures are not communication loss; evidence available through
another path must be distinguished from edge-level distortion.

The retained bounded driver requires explicit new authorization for its scope;
its authorization flag alone does not grant permission. New settings require a
new output directory. See [admission gates](experiment1.md).

Sources: [official code](https://github.com/texttron/BrowseComp-Plus),
[official test data](https://huggingface.co/datasets/Tevatron/browsecomp-plus).
