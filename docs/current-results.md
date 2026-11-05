# Current Validation20 Results

20 frozen questions per benchmark and condition, one solver attempt each.
Timeouts score zero as requested. No prompt change or solver rerun was made.
Two HDR Subagents answers were regraded from existing artifacts; both scored zero.

| Benchmark | Single Mean | Subagents Mean | Single Full Score | Subagents Full Score |
| --- | ---: | ---: | ---: | ---: |
| DataClaw | 0.7750 | 0.9000 | 15/20 | 18/20 |
| HDR | 0.3500 | 0.3500 | 7/20 | 7/20 |
| KramaBench | 0.7454 | 0.7954 | 14/20 | 15/20 |

Full-score totals: Single 36/60, Subagents 40/60. This repeatedly used development
set is not an independent final test. Different benchmark scores are not pooled.

HDR `sql2s_103` uses saved CLI final text because the required original submission
file was missing (score zero). Single HDR `parallel_009` timed out (zero).
Krama Subagents `wildfire-easy-3` retains its original lifecycle flag in this
report; offline lifecycle reconciliation did not change its score.

[Current report](../outputs/validation20-current-report/REPORT.md).
The same report is under server `/home/zhoujunye/MAS-information/outputs/`.
Original run and artifact-only regrade directories retain their recorded names;
raw evidence, original scores and earlier reports are preserved on the server.
No current prompt version label is implied by historical directory names.
