# Fixed Validation Set

Exactly 20 frozen tasks per benchmark in `validation20-v1-manifest.json`.
Its filename versions the task set, not the prompt. Preserve every task ID/hash;
never replace failures or sample based on results. This is a repeatedly used
development set, not an independent held-out final test.

The frozen Single/Structured baseline profile is `validation20-final-protocol.json`;
it is not the current FULL resource profile. The frozen lead prompt lives
in `scripts/common/prompts/structured_subagents.py`. Both conditions use high effort, native
output defaults, identical task limits, solver concurrency 6 and judge
concurrency 2. One attempt per task per condition, zero retries.

Use the generic `scripts/studies/benchmark_matrix.py` with fresh explicit run
authorization and exact frozen settings. The older study-specific drivers and
results were removed. See [current results](../current-results.md) and
[active infra](evidence-infra.md) for the separately recorded CPU8 resource profile.
