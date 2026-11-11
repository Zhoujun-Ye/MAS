# FDABench Single/Structured Smoke4

## Authorized Scope

Four fixed choice questions, each solved once by strict Single and frozen
Structured: eight solver attempts, no retries, no paid judges. Choice scoring is
offline. This is a small engineering validation, not held-out efficacy evidence
or a causal before/after speed comparison.

FULL, OBS and their prompt-only ablations are retired. Their paid historical
evidence stays protected; no retired decision/sharing mechanism is transferred
to either baseline. Both retain their exact existing prompts.

## Frozen Selection

The existing seeded public-strata round-robin policy (seed 42) selected from
282 publicly scoreable local choices whose database was already present. This
readiness filter is explicit for this opt-in smoke only: it does not shrink the
canonical eligible pool or bypass missing-asset preflight. No answers or scores
were used for selection. Preserve these IDs even if a solver fails.

| Task | Kind | Task SHA-256 |
| --- | --- | --- |
| FDA0699 | single_choice | 5085401aed84b6ef16b422cd5e608241bc41cf1356665f901c9f60076eba320e |
| FDA1543 | multiple_choice | eb224f3e7574c34687b61ae1f8888d60c5aea14f83cee4f103fc6883fd0a7b1d |
| FDA0867 | single_choice | c484c983b49950e47df58844bb9b4794e54263e4db042d0f93909247e63aebae |
| FDA1948 | multiple_choice | 09849a66ae0cd4d2fa7d2e9d705cc11572e6aea4e3d6e7c7206d42fcd96fc673 |

All four permit SQL, local corpus and web tools. Solver mounts contain only the
selected SQLite DB, raw corpus and local search index, never scoring references.
See [adaptation limitations](../fdabench.md).

## Runtime And Admission

Claude Code 2.1.286, existing DeepSeek Flash model, max effort, 1800-second limit
per attempt, 20 successful web calls, 2 CPUs and one numerical thread per solver.
Concurrency is four solver containers total with isolated outputs; offline grades
use a separate pool of two. Solvers have no network; real keys remain host-side.
Web GET/DNS use the existing private Mac/Clash tunnel, not direct fallback.

Admission requires fresh fake-provider Single/delegation proofs, real native
runner SQL/corpus checks, free real web probes and server regression tests.
Freeze source, image/binary/proof hashes, exact task manifest and settings before
paid dispatch. The CNY 25 planning estimate with 1.5 safety factor and CNY 5 balance
reserve is an admission estimate, not a provider-enforced monetary cap.

Receipts: `/home/zhoujunye/mas-data/receipts/fdabench-single-structured-smoke4-20261110-01/`.
The completed paid artifacts and subsequent free repairs are separated below.

## Completed Diagnostic

Output: `/home/zhoujunye/mas/outputs/fdabench-single-structured-smoke4-20261110-01`.
Frozen source: `/home/zhoujunye/mas-stages/20261110-fdabench-single-structured-smoke4-01`.
All eight solvers and offline grades finished; the controller exited zero.
Native condition audits passed 8/8, with no retries and zero paid judges.

| Condition | Exact Choice Score | Mean CLI Minutes | Model Requests | Input Cache Hit |
| --- | ---: | ---: | ---: | ---: |
| Single | 4/4 | 4.19 | 103 | 96.38% |
| Structured | 4/4 | 3.67 | 120 | 92.29% |

Important configuration error: this diagnostic used the generic 2-CPU/thread1
defaults instead of the previously adopted 8-CPU/thread4 profile. The user flagged
this after all eight attempts had dispatched. No container was hot-changed and no
paid attempt was repeated. Results are retained as an explicitly labeled 2-CPU
diagnostic, not proof of CPU8 performance or of the later repairs.

Shared-account interval decrease: CNY 4.29. It is not an attributable invoice.
The export's USD 0.118573/0.172413 per-condition values are legacy off-peak price
scenarios, not current-rate bills. No provider response failed in this diagnostic.

Model-request union occupied 90.16% of Single and 95.01% of Structured CLI windows;
individual runs used 0.09-0.39 CPU cores on average. Structured output was 206,408
tokens versus Single's 141,548; uncached inputs were 261,235 versus 133,353.
Native token accounting is observational, not process-authenticated billing.
High cached-input totals must not be presented as fully uncached spend. More CPU
does not directly shorten provider generation or remove model reasoning tokens.

## Shared Infra Repairs

- All four benchmarks now default to 8 CPUs/4 threads from one shared definition;
  child commands always pass both, and plans record them explicitly. Admission
  rejects total CPU reservations above host capacity. Old frozen runs are unchanged.
- The user authorized a new shared image with Poppler, fixing observed native
  PDF reads that previously failed repeatedly. Old-image retention was later
  superseded by the user's November 11 conditional image-retirement authorization;
  this batch's raw evidence and recorded image ID remain protected.
- SQLite errors retain their type/message but omit tracebacks. A deterministic
  fixture reduced stderr from 896 to 67 bytes; this is output-size evidence, not
  a measured paid token/time saving. Successful query output is unchanged.
- Frozen organization prompts, model, effort, scoring and web limits are unchanged.
  No context pruning, automatic response cache, semantic shortcut or retry was added.

Post-repair verification is free: server regressions, image rendering, native
Single/Structured proofs, real runner SQL/corpus/PDF reads and private-route web
probes. The existing paid authorization is exhausted; a paid CPU8 comparison or
claim of end-to-end post-repair improvement requires separate authorization.

Final server verification: 806 full-suite tests passed, followed by 20 focused
tests after the final probe assertion. Six fake-provider native runner checks
(DataClaw/HDR/FDABench times Single/Structured) passed with observed 8-CPU quotas,
four-thread environment/numerical-library assertions, SQL/corpus access and native
PDF Read for FDABench. Both Krama container preflights passed with CPU quota
`800000 100000`, four-thread capability checks and the new image. Two fresh native
gateway proofs and real private-route web probes passed. No post-repair paid
solver or judge was started.

Key receipts: `tests-release.xml`, `tests-final-focused.xml`, `paid-audit.json`,
`infra-token-audit.json`, `pdf-image-03/environment.json`, `cpu8-gateway-proof/`,
`cpu8-thread4-final-proof/`, `cpu8-krama-preflights/` and `cpu8-web-proof/`.
