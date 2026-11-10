# Three-Condition Engineering Smoke

User authorization: three benchmarks, two tasks each, Single / Structured / FULL,
one attempt per task and condition. Eighteen solver attempts, at most fifteen paid
grades (three HDR SQL grades are deterministic), no automatic retry or recovery.
Selection is the first two frozen Validation20 tasks per benchmark, not a new test set.

Frozen source: `/home/zhoujunye/mas-stages/20261109-threebench2-01`.
Batch: `/home/zhoujunye/mas/outputs/threebench2-20261109-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/threebench2-20261109-01`.
Protocol: `threebench2-20261109-protocol.txt`, unchanged prompts/model/limits,
eight solvers and two graders, CPU8/thread4. Admission estimate CNY25, factor 1.5,
reserve CNY5; this is not a provider-enforced expense cap.

## Preflight

- Server was idle with approximately 988 GiB available memory and no active containers.
- Existing server source passed 756 tests. Frozen stage passed 754 with two missing
  upstream-path skips; all 13 answer-metric tests then passed with the explicit
  existing `KRAMABENCH_UPSTREAM`, including both skipped integration checks.
- Fresh Single, Structured and FULL synthetic native proofs passed, no paid APIs.
- Real container/gateway/tunnel/Clash public fetch passed, including known-failure
  handling and helper operation outside the workspace; search used synthetic data.
- Initial tunnel had no local SSH master but a live remote listener; real TLS
  readiness timed out. Terminated only the identified stale owned SSH session and
  restarted the existing local launch agent. Real-link probe then passed.

## Network Interruption

After paid launch, a subsequent SSH connection failed with `Campus VPN source
address unavailable; reconnect EasyConnect`. Local tunnel master was again absent.
The user was asked to reconnect VPN. The original driver connection is retained;
no continuation, retry or replacement attempt was launched. After the user
reconnected, the original controller was still running, with sixteen completions.
Its final summary contains eighteen `cli_exited` solver records, all native audits
passing. No solver timed out. The obsolete local SSH connection was closed only
after the remote controller had finished and its final summary was present.

A local inspection during the outage also observed the server route on Clash's
TUN interface instead of the campus-VPN interface; reconnecting restored the
campus route. The initial SSH error alone did not prove EasyConnect was logged out.

## Separate Repair

The remote heartbeat watchdog repair was validated outside the frozen paid stage
in historical stage `20261109-tunnel-watchdog-01`. All 758 server tests passed
with the upstream path configured. When the old tunnel was again unavailable after
VPN reconnection, only its identified stale owned SSH session was terminated and
the repaired launch agent installed. The real-container public-fetch probe passed
again (`watchdog-web/`), and the master remained alive beyond the watchdog deadline.
A separate real SSH session exited normally when further heartbeats were withheld.

## SQL Grading Repair

The operator launched the batch with the project's `.venv` rather than the
documented existing evaluation Python. The three HDR SQL scorers failed because
`sqlglot` was missing. All three were regraded concurrently using the existing
`mas-data/environments/evaluation/bin/python`, with zero solver or judge calls.
Original reports/journal failures remain unchanged. `sql-regrade/` binds the new
grading receipts, and `effective-report.json` / `effective-report/` expose the
derived scores. No packages or environments were installed or modified.

New matrix admission checks the selected HDR SQL evaluator's `--help` with the
current Python, before credentials or paid dispatch. The actual wrong environment
was rejected and the existing evaluation environment passed. Combined repair
stage `20261109-infra-repair-02` passed 762 server tests in 35.28 seconds. Repaired
source was synced narrowly to the active project; the frozen paid stage was not edited.
Those free repair stages were subsequently removed under the retention policy;
their names are historical provenance, not current launch paths. Current source
and proof locations are documented in [active infra](evidence-infra.md).

## Results And Limits

| Benchmark | Single Score / Mean Min | Structured Score / Mean Min | FULL Score / Mean Min |
| --- | ---: | ---: | ---: |
| DataClaw | 1.0000 / 3.17 | 1.0000 / 3.97 | 0.7500 / 8.95 |
| HDR | 0.0000 / 20.12 | 0.0000 / 16.63 | 0.0000 / 17.60 |
| Krama | 0.9538 / 1.09 | 0.9538 / 1.64 | 0.9538 / 3.17 |

Nine model judges were called, below the authorized ceiling; Krama grades here
were deterministic. Shared-account balance fell CNY23.62 over the batch interval,
not an attributable invoice. One FULL HDR stream ended `client_disconnected` with
partial usage, so complete per-condition cost is unknown, not zero. No upstream
model HTTP errors were observed. Original summary remains `interrupted=true` due
to the three original SQL grading failures, not solver timeouts.

| Condition | Model Requests | Recorded Output Tokens | Token-Weighted Input Cache Hit |
| --- | ---: | ---: | ---: |
| Single | 222 | 413,992 | 98.34% |
| Structured | 265 | 567,271 | 95.61% |
| FULL | 473 | 909,719 | 96.98% |

Native retained-message accounting is not an exhaustive billing ledger. FULL used
1.78 times the model requests and 1.60 times the recorded output of Structured;
cached input was also longer. High cache reuse does not eliminate output/reasoning
or repeated-turn costs. No exact-Bash-call explosion or FULL sleep command was
observed (one exact repeat in FULL DataClaw); this does not rule out semantically
duplicated computation. FULL decision/read interactions and longer trajectories
remain costs, not automatically infrastructure defects or proven necessary work.

All eighteen resource captures showed no CPU quota throttling or observed OOM;
average usage stayed between 0.060 and 0.530 cores. Model-inflight interval unions
covered 86.0%-98.5% of HDR solver wall time. These intervals include provider
generation/streaming and overlap tools, not pure transport latency. Additional CPU
does not address this measured dominant component.

Fourteen fetches timed out and two were rejected as unsupported content types.
VPN disruption affected this batch; do not attribute all fetch failures to one
cause or interpret scores as a clean networking-controlled comparison. No automatic
retry or fallback was added. All owned containers were removed. Current transport
passes real probes, but there is no claim of maximum speed, zero token waste,
benchmark-wide efficacy or independence from the Mac/VPN/Clash availability.
