# Exact tool-loop protection

Historical record only. The user retired the detector and its launch/probe
options on November 12. The implementation remains only in protected frozen
paid sources, not active code. See [retirement](loop-guard-retirement-20261112.md).

## Scope

The user requested loop detection after observing hundreds or thousands of
identical native tool calls. This change applies the same cooperative guard to
Single, Native and Structured, including workers. Frozen organization prompts,
model policy, tool surface, task selection and retry count are unchanged.
The subsequent user request separately authorizes the nine-solver prospective
pilot in [its frozen design](loop-guard-pilot-20261111.md); there is no standing
authorization for additional experiments or judges.

Policy v3 supersedes v2 and the development-only v1 global-stop policy. Five consecutive
equal tool-name/input/normalized-result pairs for one agent produce one neutral
additionalContext warning. Ten stop the lead/Single solver, but only the
triggering worker if its agent_id is present. Worker-local receipts are never
watched by the host termination monitor. Errors are compared separately from normal
results. State uses per-session/per-agent hashes, bounded call-ID deduplication,
locked updates and atomic receipts. Parallel/abandoned calls cannot inflate the
streak or permanently disable later detection. Missing observations are not
invented. Assistant prose alone does not reset a repeated action/result streak.

Calls with native duration_ms at least 60,000 reset the streak. Only the Bash
result envelope's persistedOutputPath/backgroundTaskId fields are normalized;
tool inputs, stdout/stderr, nested user JSON and output size remain significant.
The warning discloses no threshold and does not suggest giving up. Agent contexts
and scheduling remain native; there is no replacement worker or automatic retry.

A free pinned-CLI probe with host termination monitoring disabled established
that continue=false inside a worker ends that worker while the lead continues.
Native statistics/notification call this completed; that is not substantive
completion. A deduplicated lead additionalContext notice therefore identifies
the stopped worker and says its work may be incomplete, not verified. The probe
is retained at
`/home/zhoujunye/mas-data/receipts/tool-loop-v2-20261111/native-stop-semantics/`.

The host still independently terminates lead loops and guard failures, then the
benchmark launcher stops/removes the owned container. Native success cannot
override these solver-scoped failures. Worker loop receipts alone never zero a
lead submission. Krama lead-loop/timeout artifacts remain diagnostic with zero
primary score and no paid judge. A loop_guard_error instead receives score=None
as a harness failure and excludes its matched task from every condition's primary scoring, with all costs and
artifact diagnostics retained. Other benchmark stopped solvers export no
successful prediction; their guard-error rows are likewise excluded in reports.

Reports retain raw all-attempt metrics plus explicit primary denominators;
they count warnings/stops separately for lead and worker in each condition.
The paired sensitivity excludes any task with a recorded warning/stop/guard
failure from all conditions, rather than dropping only its failing arm. Missing
guard observations make this sensitivity unavailable, not silently clean.
Existing 5xx/recovery policy is unchanged. Historical evidence is never rewritten.

V3 additionally records policy activation at SessionStart, so first-request
failures with no tool calls have measured zero intervention counts. Primary
scores now remove a guard-error task from every condition, not only its failed
arm. Worker action fingerprints, not worker identities, are blocked: native
SendMessage can reuse the same worker with a different action. New stop episodes
receive separate notices. If a notice is emitted from lead Stop, additionalContext
may add a continuation. The documented native default caps eight consecutive
Stop continuations and resets after a tool call; it is not a global eight-notice
cap. This MAS-only continuation is part of the guard intervention, not untouched
native scheduling. Stop notice emissions are counted separately from proven
model incorporation.

V3's final server suite passed **1,043 tests with no skips**. Eighteen free
native checks passed: mode-bound baseline proofs for enforce/observe/warn/
worker-stop, three persistent-loop intervention pairs, same-worker SendMessage
reuse, and first-request HTTP503. The latter has measured zero intervention
counts from SessionStart. Final receipts are under
`/home/zhoujunye/mas-data/receipts/tool-loop-v3-20261111/final/`; the paid pilot
uses the frozen source `20261111-loop-guard-pilot-01`, not the production tree.

