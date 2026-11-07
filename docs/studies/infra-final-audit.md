# Infrastructure Boundary And Overhead Audit

2026-11-07. Offline engineering work only; no paid models, judges, search API,
retries or balance queries. HDR stays 1800 seconds; model, effort, task order,
prompts, scoring and FULL sharing/decision semantics are unchanged.

## Repairs

- Fetch failures now expose safe reason codes and original target HTTP status
  where known, separately from the gateway's wrapper HTTP502. Raw page bodies,
  URLs/queries and exception text are not copied into accounting/error receipts.
  Historical four failures still cannot be classified retroactively.
- Single-read body iteration checks the total deadline between reads; truncated
  Content-Length bodies fail rather than becoming successful incomplete evidence.
  Redirects, DNS, CONNECT and TLS remain bounded without direct fallback.
- Gateway shutdown tracks/closes active GET connections and response sockets,
  not only provider model streams. Cancelled or unknown work is not retried.
- Grading progress is now persisted as grading completes, while solvers continue.
  The previous executor overlap worked, but progress display waited for all solvers.

## Preparation Optimization

The host SHA256 inventory cache now also binds Krama's expected Git blob OID and
verified SHA256. Filename inventory, pinned revision/blob checks, symlink rejection,
two-second fresh-file rehash window and stat mutation checks are retained. A miss
verifies both hashes. Warm reads avoid a global writer lock; misses are serialized
and rechecked. This is a trusted-host optimization, not an adversarial boundary.

Matrix Krama jobs share the batch host-only `--asset-cache`, as DataClaw/HDR already
do. The hashing policy is frozen in each attempt plan and cannot change on execute.
No dataframes, model responses, answers or cross-task observations are cached.

Measured on all 1,742 Krama input files (666,850,039 bytes):

| Check | Full Hash | Warm Cache |
| --- | ---: | ---: |
| One process | 1.89 s | 0.82 s |
| Eight independent processes, total wall | 2.02 s | 0.98 s |

The cold cache cost 2.48 seconds. Inventory fingerprints matched exactly in all
checks. An eight-thread microbenchmark was slower with the cache (14.10 vs 7.42
seconds), so no thread-throughput gain is claimed; actual matrix workers are
independent processes. These are input-preparation times, not solver speedups.

## Cost And Time Limits

Read-only analysis of native tool commands in `hdr2-network-20261107-01` found
29 searches / 29 distinct exact queries and 26 fetches / 24 distinct URLs. This is
a command-level observation, not a new billing ledger. An exact-query cache would
not have avoided those search API calls. No response cache, automatic fallback or
retry was introduced merely to claim cost savings; quota/freshness semantics stay
fixed. Existing shared result files remain available to workers.

The retained HDR trajectories had model requests in flight for almost all wall
time and very low CPU use. Removing roughly a second of hashing cannot turn that
into a short solve. TLS pooling was not enabled: reuse of stale streaming provider
connections without retry needs further validation and could increase failed-call
costs. No model changes, thinking/output limits, worker policies or prompt rewrites
were smuggled into this infrastructure pass.

## Verification

Receipts: `/home/zhoujunye/mas-data/receipts/infra-final-audit-20261107/`.
730 server tests passed in 34.21 seconds. Added coverage binds cached content and
Git OID, detects mutation, checks fetch reason/status, slow body deadlines and
response cleanup, and requires grading progress before the final solver finishes.
The real-image web helper probe also passed through the local-Clash tunnel with
one public Wikipedia GET and synthetic search responses, no paid API calls.

Paid results and frozen sources were not edited. Offline checks and small samples
do not establish absence of all engineering faults or benchmark-wide time/cost
gains. Meaningful measured end-to-end comparisons still need new paid authorization.

## Final Review Pass

A second review of the same uncommitted source found and repaired five defects.
No paid model, judge or search call was made; all GETs below were free host GETs.

- The retained `hdr2-network` transcripts show all four failed fetches were Wikipedia
  API JSON or `action=raw` wikitext. The HTML/plain-text-only rule rejected them as
  `unsupported_content_type`, as it did World Bank JSON. `web-v4` accepts textual
  types (`text/*`, JSON/XML and `+json`/`+xml`); binary formats stay unsupported.
