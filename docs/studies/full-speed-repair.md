# FULL Speed Diagnosis And Offline Repair

Subsequent explicitly authorized paid validation is reported separately in
[infra-smoke4-speed-check.md](infra-smoke4-speed-check.md); the measurements below
remain the original offline validation, not retroactive paid-speed claims.

2026-11-07. No new paid solvers, judges or retries. Diagnosis uses the retained
eight-attempt `krama-infra-smoke4-20261107-01` batch. The paid source stage is
unchanged; repairs are separately staged in
`/home/zhoujunye/mas-stages/20261107-full-speed-repair`.
Offline receipts: `/home/zhoujunye/mas-data/receipts/full-speed-repair-20261107`.

## Actual Bottlenecks

The prior smoke report's narrow sleep check missed `sleep N; echo waited/done`.
There were seven such FULL lead commands. Observed hook intervals total:

| Task | Placeholder sleep seconds | Portion with no observed active worker |
| --- | ---: | ---: |
| archeology-easy-11 | 60.18 | 60.18 |
| astronomy-easy-1 | 140.75 | 26.64 |
| legal-hard-15 | 85.37 | 27.89 |
| wildfire-easy-9 | 0 | 0 |

These are sums across tasks, not additive to parallel batch wall time. Worker
completion during an already running sleep is different from sleeping after all
workers have already stopped. The conservative new guard catches the latter;
it does not interrupt a Bash process when a worker later finishes.

FULL made 178 model requests with 174,123 output tokens versus Structured's 111
requests and 112,653 output tokens. Request time includes network/provider time;
aggregate output throughput was similar (roughly 132-150 tokens per summed request
second across tasks). At least one model request was in flight for 68%-89% of FULL
task wall time. These intervals overlap worker execution and sleeps and must not
be added as disjoint stages. CPU quotas were not throttled and average use stayed
below one core. More CPU alone will not remove model decoding or blocking sleeps.

FULL astronomy also had a dict/scalar answer representation conflict. A candidate
change invalidated reads of unchanged alternatives, and the old error did not name
the unread candidate, so the lead paged through unrelated executions. This is an
avoidable review interaction, not a reason to remove consistency checks.

## Implemented Changes

- Recognize simple sleep-plus-literal-echo wrappers. Deny lead waits explicitly
  described as agent waits only with observed worker shutdown and no pending native
  Agent/Task launch. Preserve unknown/running-worker and computation/resource waits.
  No custom scheduler or automatic worker termination is introduced.
- Compact-delta-v2: 1800-character incremental budget; shorter previews; omit raw
  output already represented by a parsed result; deduplicate exact execution
  input/output/status per recipient. All original evidence remains accessible.
  No semantic filter drops candidates, no gold/task-ID logic is used.
- Candidate-local read tokens preserve complete access to unchanged candidates.
  Changed interpretations still invalidate that candidate's access and every
  selection remains bound to the global current snapshot. Partial/overlapping
  pages, other actors and worker reads cannot bypass the full-input/output gate.
- View/read responses expose completion and exact next-read arguments; errors
  identify the missing candidates and distinguish text pages from optional extra
  executions. Mixed answer shapes produce a warning without rewriting answers.
- FULL guidance separates requested answer shape from analysis reports and
  discourages agent-wait sleeps. No roster, mandatory replication, semantic judge,
  model/effort change or Structured prompt change was introduced.

## Offline Measurements

`scripts/probes/sharing_volume.py` replayed the identical recorded hook event order
into fresh temporary stores using the frozen paid implementation and repaired one.
It executes no recorded tool commands and makes no model calls. Baseline replay
reproduced the 250,183 characters in the actual emission receipts.

| Task | Original emitted characters | Repaired replay |
| --- | ---: | ---: |
| archeology-easy-11 | 30,661 | 19,632 |
| astronomy-easy-1 | 68,314 | 39,701 |
| legal-hard-15 | 126,827 | 64,558 |
| wildfire-easy-9 | 24,381 | 16,216 |
| Total | 250,183 | 140,107 |

This is a **44.0% reduction in emitted characters**, not measured token or runtime
savings. All 241 delivered observation references remained represented on this
trace replay. One completed-worker wait was identified for rejection (the 60-second
archeology wait). Model behavior after rejection and the remaining active-worker
waits cannot be predicted from replay.

Active server suite: 608 tests passed in 17.04 seconds after deployment.
Pinned native fake-provider FULL/OBS checks passed after updating the probe's
obsolete context-marker assertion. They verify bidirectional compact delivery,
decision selection, and actual native denial of the completed-worker wait without
executing it (14 synthetic requests per mode). Active-server proof validation
matches the tested configuration. The first probe run failed only its old marker assertion; its receipts
have their failure summary retained, not relabeled successful. The superseded
synthetic request/workspace copies were removed during cleanup. Real credentials were not supplied and
all owned containers were removed.

## Remaining Limits

This removes measured avoidable overhead but does not establish significant
end-to-end speedup. Long waits initiated while workers are active remain possible;
the prompt change needs real-model validation under separately authorized trials.
Provider/model generation dominates many tasks, and workload-dependent threading
cannot accelerate it. Independent worker premises, lower-effort studies, data-loader
reuse and larger batch concurrency remain separate decisions. No new paid test is
authorized by this source or resource profile.
