# Temperature 1.0 Three-Question Pilot

Historical completed pilot. The later user request retains thinking off/T=1.0
but removes the loop detector entirely. The driver and observation-only counters
below describe this frozen paid run, not the current runtime. See
[retirement](loop-guard-retirement-20261112.md).

User-authorized scope: exactly three Structured solvers, one each on
`legal-easy-11`, `astronomy-easy-5`, `wildfire-hard-10`. Frozen organization
prompt unchanged; thinking disabled, T=1.0, effort not applicable. Policy v4
records exact loops only; no warnings, agent stops, lead notices or host loop
termination. Shared solver limit 900 seconds, replay limit 180 seconds,
concurrency three, CPU8/thread4, zero retries, zero paid judges.

Independent CNY20 authorization, account-monitor stop-loss CNY18, leaving an
in-flight margin. This is not a provider-enforced hard cap. Account changes are
account-wide estimates, not attributable invoices; unknown billing is not zero.

Frozen-source driver: `scripts/studies/loop_guard_pilot.py --study temperature1`. Preparation
must reject historical T=0 policy under current source. Native fake-provider
proofs must verify T=1.0 on both main and worker requests before paid dispatch.

Source stage: `/home/zhoujunye/mas-stages/20261112-temperature1-pilot-01`.
Output: `/home/zhoujunye/mas/outputs/krama-temperature1-pilot-20261112-01`.
Free receipts: `/home/zhoujunye/mas-data/receipts/temperature1-20261112-01`.

This targeted, previously inspected set is not held-out validation. One attempt
per question cannot establish a general loop rate or causal improvement. Exact
loop counts do not detect changing-parameter cycles. Earlier T=0 pilot evidence
and frozen source remain unchanged; no historical score is relabeled.

## Measured Results

Completed all three slots on November 12, 05:35:16-05:36:37 UTC, no budget stop.
Each child exited zero; all native audits passed, replay exited zero and matched
the submitted answer, and all three owned solver containers were removed.
`verification.json` in the output records the post-run checks. Source hashes
still matched the authorization after completion. Server tests: 1047 passed;
six free native checks passed (both adapters, ordinary/persistent-loop/503).

| Task | CLI Seconds | Score | Model Requests | Longest Exact Pair Streak |
| --- | ---: | ---: | ---: | ---: |
| legal-easy-11 | 74.90 | 1 | 30 | 1 |
| astronomy-easy-5 | 36.83 | 0 | 14 | 1 |
| wildfire-hard-10 | 40.08 | 1 | 17 | 1 |

All 61 host-dispatched requests used thinking disabled, T=1 and effort absent.
No HTTP errors, timeout, loop warning/stop/notice or observer error was recorded.
No threshold crossing occurred, including for workers. This small run did not
reproduce the old long repetition; it does not establish general elimination.
Astronomy's zero is an incorrect answer, not a failed submission or timeout.

There were 60 complete streams and one client disconnect. On astronomy, the
lead explicitly called native TaskStop on its verification worker; the stream
closed between that tool's PreToolUse and successful PostToolUse. Native final
stats report one worker killed by the parent. This was not guard intervention;
the submitted pipeline remained replayable and consistent. That request's full
usage/charge is unknown, so full token accounting is unavailable. Known subtotal:
854001 input tokens (753920 cache hits), 16703 output tokens. Retained-message
token-weighted cache reuse: leader 90.01%, worker 84.41%; this is not billing coverage.

The immediate final balance and first follow-up at 05:37:25 UTC both showed an
account-wide CNY0.00 decrease. This is a balance observation, **not a claim of
zero cost**: settlement can lag and the cancelled request has partial usage.
Preserve the original receipts rather than rewriting the controller summary.
The final follow-up at 05:40:23 UTC observed an account-wide **CNY0.19** decrease,
well below the stop-loss. `billing-followup.json` records that later observation;
it is not an attributable final invoice and does not resolve the partial usage.
The controller process had exited and no Docker containers remained. The three
question fingerprints and frozen organization hash matched the earlier pilot.
