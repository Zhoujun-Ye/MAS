# Hard Boundaries and Controlled Information Access

The generic architecture is Leader decomposition -> independent workers ->
Information Harness -> authorized Shared Workspace -> Leader synthesis.
BCP supplies public requests, domain tools and grading, not its own architecture.
TravelPlanner source and launchers are retired; historical outputs stay unchanged.

## Ownership

- `harness/planning.py`: one tool-less Leader planning call using public input and
  the fixed capability/tool catalogue. It produces concrete assignments and
  persists the TeamSpec and planning cost once, before communication conditions.
  The planning and execution phases use the same Leader capability template;
  execution starts from the frozen plan, not an unlogged planner conversation.
- `harness/pool.py`: fixed role templates and capability bindings. Leader has no
  domain capabilities. Selection never creates role prompts or grants tools.
- `harness/agent_team.py`: independent append-only conversations/tool histories,
  queued direct peer messages, controlled encoders, completion and finalization.
  Nonempty Leader domain grants are rejected, even from a custom adapter.
- `harness/information.py`: SharedWorkspace stores immutable evidence, artifacts,
  private memory notes and state revisions. InformationHarness mediates ACLs,
  reads, searches, integrity verification and workspace recovery.

## Hard Boundary

Domain observations are initially readable only by their producer. The public
task and frozen assignments are shared; private observations and memory are not.
No model receives a global workspace dump or another agent's live history.
Leader may communicate and inspect explicitly granted workspace records, but
cannot invoke any domain tool, including by hallucinating a tool call.

`publish_artifact` creates a private record. `previous` appends an owner-only
revision without overwriting the old one or inheriting its recipient grants.
Explicit `artifact_ids` in send/finish requests select revisions to share.
A bare worker completion does not automatically share its private artifacts.
Evidence uses the existing evidence IDs and observation provenance events.

Summary/Structured deliver encoded text, not original-record read grants.
Document Retrieval/Adaptive grant only explicitly selected records to the named
recipient. Adaptive searches only that recipient's authorized records. Full
Context materializes the sender snapshot at an explicit send boundary; it is
not unrestricted access to every participant or to the underlying workspace.
Artifact reads, verification and recovery consume the shared read budget.
All new tools/schemas, roles and isolation version enter the frozen control digest.
Old plans and manifests must not be reused for this architecture.

## Verification and Recovery

Records carry owner, kind, immutable ID, previous revision and content digest.
`verify_artifact` checks integrity and recorded origin, not whether the content
is true. Incorrect claims remain possible and are not silently corrected.
`recover_artifact` rematerializes an authorized exact revision; it cannot recover
another agent's private context or grant access by guessing an ID.
`InformationHarness.recover` rebuilds records and ACLs from workspace trace
events with digest checks. It does not resume conversations, replay domain
actions or launch paid inference. Traces are trusted local audit artifacts, not
cryptographically signed proof against a malicious filesystem owner.

## Evidence Limits

The enforced asymmetry is between domain-tool workers and a tool-less deciding
Leader. Workers may share domain tools; neither disjoint corpora nor a single
agent capacity bottleneck is claimed. Dependency and completion requirements
are in Leader assignments, not an executable DAG. Schema validation does not
certify decomposition quality. This is model/tool-boundary isolation, not an OS
sandbox for untrusted adapter Python or arbitrary shell/filesystem tools.

Wrong-value propagation, coordination-budget exhaustion and distributed evidence
coverage remain hypotheses requiring decision-time traces and controlled tests.
The runtime does not label a failed answer as information loss automatically.

## Offline Verification (2026-10-29)

On the standalone server, `pytest -q` passed 84 tests. Coverage includes generic
planning/reuse, forbidden Leader grants and forged calls, all five communication
forms, direct peer artifact delivery, unauthorized reads, immutable revisions,
corruption detection and workspace/ACL recovery without cross-condition reuse.

BCP native BM25 integration completed six scripted Leader plans and 24 scripted
team runs (six questions, four forms), with matching per-task control digests
across forms and valid traces. No paid calls or model-quality measurements.
Server evidence: `/home/zhoujunye/MAS-information/outputs/browsecomp_plus/hard-isolation-offline-20261029-02`.
Verified source digest: `9d33d1daa544d6f4`. Real-model decomposition quality,
semantic verification and causal information-loss effects remain untested.
