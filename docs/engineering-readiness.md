# Baseline Engineering Checks

This checklist addresses the ten review findings supplied on 2026-11-04.
Engineering verification uses fake providers and makes no paid API calls.
It is not a benchmark accuracy or cost result.

| Finding | Current handling |
| --- | --- |
| Direct network bypass | Gateway-backed containers force `network=none`; only the mounted Unix gateway reaches provider routes. |
| Inconsistent web limits/errors | Plan, helper and gateway use the same effective default of four attempts; local budget exhaustion and provider rate limits have distinct errors. |
| Formal versus substantive delegation | Native lifecycle is structural evidence only. Child tool observations are retained; substantive contribution stays `unverified`, including reasoning-only workers. |
| Direct tool-origin model requests | Every permitted model request is in the host ledger. The token does not authenticate process origin; no claim that direct calls are impossible. |
| Writable/missing accounting | Fsynced host-only started/dispatched/finished receipts are authoritative; resetting the helper ledger cannot reset quota. Missing usage/completion stays unknown. |
| Lost upstream errors/headers | Sanitized JSON errors and request-ID/rate/retry headers are forwarded. Credential-bearing headers, redirects and cookies are not. Non-JSON/oversized errors are safely wrapped/truncated. |
| Krama timeout regression | Restored 3600 seconds; DataClaw uses upstream 1200; HDR uses provisional 1800. |
| Prompt/instructions conflict | AGENTS documents the explicitly authorized orchestrator-worker prompt and distinguishes it from unprompted native behavior. |
| Stale CLI/transport documentation | Claude 2.1.286; native wire protocol through the credential gateway; no SDK orchestration. Codex is retired. |
| Lead rules visible to workers | Shared Krama rule files contain only generic task rules; lead organization instructions stay in the lead prompt. Native context inheritance is not eliminated. |

Additional checks cover runtime-bound proof admission, independent task outputs,
bounded concurrency, matching within-benchmark timeouts, no automatic retries,
SIGTERM cleanup, ownership registered before Docker creation, interrupted gateway
requests, and no re-dispatch after shutdown. In-flight provider work cannot be
declared unbilled merely because a local process was stopped.

## Evidence

Server receipts under `/home/zhoujunye/MAS-information-data/receipts/`:

The engineering stage regression suite passed 298 tests on 2026-11-04, using the
existing server evaluation environment. Earlier Codex fixture checks are historical only.

- `native-gateway-offline-02/summary.json`: all four real native CLI modes passed
  through the gateway in parallel, with native delegation/denial and shell checks.
- `credential-isolation-offline-07/proof.json`: both container configurations
  blocked direct external sockets, hid the host key and ledger, and retained the
  web quota after the solver-writable helper ledger was cleared.

The user requested engineering and cleanup only after stopping the old batch.
No fresh paid solver/judge run is part of this verification. Old benchmark outputs
and interrupted matrix records were deleted; source-only snapshots, input data,
environments and useful offline proofs remain. See [retention](archive.md).

## Remaining Boundaries

Same-UID native/tool processes share access to the run token. Host accounting
covers their gateway requests but does not independently attest which process
originated each request. Native profiles are solver-writable evidence, not a
tamper-proof audit trail. Semantic delegation quality requires separate review;
native start/stop events and tool counts alone cannot prove it. These limits must
remain visible in any future baseline report.
