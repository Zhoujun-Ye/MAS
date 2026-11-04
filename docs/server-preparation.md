# Server Benchmark Preparation

## Credential Incident Cleanup

On 2026-11-04 the user authorized deletion of recent smoke runs, their interrupted
attempts and grading artifacts, plus `/tmp/cost-insight-zj`. Twelve named smoke
directories under the external data receipts root and that temporary directory
were deleted. Historical full-benchmark runs, datasets, dependencies and `.env`
were retained. Obsolete smoke result summaries were removed from this document.

The user confirmed revoking the old key and authorized copying the replacement
local `.env` to the server over SSH; both files remain mode 0600. After this,
the user stopped the old batch and authorized deleting historical results too.
Paid runs are paused: the current request is engineering and cleanup only.
Real provider keys must not enter solver containers.
The gateway uses per-run revocable tokens, fixed upstream routes, server-side
web request limits, no redirects and no retries. Provider errors are forwarded
with credential redaction and safe protocol headers. Tokens visible in agent logs are not provider keys,
but can authorize requests while their run gateway remains alive.

Current engineering stage: `/home/zhoujunye/MAS-information-stages/20261104-engineering`.
Old results and the interrupted `dual-matrix-01/02` batches have been removed;
there is no retained paid benchmark result for the current configuration.
Datasets, environments, source-only snapshots and offline proofs remain.

Offline containment receipt: `receipts/credential-isolation-offline-05/proof.json`.
Both Claude and Codex Docker configurations passed model/search gateway transport,
environment and `/proc/1/environ` canary checks, Docker metadata checks, host `.env`
inaccessibility, and container/socket cleanup. The provider was mocked on the host,
containers had `--network none`, and paid calls were zero. This is not native CLI
or real-provider end-to-end verification. Long Unix socket paths now fall back to
a private short directory. Gateway sockets are mode 0600, and arbitrary container
environment overrides or inherited host credential variables are rejected.
KramaBench now uses the same host gateway with web calls disabled. Offline lifecycle
tests cover normal completion, container startup failure, solver failure and cleanup
failure; all close the gateway and redact host credentials from error reports.
Old stage directories are historical source, not approved experiment entry points.

## Locations

Server: `zhoujunye@10.123.4.30`.

```text
/home/zhoujunye/MAS-information-data/
  kramabench/upstream/
  dataclawbench/upstream/
  hybriddeepresearch/upstream/
  hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl
  hybriddeepresearch/data/<db>/<db>_template.sqlite
  hybriddeepresearch/data/<db>/<db>_kb.jsonl
  environments/evaluation/
  receipts/
```

KramaBench was moved intact; its former production path is a compatibility
symlink for historical commands. There is no second data copy. Source used for
preparation and smoke is `/home/zhoujunye/MAS-information-stages/20261103-preparation`.
It is a scoped source stage, not a destructive production-tree deployment.
No `/home/zhoujunye/agent-team` resources were modified.

## Pins And Dependencies

- DataClaw source: `32e138750ceba41b47290211403ad1781d5e1971`.
  All 492 tasks parse, with 19 default input files and 9 cleaned-control files.
  Nine Git LFS objects were hydrated against their SHA-256 and size; no LFS
  pointer enters a solver mount. Hydrated files may appear modified to Git on a
  host without Git LFS; `receipts/data-hydration.json` verifies actual objects.
- HDR source: `3523f1da83a0470cdea742ea8b7426e7af6ca89b`.
  Encrypted Hugging Face release pin: `31304784b7aec82f22d59772a8afeb78567fd8b3`.
  LiveSQLBench DB/KB pin: `0664a2f28555faa0dd2947c8c23288df79bcc06b`.
  All 380 tasks parse; all 18 required SQLite databases pass integrity/readability.
- Dedicated evaluation Python uses upstream exact versions: numpy 2.5.2,
  pandas 3.0.5, scipy 1.18.1, sqlglot 30.17.0, openai 3.3.1. Installation used
  Tsinghua PyPI. `receipts/evaluation-requirements.lock` records all dependencies;
  `uv pip check` passes. The old project environment was not modified.
- Solver image: `mas-information/research-benchmarks:20261103-v1`, derived from
  the existing KramaBench image, adding only curl/libcurl via Tsinghua Debian.
  Image ID: `sha256:f940900759fee9d7f9fcdd819f5fc7062d4b1e11b192355b503ce33511bfa14b`.
  Claude remains pinned at 2.1.225. Native processes run as the host user,
  not as the Dockerfile's build user.

HDR questions, gold SQL, answers and evaluation logs remain private on the server.
Do not copy or publish decrypted evaluation inputs in the source repository.

## Offline Verification

- 193 tests pass in the dedicated environment, including both benchmark workflows
  with fake boundaries, input integrity, request caps and key-free process arguments.
- Four network-disabled native probes passed: both benchmarks, both modes.
  Real data mounts/CSV reads/SQLite helper checks are included; provider responses
  are loopback fixtures with dummy credentials, not quality evidence.
- Two additional native budget probes passed, including a costly simulated child
  call. CLI output reports `error_max_budget_usd` rather than successful completion.
  Native cost uses Claude fallback prices, not DeepSeek invoice prices, and a
  threshold is checked after calls; it is not a hard provider-side CNY cap.
- Official HDR SQL evaluator reference self-check: 58/58 matched against actual
  databases. This checks evaluator/data compatibility, not solver accuracy.

Receipts: `pytest-provisioning.xml`, `native-offline-03/summary.json`,
`data-verification-01/verification.json`, and `runtime-environment.json`, all under
the external data directory's `receipts/`.

## Web Configuration

The user-supplied Tavily key is in the existing server `.env` (mode 0600), never
mounted or committed. One basic Tavily connectivity search returned three results
and reported one credit. The account was on the free Researcher plan; immediate
account counters lagged the response. No later Tavily searches are authorized here.

The user subsequently selected **DeepSeek Search/Fetch**. Use `--web-search deepseek`;
it reuses the existing DeepSeek authentication, not the Tavily key. The official
endpoints are `/v1/tools/search` and `/v1/tools/fetch`. A direct search in the solver
image returned five results, with no model call and no retry. Immediate balance
delta was CNY 0.00; this is not evidence of free service or a zero-cost invoice.
Official successful nonempty Search/Fetch requests cost USD 0.00075 each.
[Official API and billing](https://api-docs.deepseek.com/guides/search/).

Search queries are bounded to the official 128-character limit. The shared
`--max-web-requests` ledger reserves before each paid helper request across agents;
errors are retained and not automatically retried. Search/fetch requests use curl
with credentials on stdin, because urllib TLS handshakes to Tavily timed out on
this server. No secrets appear in argv or receipts. This is not an adversarial
shell sandbox: native agents still have shell/network capabilities.
