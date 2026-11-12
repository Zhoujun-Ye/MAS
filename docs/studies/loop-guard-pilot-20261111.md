# Prospective loop-guard pilot

Historical completed pilot. Loop hooks, launch modes and the active pilot driver
were removed on November 12; the following design describes the preserved paid
source, not a current launch option. See [retirement](loop-guard-retirement-20261112.md).

## User Authorization

The user explicitly approved nine solver slots, a CNY50 budget, no retries and
no paid judges. Each solver has the same 900-second limit; three run in parallel
with CPU8/thread4. CNY50 is a planning/stop-loss limit, not a provider-enforced
hard cap. The controller checks the account balance and stops its own jobs at
CNY45 observed account spend, leaving margin for in-flight charges. Unrelated
account use can cause an early conservative stop. Missing balance/fatal-provider
evidence stops further dispatch; no replacement attempt is authorized.

## Frozen Design

All arms use the exact Structured lead prompt, pinned Claude Code 2.1.286,
DeepSeek thinking disabled, temperature zero and effective effort none.
The explicit tool surface and all non-guard runtime settings are identical.
Three fixed historical worker-loop questions are selected before new outcomes:
legal-easy-11, astronomy-easy-5, wildfire-hard-10. These cover a previously correct
lead submission, an incorrect submission and a missing submission. This is a
targeted diagnostic, not a randomly sampled independent quality test.

Each question receives one attempt under each intervention:

| Mode | Feedback | Hard Stop |
| --- | --- | --- |
| observe | None; record would-warn/would-stop only | None |
| warn | Generic warning at five unchanged pairs | None |
| worker-stop | Same warning | Worker only after ten unchanged pairs |

The study intentionally disables lead hard stopping in all three arms to
separate warning effects from the incremental worker-local stop effect. The
ordinary default remains enforce, with lead and worker stopping. A task wave
launches all three arms together; launch order rotates across the three waves.
The wave barrier keeps task-paired provider/time windows comparable. There is
one attempt per cell, not best-of-N. Failures are retained and never rerun.

## Execution And Evidence

In the frozen paid source, `scripts/studies/loop_guard_pilot.py` plans by default. --prepare freezes nine
independent existing Krama workflow plans and runs their free preflights.
--execute additionally requires --authorized-solvers 9 --budget-cny 50, matching
source/proof/plan hashes and sufficient live account balance. A durable exclusive
execution receipt rejects a second execution of the same pilot directory.
Provider credentials stay host-only behind the existing Unix gateway; solver
containers use network=none. No new dependency/image/proxy is provisioned.

Keep authorization, per-slot source/proof/input bindings, raw native evidence,
host ledgers, container/resource records, submissions, offline grades, balances,
progress and summary. A guard error removes its task from all arms' primary
scores; all incurred costs remain. An incomplete paired task is not silently
compared against different tasks. No semantic judge is dispatched.

## Interpretation

Report per-cell outcome, valid pipeline replay, score, wall time, model calls,
tokens/cache reuse, warning/stop roles and repeated-pair streaks. A changed
action/result after warning is observed behavior, not proof of incorporation.
SessionStart permits measured-zero guard counts for a first-request failure.
If lead Stop is the notification point, guard additionalContext can add a native
continuation (the documented default caps eight consecutive Stop continuations
and resets after a tool call, not an eight-notice total cap); that is part of
the intervention and can occur only in the worker-stop arm.

Only contemporaneous arms can inform this pilot comparison. Do not compare it
directly with random20 -01/-02 or promote three targeted questions into a claim
of general model-quality improvement. No additional paid run is authorized if
the pilot has no loops or produces an inconclusive result.

## Run Location

Output: `/home/zhoujunye/mas/outputs/krama-loop-pilot-20261111-01`.
Frozen source: `/home/zhoujunye/mas-stages/20261111-loop-guard-pilot-01`.
Execution began at `2026-11-12T04:48:21.669794+00:00` (November 11, 23:48 EST).
The live account admission observed CNY587.46 and required CNY50 headroom.
The detached controller PID is recorded in execution-start.json; authorization,
progress and final summary are in the output root. Do not modify that frozen
source or treat successful startup as completion. Local result documentation
is updated separately, never synced into the running source stage.
