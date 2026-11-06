# Current Validation20 Results

20 frozen questions per benchmark and condition, one solver attempt each.
Timeouts score zero as requested. The original Single/Structured results remain
unchanged; two original HDR Subagents answers had artifact-only regrades, both zero.
On 2026-11-05, the separately authorized Native Subagents prompt condition
completed the same 60 questions, with no replacement attempts.

| Benchmark | Single Mean | Structured Mean | Native Mean | Single Full | Structured Full | Native Full |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DataClaw | 0.7750 | 0.9000 | 0.8750 | 15/20 | 18/20 | 17/20 |
| HDR | 0.3500 | 0.3500 | 0.3500 | 7/20 | 7/20 | 7/20 |
| KramaBench | 0.7454 | 0.7954 | 0.7287 | 14/20 | 15/20 | 13/20 |

Full-score totals: Single 36/60, Structured 40/60, Native 37/60. This repeatedly used development
set is not an independent final test. Different benchmark scores are not pooled.

HDR `sql2s_103` uses saved CLI final text because the required original submission
file was missing (score zero). Single HDR `parallel_009` timed out (zero).
Krama Subagents `wildfire-easy-3` retains its original lifecycle flag in this
report; offline lifecycle reconciliation did not change its score.

Retained private reports under server `/home/zhoujunye/mas/outputs/`:

- Original comparison: `validation20-current-report/REPORT.md`.
- Single/Structured uniform accounting audit:
  `validation20-baseline-accounting-audited-20261105-01/REPORT.md`.
- Native artifact-only accounting correction:
  `claude-validation20-native-20261105-01-report-audited-01/REPORT.md`.

These ignored output files are not published as repository-relative links.
The Native condition had 60 normal CLI exits and 60 passing native lifecycle
audits; these do not establish correctness or substantive worker contribution.
See [Native run and web diagnostics](studies/validation20-native.md) for limitations.
One cancelled model stream leaves the total cost unknown; no score was changed
by the accounting correction and no solver was rerun for it.
Uniform reinspection also leaves one original Single task and three original
Structured tasks with incomplete model charges. The earlier complete totals
must not be treated as audited batch totals. All three complete totals are
unknown; [README](../README.md) lists the known subtotals, cost coverage and
per-attempt times using the same accounting rule. Original scores and HDR
regrade provenance are preserved.
Original run and artifact-only regrade directories retain their recorded names;
raw evidence, original scores and earlier reports are preserved on the server.
No current prompt version label is implied by historical directory names.
