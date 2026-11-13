# Loop Guard Retirement

The November 12 retirement used thinking disabled, temperature 1.0. The later
fixed default is T=0.7; see [current inference policy](../reproducibility.md).
Neither retirement nor cleanup authorizes another paid solver, judge or retry.

Removed from active code: exact-loop state/counters, all loop modes, warnings,
worker action blocking, lead notices/Stop continuation, host receipt monitoring,
Krama loop-stop scoring paths, synthetic loop-provider scenarios, and the
experiment-specific pilot driver/tests. Native lifecycle/tool recording and
strict-Single delegation denial remain, as do ordinary deadlines and cleanup.

Runtime proofs bind native environment/tool settings and current adapter source
hashes, so proofs from the removed implementation cannot admit new runs.
Historical T=0 manifests and frozen organization prompts remain unchanged.
Read-only historical report readers/tests are retained to interpret the paid
guard evidence; they neither detect loops nor alter native execution.

Protected paid output/source pairs remain untouched:
- `krama-loop-pilot-20261111-01` / `20261111-loop-guard-pilot-01`.
- `krama-temperature1-pilot-20261112-01` / `20261112-temperature1-pilot-01`.

Free verification uses independent stage
`/home/zhoujunye/mas-stages/20261112-loop-retirement-01`, with receipts under
`/home/zhoujunye/mas-data/receipts/loop-retirement-20261112-01`.
This is not production deployment, a new experiment, or evidence that T=1.0
eliminates all repetition. No environments, images, credentials or other
projects' resources are changed.

## Verification

Server full suite: **997 passed**, no skips. Four free pinned-native checks
passed: normal admission plus first-request HTTP503 for Single and Subagents.
Main/worker request observations confirm thinking disabled, T=1.0, effort absent.
The 503 checks each made one synthetic request with zero retries. Native events
contain no loop-detection fields/state/feedback; the former T=1 guard proofs are
rejected as stale. `tests.xml` and `verification.json` are in the receipt root.
All probe containers/sockets were removed; no paid provider calls were made.

## Historical Design And Evidence

The retired exact-match guard compared tool name, input and normalized result
per native actor. Five unchanged pairs warned; ten stopped the lead or only
the triggering worker. Calls lasting at least sixty seconds reset the streak.
Worker stops emitted an incomplete-work notice; a notice at native Stop could
add a continuation. These were harness interventions, not native scheduling.
The [paid pilot](loop-guard-pilot-20261111.md) owns its three targeted questions,
observe/warn/worker-stop arms, authorization and interpretation limits. Exact
implementation remains in its protected frozen source, not active launch code.

Development checks are historical, not current admission proofs:

| Version | Free Verification | Receipt Root Under `mas-data/receipts/` |
| --- | --- | --- |
| v1 | 1,008 tests plus two separately rerun pinned-metric checks; eight native scenarios | `tool-loop-guard-20261111-04/` |
| v2 | 1,029 tests; twelve native scenarios, including worker-local stop and large-output/failure hooks | `tool-loop-v2-20261111/final/` |
| v3 | 1,043 tests; eighteen native checks, including actor reuse and first-request HTTP503 | `tool-loop-v3-20261111/final/` |

Read-only v1 replay hit the ten-pair rule in 19 of the sixty recorded Random20
`-02` attempts, including scoring submissions. V2 replay of Random20 `-01`/`-02`
recorded respectively 6/7 lead stops and 6/12 worker-only stops. These are
counterfactual detector hits, not failed tasks or evidence of model recovery.
Replay receipts remain at `tool-loop-guard-20261111-03/replay.json` and
`tool-loop-v2-20261111/final/replay.json`. Raw scores, paid sources and incurred
accounting are unchanged. The former standalone development narrative is
consolidated here; it is not a recipe to restore the retired guard.
