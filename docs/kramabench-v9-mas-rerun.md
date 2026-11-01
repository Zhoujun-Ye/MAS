# V9 Same-Task MAS Rerun

2026-11-01. User authorized one further MAS attempt on `archeology-hard-1`.
No Single rerun, model retry, paid judge, install or image build.
The runner gained `--mode mas` to select only the authorized paid arm; its
existing matched-container preflight still prepares and removes both containers.

Evidence: `outputs/kramabench-paid-v9-mas-20261101-01` on the server.
Current source digest: `d83223621b7258d7`; current v9 capability catalog.
Server scripted regression before launch: 207 passed in 2.77 seconds.
Same model, thinking, request/tool/time ceilings and pinned image as the v7 rerun:
deepseek-flash, high effort, 16384 output tokens, retries 0; 64 shared requests,
120 domain actions, 1800 execution seconds, four parallel children maximum.

| Measure | Previous v7 MAS | Current v9 MAS |
|---|---:|---:|
| Submitted answer | 8477.8648 | 8347.1887 |
| Pinned numeric score | 0 | 0 |
| Model calls | 31 | 41 |
| Leader calls | 15 | 11 |
| Domain actions | 34 | 52 |
| Prompt tokens | 338764 | 507948 |
| Completion tokens, including reasoning | 29233 | 49506 |
| Token-weighted prompt-cache reuse | 80.67% | 78.72% |
| Maximum prompt tokens | 26121 | 27712 |
| Runtime seconds | 170.90 | 260.36 |
| Estimated USD, frozen runner rates | 0.028182240 | 0.047114616 |

## Observed Delegation

The leader selected `pipeline_analyst` (12 calls), then `reproduction_checker`
(10) and read-only `result_reviewer` (8). The latter two delegation intervals
overlapped. No child resume occurred. The production worker owned saved runnable
pipeline/results, unlike the previous review-heavy allocation. Root calls fell,
but aggregate calls rose; production delegation did not reduce total expense here.

The leader had already inspected sources and specified endpoint averaging as
PRIMARY, interval averaging as SECONDARY in the production brief. Both workers
returned both values; the reproducer did not receive the candidate numeric answer
or permission to read the candidate pipeline. This supports independent arithmetic,
not independent selection of the estimand. The reproducer also challenged the
brief's claim that Malta coordinates were blank, illustrating that a supplied
premise was not automatically treated as verified by the child.

The final submitted answer selected the endpoint mean, the same value as the
previous Single attempt. Interval mean 8477.8648 remained in the saved pipeline
as an alternative. Neither matches pinned gold 8577.5298. The existing reference
rounding/tie-policy/replay discrepancy in `kramabench-pilot-analysis.md` remains
unresolved; no gold or historical score was changed.

## Accounting And Limits

| Role | First / max prompt tokens | Weighted cache reuse | Calls |
|---|---:|---:|---:|
| Leader | 3236 / 26272 | 90.43% | 11 |
| Pipeline analyst | 3183 / 17942 | 81.46% | 12 |
| Reproduction checker | 2881 / 14689 | 76.95% | 10 |
| Result reviewer | 2298 / 27712 | 61.30% | 8 |

The run completed with valid submission, no failed provider calls, no trace-integrity
errors and `infra_affected=false`. Children reached their local call ceilings;
the reviewer also reached its local tool ceiling. These are limits, not independent
verification of completed checks. All report reservations were released. Both owned
containers were removed successfully and `docker ps` was empty afterward.

Costs use the runner's frozen price table, not a newly verified tariff or attributable
invoice. The final submitted pipeline was not independently re-executed after the
attempt and the upstream paid pipeline evaluator was not invoked. This reused,
inspected task and changed prompt/catalog do not provide held-out evidence or a
causal estimate of the effect of any individual revision.
