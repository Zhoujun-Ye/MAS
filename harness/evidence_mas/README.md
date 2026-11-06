# Shared Evidence Workspace

Active FULL now uses **decision-v3**: OBS observation tools plus four decision tools,
typed intermediate measurements, anonymous candidates and a host-side consistency
check. FULL/OBS share the exact existing Native (N) organization prompt; Structured
remains the unchanged separate baseline. Protocol-rejected raw artifacts remain
eligible for the same one-time authorized shadow grading. See
`docs/studies/intermediate-full.md` for current behavior and verification.
The legacy ledger API documented below remains for historical evidence and fixtures;
it is not the active FULL interface.

## Historical Ledger Reference

The following describes the superseded ledger condition, not decision-v3. Its
Structured composition and lack of a submission gate are historical facts only.

This is one reusable evidence workspace for ordinary Claude Code subagents:
Observations, Issues & Candidates, Evidence Links, and Selections share one
run-bound store and MCP implementation. It is opt-in and not
connected to the frozen baseline automatically. No Framer, judge, executor,
scheduler, automatic model calls or automatic submission is included.

## Components

- `store.py`: run-bound SQLite transactions, content-addressed immutable payloads,
  versioned Issue/Candidate/Selection/EvidenceLink, execution/outcome registration,
  dependency validation and transitive stale views.
- `hook.py`: records PreToolUse/PostToolUse/PostToolUseFailure. Start and terminal
  records share an observation ID with preserved revisions; interrupted calls
  without results remain unknown/missing. Duplicate native events are idempotent.
- `mcp.py`: stdio JSON-RPC tools, bounded observation/artifact reads, reference
  validation, operation keys and an interface-level lead-only selection policy.
- `config.py`: pure construction of explicit hook/MCP configuration fragments.
- `entrypoint.py`: absolute-path entry for `python -I`, independent of solver cwd.
- `cli.py`: separate opt-in `EvidenceMASCLI`, merging hooks and configuring native
  lead/worker MCP access without changing the frozen baseline adapters.
- `audit.py`: read-only checks for explicitly required successful role/method
  calls. Missing steps remain incomplete; this never schedules calls or submits.
- `integration.py`: shared opt-in launch, source mounts, source-bound native proof
  checks and post-run audits used by the existing benchmark runners.

## Offline Usage

From the source root, the Python API is `harness.evidence_mas.SharedEvidenceWorkspace`.
The run ID permanently binds a store directory. Reference objects have the exact
shape `{"id": "...", "revision": 1}`. All offsets are Unicode character offsets
in the stored text, or canonical JSON for structured tool results.

```sh
python -m harness.evidence_mas.mcp --root /absolute/private/run-store --run-id run-001 --role worker
python -I /absolute/source/harness/evidence_mas/entrypoint.py hook --root /absolute/private/run-store --run-id run-001
```

The MCP server expects initialize followed by tools/list or tools/call messages
on stdin. It never executes registered SQL/scripts. Source snapshots may be task,
codebook, document or data_manifest; outcome records must bind an execution and
observation status. Caller-declared provenance is not proof the code was executed.

MCP proposals require an explicit `dependencies_complete` boolean. An independent
candidate uses an empty dependency list and true. The lower-level historical
store API retains its conservative false default; unknown is never auto-confirmed.
New Selection revisions invalidate dependent candidates transitively. Reuse of
an old outcome on revision requires an unchanged execution reference and an
applicability EvidenceLink. Schema checks cannot prove that reasoning correct.
Views compute current dependencies across issues, returning compact summaries by
default; `detail=true` includes full records. History is paginated. Observation
lists/search include bounded input summaries and output previews; search covers
both inputs and outputs. `obs_read(field='input')` reads original inputs. Reads
clamp valid ranges to available text and the 16000-character cap; evidence citation
spans remain strict, so clamping cannot silently change a cited range.

Use operation_id for safe replay of the same MCP mutation; a different request
with the same actor/role/key is rejected. Native event capture also reconciles duplicate
events with supplied call IDs. Reads are audited with argument/result snapshots;
access is not evidence of comprehension. Native servers are named `evidence`
and `evidence_worker`; both are excluded from recursive hook capture.

`workspace.trace` follows versioned provenance in both directions. Interpretations
can be revised or withdrawn, and evidence links retracted, without changing raw
observations. Claims without attached evidence are explicitly hypotheses.
`mode=observations` exposes only observation/artifact reads and tracing;
`mode=full` also exposes structured claims and decisions. Mode binds once per run.
These are ablations of one component, not two storage services.

Existing `scripts/<benchmark>/run.py` entrypoints accept `--evidence-mode
observations|full` with backend claude-code-subagents. Omitting the option retains
the original adapter and frozen prompt. The existing benchmark matrix accepts
`--evidence-modes observations full`; grading and report export keep the modes in
separate namespaces. `scripts/studies/run_validation20_evidence.py` composes those
workflows for the unchanged 60-question manifest, without a custom solver loop.

MCP schemas spell out version references, enums, array element types and bounds.
Input validation returns a tool error with the failing field path; semantic store
errors include recovery guidance. Invalid input never relaxes reference checks.
Workflow checks establish that recorded calls succeeded, not that agents understood
them. A model can still omit a required step; audit reports the omission rather
than inventing a successful call or automatically rerunning the agent.

## Integration Limits

`config.fragments` is pure configuration. `EvidenceMASCLI.run` provides the
explicit launch path, with `execute=False` by default. Native Claude 2.1.286
lead and background worker access were verified on the server using a strictly
fake provider in both modes; see `docs/studies/shared-evidence-native.md`.
Per-role stdio processes share the same workspace, rather than separate databases.
This verifies wiring, not reasoning quality or paid-provider behavior.

Both modes prepend the exact frozen Structured lead prompt and append the same
mode-specific tool guidance given to workers. The baseline prompt file is unchanged.
There are no mandatory workspace reads, traces or selections. Post-run benchmark
audits record worker lifecycle, cross-agent reads and method counts descriptively;
only workspace integrity/degraded capture affects the workspace availability status.
Availability is not verified delegation or reasoning. Explicit smoke-fixture
workflow requirements remain separate from benchmark acceptance criteria.
SendMessage phase-specific inputs are retained separately when the pinned CLI
prunes compatibility fields. True input/result conflicts still fail capture.
Diagnosis and offline repair evidence: `docs/studies/evidence-runtime-repair.md`.

Actor/role is a process configuration, not OS authentication. Same-UID shell
access is not isolated. No claim of tamper-proof storage or independently thinking
workers is made. Hash checks detect inconsistent stored payloads, not a malicious
process rewriting the whole store. Worker MCP processes receive distinct instance
IDs for write ownership; these are not native agent IDs. Native process reuse and
restart-to-agent binding remain unverified. Unknown identities remain unknown.

Only explicitly mounted, solver-visible inputs may be registered. Gold,
credentials and private evaluation logs must not be sent to these components.
Store directories are private; public reports must not include payloads.
Hook errors emit an empty permission-neutral response and a degraded receipt
where possible. They never retry external tools or grant permissions.

Tests: `tests/test_evidence_store.py`; run on the server with the existing
evaluation Python. Design: `docs/studies/subagents-evidence-design.md`.
Completed server verification: `docs/studies/evidence-mas-offline.md`.
