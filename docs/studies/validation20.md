# Fixed Validation Set

Exactly 20 frozen tasks per benchmark in `validation20-v1-manifest.json`.
Its filename versions the task set, not the prompt. Preserve every task ID/hash;
never replace failures or sample based on results. This is a repeatedly used
development set, not an independent held-out final test.

Current settings: `validation20-final-protocol.json`. Current lead prompt lives
only in `scripts/common/runtime.py`. Both conditions use high effort, native
output defaults, identical task limits, solver concurrency 6 and judge
concurrency 2. One attempt per task per condition, zero retries.

Use `scripts/studies/run_validation20_final.sh` only with fresh explicit run
authorization. It does not automatically resume or replace attempts.
Current scores include the separately labeled artifact-only HDR regrades and
the user's timeout-zero reporting policy. See [current results](../current-results.md).
