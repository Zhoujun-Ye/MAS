# Benchmark Timeout Policy

This policy applies to future solver runs. It does not change an existing run's
frozen plan, extend an active process, or authorize replacement attempts.

| Benchmark | Default solver timeout | Basis |
| --- | --- | --- |
| DataClawBench | 1200 seconds (20 minutes) | Pinned upstream task configuration |
| HybridDeepResearch | 1800 seconds (30 minutes) | Provisional engineering choice |
| KramaBench | 3600 seconds (60 minutes) | Provisional engineering choice |
| FDABench (local-only, opt-in) | 1800 seconds (30 minutes) | Provisional engineering choice |

The DataClawBench read-only source audit found the 1200-second task timeout for
all 492 released tasks. Relevant pinned-source locations are
`dataclaw/build_tasks.py:187` and `dataclaw/eval/run_batch.py:429,473,487`, at revision
`32e138750ceba41b47290211403ad1781d5e1971`. This is the source for the future
DataClaw default, not a claim that the external CLI reproduces every upstream
timeout or execution behavior.

No official whole-solver timeout was identified for HybridDeepResearch,
KramaBench or FDABench in the audited sources. Their defaults are explicitly engineering
choices, not benchmark requirements. Database query, replay and paid-judge
timeouts are separate settings and are not changed by this policy.

## Enforcement And Evidence

`benchmarks/policy.py` owns the default mapping and provenance. DataClaw
and HDR resolve their default after the benchmark is known; Krama defaults to
3600 seconds. An explicit positive `--timeout` remains supported and is recorded
in the run plan. Within a benchmark, both active Claude CLI conditions use the same timeout.

The matrix launcher passes the benchmark timeout explicitly and records
`timeout_seconds_by_benchmark` and `timeout_policy_by_benchmark` in its
authorization metadata. Its subprocess watchdog allows 4200 seconds, the
largest solver default plus 600 seconds for launch, evaluation and cleanup;
the solver itself still receives the benchmark-specific limit.

## Existing Frozen Batch

The former 900-second `dual-matrix-02` batch was stopped and its results deleted
at the user's request. It is not evidence for the new timeout policy. Adopting
this policy does not authorize a paid rerun; future runs need fresh authorization.
