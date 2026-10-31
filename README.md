# CooperBench Agent Team: Collaboration Diagnosis

CooperBench is the sole benchmark selected for this study. Old benchmark
adapters, launchers, tests and screening documents have been removed.
Other projects' resources are never modified. Historical experiment outputs
were deleted at the user's request; new runs use fresh output directories.

## Study Contract

Fixed capability templates, assignments, domain permissions and scheduler;
independent append-only contexts; verbatim peer messages; shared task status.
Observe free collaboration before selecting Harness mechanisms for evolution.
Information loss, delay, misuse, coordination failures and overhead are distinct
but potentially co-occurring diagnoses. No efficacy or causality claim follows from setup.

The CooperBench adaptation uses worker_a + worker_b (both coder templates) + a communication-only leader.
Each worker sees only its own feature description and its own repository.
This is a leader-led adaptation, not the paper's original two-peer setting.
Gold solutions and hidden tests are evaluator-only.

Runtime fixes scheduling, transport, permissions and lifecycle. Information
Harness supplies a frozen sender policy for every substantive report/message.
Submitting freezes a version; receiving a message does not reopen it. Verified
completion requires an evaluator result for the exact submitted artifacts.
Only submit_assignment submits; a tool-free reply merely yields. Members have
independent budgets. Failed runs retain terminal code snapshots and remain in the
all-started denominator; passing diagnostic code tests cannot erase an agent failure.
Messages and tool output show unescaped raw text, not nested JSON.

## Entry Points

- scripts/cooperbench/prepare.py --fetch: pinned source and bundled dataset.
- scripts/cooperbench/offline.py --output NEW_DIR --scheduler controlled:
  real public descriptions with scripted agents, no Docker or model calls.
- scripts/cooperbench/offline.py --output NEW_DIR --scheduler async:
  the same control-flow check with independent concurrent agent turns.
- scripts/cooperbench/run.py: one explicitly authorized paid pair in two
  pre-provisioned isolated containers; no automatic provisioning or expansion.
- scripts/cooperbench/grade.py: separately authorized local Docker evaluation
  using the pinned upstream merger and feature tests, with no model judge.

Run tests on the server after CPU/process inspection and scoped source sync.
The exploratory default is async with autonomous communication under fixed
tool/time allowances, without cumulative-token, message or discussion-round caps.
All members, including the leader, start runnable. Workers are sanitized and
independently checked for future Git history before any model call. Native
baseline/gold gates and server regression tests must pass before paid execution.
No result is implied by successful setup or a model's completion report.

## Documentation

- [CooperBench setup and evaluation](docs/cooperbench.md)
- [Architecture](docs/leader-led-team.md)
- [Information boundaries](docs/information-harness.md)
- [Communication policy](docs/communication-policy.md)
- [Decision-time evidence and delay](docs/information-feedback.md)
- [Completion protocol](docs/completion-protocol.md)
- [Study validation gates](docs/experiment1.md)
- [Lite 100 execution contract](docs/lite100-20261030.md)
- [Lite 100 results](docs/lite100-results-20261030.md)
- [Failure audit](docs/lite100-error-analysis-20261030.md)

Paid authorization is run-specific. The completed lite100 study superseded the
earlier twenty-pair scope; its authorization does not extend to new paid runs
or retries. Original run evidence remains immutable on the server.
