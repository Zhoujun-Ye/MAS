# FULL Infrastructure Audit (November 10)

Historical paid evidence only. FULL/OBS and prompt-only ablations were retired
on 2026-11-10; the runtime and launch paths are no longer active.

## Scope And Evidence

The six retained FULL attempts in `threebench2-20261109-01` contain 472 native
terminal Bash events, all represented in their stores. No store was degraded or
pending at termination. All host gates accepted, but HDR SQL had no comparable
candidates (`coverage=false`). Three rejected DataClaw selections later succeeded.
Gate acceptance, emission and access do not prove correctness or model uptake.

The following paid check and subsequent free repairs are distinct. No frozen
paid source, original result or incurred-cost record was rewritten.

## Capture And Read Defects

Fifteen original Bash results across four attempts contained native overflow-file
pointers, but their previews were marked complete. Retained files matched declared
byte sizes and differed from previews. This could miss tail results and misstate
complete access; it does not establish the cause of any particular wrong answer.

The repair marks overflow as `pointer`, preserves raw hook payloads and snapshots
bounded original artifacts for `obs_read(field="persisted_output")`, without
inventing stdout/stderr separation. Missing/unsafe/oversized files remain explicit
unavailable pointers. Nested interruption/truncation flags exclude incomplete
candidates. Duplicate/out-of-order hooks reuse snapshots even if sources disappear.

The paid HDR check also made four `obs_read(limit=16000)` calls rejected because
only absolute `end` was supported, unlike `decision_read`. A later bounded
`start/limit` compatibility parameter preserves `start/end`, rejects ambiguous
`end+limit` and does not bypass decision review or retry old calls.
The [canonical contract](intermediate-full.md) owns these APIs.

## Authorized Paid Check

Four FULL attempts, at most two paid grades, CNY20 planning estimate, no retries.
Original task/model/prompt/timeouts, CLI/image and CPU8/thread4 were unchanged.
Three independent controllers supplied total solver concurrency four (2/1/1);
only DataClaw used paid grades, at most two concurrently.

Frozen source: `/home/zhoujunye/mas-stages/20261110-full-infra-01`.
Batch: `/home/zhoujunye/mas/outputs/full-infra-paid4-20261110-01/`.
Receipts: `mas-data/receipts/full-infra-20261110-01/`.

| Task | Score | CLI Minutes | Model Requests | Overflow Snapshots |
| --- | ---: | ---: | ---: | ---: |
| DataClaw hard011 | 1.0 | 7.70 | 90 | 2/2 |
| DataClaw medium006 | 1.0 | 10.30 | 135 | 5/5 |
| HDR s2sql_024 | 0.0 | 28.91 | 105 | 1/1 |
| Krama astronomy-easy-1 | 1.0 | 3.18 | 46 | 0/0 |

All four native audits and gates passed with comparable candidate coverage.
All 365 terminal Bash events were captured. Eight overflow results were saved,
marked pointers and excluded from complete candidates. DataClaw/Krama had no
workspace tool errors; HDR's four argument errors remain recorded, not hidden by
its final successful gate. HDR's consistent submission was still wrong.

Exactly two paid DataClaw grades ran; HDR SQL and Krama were deterministic.
Retained output tokens total 583,069; token-weighted input cache hit is 97.61%
over 29,616,593 recorded input tokens. Per-role accounting and actual CLI prompt
lengths/hashes are in `paid-audit.json`. Missing Krama organization-length metadata
is unknown, not zero. The joint shared-account balance fell CNY10.58, not an
attributable invoice. No call or grade was retried.

There were 17 successful fetches, one DataClaw DNS failure and two HDR TLS failures.
The user confirmed a Clash node/config change during investigation; its exact time
was not captured. This is not a clean network-controlled efficacy comparison or
a held-out test. Both DataClaw scores are now 1.0, but one repeated attempt cannot
attribute gains to capture repair. HDR remains wrong; infra alone has not solved
quality. The paid stage stayed on web-v4 throughout.

## DNS And Service Repair

The campus DNS returned empty SEC A/AAAA results with `user.rpz`, while Clash's
DNS API resolved the domain. Thus server DNS could fail before a GET ever entered
the Mac tunnel, despite browser access. Separately, local proxy TLS failures
occurred and later checks passed after the user changed node/config; the exact
old exit failure is not conclusively identified.

The user then authorized web-v5 DNS alignment through a restricted private bridge,
without system-DNS/Clash-profile changes, fallback or retry. It exposes only
bounded A/AAAA queries, never the Clash control socket. Public-address checks,
IP-pinned CONNECT and original-host TLS verification remain.
See [Web And DNS Transport](web-infra.md).

A real API probe caught Mihomo's uppercase Question fields before activation.
Reinstall also exposed a launchd race: successful bootout could leave its old
registration briefly visible. Installation now waits boundedly for disappearance
and still rejects genuine unload failures.

## Verification And Limits

Receipts: `mas-data/receipts/clash-dns-20261110-01/`.
The final pre-cleanup server suite passed 900 tests in 42.99 seconds.
`native-proofs-with-read/` passed FULL/OBS with 17/14 synthetic model requests,
zero workspace errors and containers removed; FULL read an actual overflow tail
using `limit`. `combined-final-verification.json` verifies all eight overflow
blobs, replays the four failed arguments read-only, checks unchanged database
hashes and binds deployed source to current proofs. No extra paid call followed.

Real network-none container probes passed Wikipedia HTML/JSON, synthetic search,
failure accounting and shared files outside the workspace. Installed helper/runner
hashes matched source; both owned remote sockets were mode 0600 and SSH was live.
SEC then resolved and completed TLS but returned HTTP403, a site refusal rather
than DNS failure. Stable access to every site is not guaranteed.

That repair's cleanup/probe receipts are in `maintenance-20261110/`, with 905 passing
server tests and fresh FULL/OBS raw proofs in `native-evidence/`. Earlier proof
summaries remain; duplicate synthetic payloads and test XML were consolidated
under the [retention policy](../archive.md). The paid check
does not validate the later DNS/read repair's effect on scores; no new paid
web-v5 experiment was authorized.
