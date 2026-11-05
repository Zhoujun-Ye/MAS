# Native Subagents Validation20

Authorized on 2026-11-05: add the user's four-point Native Subagents prompt as
one new condition on the same 60 frozen questions. Do not rerun Single or the
Structured Subagents baseline, replace failures, or retry requests/attempts.
The user subsequently authorized one separate replacement attempt per task
affected by a confirmed, repaired engineering fault. This does not add automatic
request retries or alter the original batch; preserve both attempts and disclose
the repair and replacement selection independently of scores.

## Frozen Scope

- 20 questions each from DataClaw, HDR and KramaBench; one attempt per question.
- The unchanged `validation20-v1-manifest.json` has SHA-256
  `fc39ad8539e2af0b140a6b9a8b3144d241742b2c3b2424b6d74ae03f1829e0a5`.
- Lead text comes from `scripts/common/prompts/native_subagents.py:PROMPT`,
  UTF-8 SHA-256 `a9a51942cd7a00ea6c81c37191dc48c36e2873dcab74de47c0fb112c537ef173`.
- The Structured Subagents default is unchanged; this study uses an explicit
  lead-only raw-text override, frozen into the run directory.
- Claude Code 2.1.286, DeepSeek Flash, high effort for lead/workers, Teams disabled.
- Solver concurrency 6; grading concurrency 2; at most 53 paid grading calls.
- Limits: DataClaw 1200 s, HDR 1800 s, KramaBench 3600 s; web cap 4 when enabled.
- No project-defined output token cap or new decomposition/roster policy.
- Timeout scores are zero; other unknown scores remain unknown.
- Settings are frozen in `validation20-native-protocol.json`. No dollar cap was
  specified; authorization is bounded by 60 solver attempts and 53 grading calls.

## Execution

Source stage: `/home/zhoujunye/MAS-information-stages/20261105-native-subagents-01`.
Fresh high-effort native gateway proofs:
`/home/zhoujunye/MAS-information-data/receipts/native-validation20-high-20261105-01`.
Server validation: 360 offline tests passed; both native gateway probes passed,
with dummy credentials, network-disabled solver containers and zero paid calls.

Driver: `python -m scripts.studies.run_validation20_native --output RUN --proofs PROOFS`.
It only plans unless `--execute` is supplied. Execution requires a fresh direct
child of `/home/zhoujunye/MAS-information/outputs` and does not resume a batch.

Run prefix: `/home/zhoujunye/MAS-information/outputs/claude-validation20-native-20261105-01`.
The matrix writes authorization, fixed-task manifest, protocol, a frozen lead
prompt, progress, raw private evidence, grading results and summary. Sibling
`-export.json`, `-report/` and `.driver-status.json` are written after the batch.
The driver's `.driver.log` records progress without publishing private answers.

## Comparison Limits

The native CLI adapter is identical to the previous run's staged adapter.
Current code includes already-existing evaluation fixes after that run: valid
CLI submissions remain evaluable when native lifecycle admission is unverified,
and Krama writes an early report receipt. Preserve those flags and the earlier
baseline's artifact-only regrade provenance; do not claim a byte-identical
whole-source experiment or infer prompt causality from one reused validation set.

Costs are usage-based estimates, not invoices. Shared-account balance changes
are not per-condition charges. Native delegation evidence does not establish
substantive worker contribution. Real provider retry/rate-limit semantics remain
unverified; native retries are requested as zero and adapters do not retry.
Questions, gold SQL, answers and evaluation logs remain private on the server.

## Web Diagnostics

During the batch, observed Fetch 404s were upstream rejections, not local route
or authentication failures. Two bounded public-URL diagnostic calls produced:
DeepSeek documentation fetched successfully (200, nonempty content), while the
Wikipedia main page returned `not_found_error` (404). A direct host access check
to that public Wikipedia page also failed with `URLError`. This indicates a
site/provider availability limitation, not a demonstrated wrong API endpoint.
It does not prove every affected target is unavailable or that an answer failed.

The official [Search & Fetch error contract](https://api-docs.deepseek.com/guides/search/)
documents 404 for pages the fetcher cannot extract, including site-policy and
content-type limitations. No fallback provider, network-policy change or paid
solver replacement was launched merely because a 404 occurred.

Private diagnostic receipts:
`/home/zhoujunye/MAS-information-data/receipts/native-validation20-web-diagnostics-20261105-01`.
Only two diagnostic provider calls were made, no model calls or request retries.
The running stage remains frozen; this follow-up note was not synced into it.

## Completed Results

The driver finished at `2026-11-05T06:57:03Z` (01:57 EST), with matrix and report
exit codes both zero. All 60 CLI attempts exited normally, all 60 native lifecycle
audits passed, and all 60 answers received scores. No timeout or replacement
attempt occurred. The batch used 34 grading calls, below the authorized 53.

| Benchmark | Mean Score | Full Score | Mean Minutes |
| --- | ---: | ---: | ---: |
| DataClaw | 0.8750 | 17/20 | 5.46 |
| HDR | 0.3500 | 7/20 | 13.09 |
| KramaBench | 0.7287 | 13/20 | 8.30 |

Full-score count is 37/60, compared with the original Structured condition's
40/60 and Single's 36/60. This is descriptive, not a generalization or causal claim.
Native used more mean time than Structured in all three benchmarks.

The lead organization text is 798 ASCII characters/bytes (Structured: 2642).
All 3482 dispatched model requests observed in the host ledger requested high
effort. Retained native usage reports give token-weighted cache reuse of 97.66%
for the leader and 95.81% for members; these describe observed native messages,
not a complete or tamper-proof billing ledger.

The final web audit observed 60 successful searches, 15 upstream Fetch 404s,
and one upstream 400 each for search and fetch, across 13 affected tasks. Local
rejections were 31 disallowed routes, three invalid authentications and one
invalid model payload. No upstream 408/429/5xx or local transport/gateway error
was observed. One model stream disconnected while the lead used `TaskStop`;
its attempt still exited normally with a successful native result. Partial
usage from that request leaves its charge unknown. These observations do not
establish a repaired engineering fault warranting a solver replacement.
The final request audit is retained beside the two public-URL control receipts.

## Accounting Correction

The first report counted a pre-dispatch local rejection among provider responses
and allowed partial stream usage into complete-cost estimates. A separate
artifact-only correction now excludes local rejections, matches dispatched and
finished request IDs, and requires complete observed usage. Scores are unchanged.
The affected unknown charge is HDR `parallel_104`; total cost remains unknown.
The other 59 tasks have an off-peak-scenario estimated subtotal of USD 5.527397,
not an invoice or a complete batch cost. Actual attributable total charges are
unknown; shared-account balance deltas do not resolve that limitation.

Original solver source and reports remain untouched. Accounting source stage:
`/home/zhoujunye/MAS-information-stages/20261105-native-report-audit-01`.
All 366 server offline tests passed after the correction (six added accounting
regressions); no paid model calls or regrading were needed.

Audited server report:
`/home/zhoujunye/MAS-information/outputs/claude-validation20-native-20261105-01-report-audited-01/REPORT.md`.
The public scores/metadata report is also available
[locally](../../outputs/validation20-native-20261105-01-report-audited-01/REPORT.md).
