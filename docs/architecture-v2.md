# Hierarchical MAS v2

Historical architecture, not the current target. This is a star dispatcher
without peer messaging. See `leader-led-team.md` for the audit/target contract.
Its benchmark adapters have been removed.

This is a new experimental setup, not a continuation of phase 0. The protocol
identifier is `hierarchical-full-task-v2`. Changed frozen prompts force a new
output directory. Existing traces, grades and preregistered thresholds remain
unchanged. Do not pool v1 and v2 results.

## Ownership

- `harness/team.py`: domain-neutral coordinator, dynamically created persistent
  workers, parallel dispatch, worker continuation, shared budget and logging.
  It imports no benchmark code. `Team.run(final_prompt)` returns an `Outcome`.
- `harness/relay.py`: common downward task envelope and upward relay forms.
- Benchmark adapters supply public task text, public constraints, domain tools,
  domain instructions and final-answer formatting. Reference answers, gold
  evidence and evaluator state must never enter those public inputs.
- BCP uses this runtime directly. Its adapter retains retrieval, C0/C5, answer
  extraction and scoring, not a second implementation of team orchestration.
- Tau2 still requires its official event-driven orchestrator and environment
  execution. Its front desk/operator adapter shares the downward policy and
  upward relays, but is not a multi-worker `Team` backend. Its operator now gets
  the complete user-visible dialogue so far in every condition. Hidden user
  simulator state and future utterances are never supplied.

## Information policy

Every assignment carries the complete original task, common constraints and
the assigned subtask. All workers have the same domain instructions. The
coordinator is prompted to give purpose, dependencies and acceptance criteria,
and to dispatch dependent tasks only after their prerequisites. This encourages
reasonable decomposition; it cannot guarantee that a model's decomposition is
correct. Record and inspect poor decomposition separately.

C1-C4 differ in upward communication only: free report, structured report,
report plus complete tool log, or report plus shared artifact index/readback.
C3 no longer receives privileged downward working notes. C4 remains a shared
storage intervention, including worker readback, not just a serialization change.
Local discoveries are not automatically broadcast. The coordinator can ask
follow-up questions and continue a worker whose append-only history is retained.
Dispatch results explicitly identify the worker so continuation is actionable.

The shared tool budget is unchanged. No per-worker allowance, reserved lead
budget or remaining-budget messages are introduced. Model settings remain the
same across roles/conditions. The optional low-effort overlay is not enabled.
For stateful tools, adapters must disable parallel dispatch or provide safe
transaction semantics; general-purpose tools are not necessarily thread-safe.

## What the experiment can establish

The question is whether task-relevant facts discovered locally fail to reach a
downstream decision despite complete public task information. Docid citation
is only a proxy. Semantic arrival needs supported facts and qualifiers, actual
received contexts, and an explicit unknown state when the judge cannot decide.
BCP has a semantic-arrival preparation/judge entry point; the general loss-type
judge is not a substitute for benchmark-specific factual ground truth.

Missing facts alone do not prove the cause of an incorrect answer. A causal
study still needs frozen decision-point replays with supported missing facts,
an unchanged-context repeat, and an appropriate control supplement. Keep
retrieval trajectories fixed, forbid additional tools, repeat to estimate
model noise, and grade independently. Do not claim causal recovery from C3's
success rate alone: its changed reports can change later assignments/retrieval.
C5 is also exploratory, since C1's adaptive assignments are replayed sequentially
under a different context. No causal replay experiment has been executed.

## Verification

Server scripted-model regression tests cover all four relays, identical public
task supply, worker continuation, shared budgets, append-only trace integrity,
BCP integration and Tau2's official tool handoff. The generic stock-tool fixture
uses no BCP code/data. Real-model decomposition quality, factual arrival,
causal effects and cost changes require separately authorized paid evaluation.