- Reason codes were misassigned: TLS certificate failures (`SSLCertVerificationError`
  is also a `ValueError`) were labelled `public_address_policy`, DNS failures
  `transport_error`. HTTP framing errors such as a truncated chunked body
  (`IncompleteRead`) escaped the handler: the helper saw an empty reply and the
  success reservation of a known failure was retained. Reasons are now assigned at
  the source by one classifier, and every host-GET exception is a known free failure.
- The helper's 30-second curl limit equalled the host fetch deadline, so a host
  timeout reason could never reach the agent and an on-time late result could be
  charged but undelivered. The helper now waits 45 seconds (frozen in `web-v4`).
- A completed web result was lost (traceback, no output) when the helper ran in a
  read-only directory. Results now save under `/workspace/web` regardless of the
  caller's directory and are printed even if saving fails.
- The Krama child monitor scanned transcript tails for phrases such as
  `authentication_error` or `insufficient balance`; tool output or data quoting them
  could stop a child, mark it provider-fatal and thereby stop the whole matrix.
  It now uses only host-ledger upstream 401/402/403 records, like DataClaw/HDR.

`docs/studies/cpu8-infra-protocol.json` now carries `web-v4`. Full manifests whose
`baseline_settings` predate this change remain valid task lists, but regenerate them
with the current profile before a new study so the frozen metadata matches.

Verification receipts: `/home/zhoujunye/mas-data/receipts/infra-final-review-20261107/`.
The server suite passed 749 tests (730 existing plus 19 new). Real host GETs through
the tunnel returned Wikipedia API JSON, raw wikitext and World Bank JSON; TLS
hostname/expiry failures reported `tls_certificate_error` and an unknown host
`dns_resolution_failed`, while bot-protected sites kept their original 401/403. The
real-image helper probe (`web-tools-probe/`) passed search, HTML and JSON fetch, a
known failure that released its reservation, and a call from `/tmp` saved under
`/workspace/web`, with synthetic search fixtures and no owned container left. A
nonexecuting full readiness plan (`readiness-plan.json`) validated 1,952 solver slots,
at most 1,836 judge calls, the image, CLI binary, existing Structured/FULL proofs and
tunnel TLS; no run namespace or credential use occurred.

## Authorized Review Closure

The user subsequently authorized the remaining repairs and CooperBench deletion.
Unexpected tool exceptions now return an MCP `isError` result instead of killing
the FULL/OBS server. A failure while persisting the error audit is isolated too.
Unexpected request-handler failures return JSON-RPC `-32603` with the original
request ID; subsequent requests continue. Raw unexpected exception text is not
returned. KeyboardInterrupt/SystemExit still propagate. No request is retried,
and an error does not claim that prior mutations were rolled back or completed.
Persistent storage failures remain visible errors, not fabricated successful reads.

Server regression: 756 tests passed in 34.01 seconds. Added stdio tests inject an
unexpected FULL/OBS tool error and an optional second audit error, then require a
successful next tool request and ping, no notification reply, correct IDs, no
exception-text leakage and no implicit retry. Separate tests cover handler errors
within batches and process-shutdown propagation. Fresh FULL/OBS native synthetic
proofs passed concurrently with the pinned image/CLI; old paid-run proofs were
not overwritten. These checks make no model-quality or end-to-end speed claim.

Receipts: `/home/zhoujunye/mas-data/receipts/infra-review-closure-20261107/`.
Use its `proofs/` set and `all-full-manifest.json` for current-source readiness
planning. The manifest freezes the current `web-v4` CPU8 profile for all 492
DataClaw, 380 HDR and 104 Krama tasks, without changing IDs, fingerprints or order.
`readiness-plan.json` is planning only, not paid authorization or a full run.

The retired server CooperBench checkout (1,323 files / 15,245,931 logical bytes)
and empty `benchmarks/cooperbench` / `scripts/cooperbench` parents were removed.
`cooperbench-cleanup.json` records the exact scope and inventory digest; no backup,
paid output, frozen paid stage or active runtime input was removed.