This is not an adversarial sandbox, a semantic stuckness classifier, a retry
policy or a worker scheduler. Identical fast legitimate polling may trigger it;
alternating/near-duplicate calls, changing observations and text-only loops are
outside its exact-match scope. See [retirement policy](../cli-adapters.md#retired-tool-loop-guard).

## Server Verification

Development uses independent source stages only; `/home/zhoujunye/mas`, frozen
paid sources and paid outputs are not deployed over or modified. No dependency,
image, provider setting or other project's resources are changed. The pinned
Claude Code 2.1.286 runs through the real Unix credential bridge with a fake
host provider, synthetic credentials and network=none solver containers.

V2 source stage: `/home/zhoujunye/mas-stages/20261111-tool-loop-v2-03`.
V2 receipts: `/home/zhoujunye/mas-data/receipts/tool-loop-v2-20261111/final/`.
The runtime proof digest includes the policy and hook/CLI implementation hashes;
old admission proofs and synthetic loop-injection proofs cannot admit new runs.

Verification scenarios, each for strict Single and native Subagents:

| Scenario | Required observation |
| --- | --- |
| Persistent exact repetition | Lead stops; worker stops locally, lead receives incomplete-work notice, preserves its submission and executes another tool |
| Large Bash output | Random persisted-output paths do not prevent detection; real output changes remain significant |
| Native tool failure | PostToolUseFailure delivers warning context and enforces lead/worker stop scope |
| Recovery after warning | Changed action proceeds and writes the expected marker |
| Same action, changing output | Twelve calls produce no loop warning/stop |
| Normal baseline proof | Original native permission, delegation, tool-surface and inference checks pass |

Unit/process coverage also checks changed arguments/results/errors, actor
separation, JSON key ordering, duplicate/parallel hooks, abandoned pre-hooks,
concurrent workers, corrupt state, native-success precedence, relative observer
paths, proof invalidation, retained diagnostic submissions and judge exclusion.
V1's server suite passed **1,008 tests with two skips** (`tests.xml` under
`/home/zhoujunye/mas-data/receipts/tool-loop-guard-20261111-04/`);
the two pinned-metric integration checks were then explicitly rerun with
`KRAMABENCH_UPSTREAM=/home/zhoujunye/mas-data/kramabench/upstream` and both passed
(`pinned-metrics.xml`). Thus all 1,010 collected checks have passing evidence.
V1's eight native scenarios passed. V2 requires the twelve scenarios above plus
the extended unit/report tests; its final receipts are separate. Each native pair runs
at concurrency two with the shared CPU8/thread4 container defaults.
All verification is free; none establishes real-model recovery or score gains.

V2's twelve native scenarios passed, including ten real native failure hooks
per tool-error probe and ten persisted-output events per large-output probe.
In each persistent worker probe, the lead received the incomplete-work notice,
executed another tool and retained its existing submission. All probe containers
were removed; no host/provider credential entered a container.

The final v2 server suite passed **1,029 tests with no skips** using the installed
pinned upstream metric sources. Receipt: `final/tests-latest.xml`. The earlier
v2 full pass of 1,028 tests is retained as `final/tests.xml`; the additional test
covers paired sensitivity when a known guard-error attempt lacks hook logs.

## Recorded-Trajectory Check

V1 read-only replay of the 60 existing `krama-random20-20261111-02` hook streams
hit the ten-pair rule in 19 attempts. Across those recorded streams, the longest
unchanged action/result streaks ranged from 22 to 2,203. This includes runs with
retained valid/correct submissions, not just timeouts or missing submissions.
The replay receipt is
`/home/zhoujunye/mas-data/receipts/tool-loop-guard-20261111-03/replay.json`.

The user's subsequent two-batch v1 review found 31 potential solver stops,
including scoring submissions and slow polling, motivating this v2 repair.
These are counterfactual detector hits, not newly failed tasks or evidence
that all repeated calls were semantically useless. No warning was injected into
the historical run, no model resumed, and no historical score was changed.
Actual warning recovery and cost/quality effects require a separately authorized
prospective run. In particular, do not compare a guarded future run against an
unguarded historical run as if their execution policies were identical.

V2 replay of both 60-attempt paid batches is retained separately in
`/home/zhoujunye/mas-data/receipts/tool-loop-v2-20261111/final/replay.json`:

| Recorded Batch | Lead/Solver Stops | Worker-Only Stops |
| --- | ---: | ---: |
| random20 -01 | 6 | 6 |
| random20 -02 | 7 | 12 |

The five previously scoring worker-triggered attempts no longer produce a
solver-scoped stop in this replay, including Structured legal-easy-11 and
wildfire-easy-2. They are not automatically assigned new scores. One scoring
Single attempt still triggers the intentionally retained lead-stop rule.
An isolated worker-only replay of legal-hard-16 Native in -01 hits the local
ten-pair stop at its fourteenth completed tool call; random persisted-output
paths no longer reset the observation fingerprint. This isolated check excludes
lead events on purpose: the whole-attempt replay reaches a lead stop earlier.
Its distinct receipt is `final/large-output-worker-replay.json`.
Observed long calls reset the streak in both batches. This is a detector/scope
audit only, not evidence that the historical agents would recover after feedback.
