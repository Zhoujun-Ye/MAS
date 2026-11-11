# Baseline Execution Infrastructure

Default conditions are Single and Structured. KramaBench also supports the
explicitly selected [minimal Native study](krama-random20-20261111.md) on the same
Subagents adapter; delegation is mandatory in both Subagents conditions.
FULL, OBS and their prompt-only
ablations were retired on 2026-11-10, including their runtime, hooks, tools and
launch choices. Their paid evidence and frozen sources remain under
[retention](../archive.md). The frozen Structured baseline is unchanged.

## Ownership And Isolation

- `harness/runtime_support/` owns containers, credential transport, SQL/web tools,
  corpus access and runtime-bound native proof validation.
- `scripts/common/` composes benchmark workflows and unchanged solver prompts.
- Native contexts, delegation and scheduling stay in the external CLI. Strict
  Single removes and denies delegation tools; Structured uses native subagents.
- No automatic semantic choice, submission, retry or custom worker scheduler.

Solvers run with network disabled. Real provider keys remain host-side; a private
Unix gateway exposes fixed native protocol destinations and records requests.
Run tokens do not authenticate same-UID process origin and are not OS isolation.
References, gold SQL, rubric answers and frozen search results are never mounted.

## Tools And Resources

SQL and corpus readers share the same implementations across supported conditions.
Web-enabled tasks use [web transport](web-infra.md): GET and DNS both use the
private Mac/Clash route, with no direct/provider-fetch or server-DNS fallback.
Model/search/judge APIs remain server-direct. FDABench choice scoring is offline;
report judges require separate paid authorization.

[Full-scale operation](fullscale-infra.md) owns durable claims, accounting,
resource telemetry, recovery and manifest rules. Full-scale means task coverage,
not the retired FULL condition. CPU quota and numerical thread limits are frozen
per run, and bounded concurrency counts total solver jobs across conditions.
The shared defaults are 8 CPUs and 4 numerical threads for every benchmark and
every supported condition. Plans and child commands record the values explicitly.

The shared image includes Poppler to eliminate the observed missing-renderer
failure in native PDF reads. SQLite helper failures return a compact typed error,
not a Python traceback. Successful SQL results, prompts, model requests and scoring
are unchanged; no automatic tool or model retry is introduced.

The current image uses SQLite 3.54.1, with baseline compile features and
UPDATE/DELETE LIMIT parser support verified. Identical read-only query replay is
separate from stochastic paid solver timing; it does not establish compatibility
with every possible query or accelerate all SQL. See the
[November 11 infra check](threebench-infra-20261111.md).

Containers use Docker's init process to forward shutdown signals and reap
children, avoiding the idle PID 1's fixed forced-kill delay. This does not change
native delegation or mark outstanding work complete. Resource records include
sampled core use and cgroup CPU/I/O/memory pressure, with unavailable counters
unknown. Stop hooks record outstanding background shells; a missing SessionEnd
remains an audit gap, not a passing lifecycle inferred from CLI exit.

`--require-module NAME` requires successful import. Explicit capability probes run
in network-disabled preflight containers, without provider keys, with source
digests and deadlines. They are not installers or proof of task solvability.

## Verification And Limits

Before paid dispatch, bind proofs to the exact image, native binary and effort.
Use synthetic provider responses to verify strict Single denials, real Structured
delegation, host credential isolation, submissions and mounted data/tool access.
Run real free web probes separately. Freeze source, task IDs/hashes, input hashes,
settings, attempt count and judge authorization before starting paid work.

Fake-provider tests establish mechanics, not model uptake or benchmark gains.
Keep failures, native traces, host accounting and exact submission hashes. Report
unknown usage as unknown; token-price estimates and shared balance deltas are not
per-request invoices. Paid historical studies remain descriptive evidence, not
authorization for further calls or active runtime contracts.
