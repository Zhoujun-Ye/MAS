# HDR Local-Network Retest

Authorized scope: `parallel_016` and `s2sql_024`, Structured/FULL once each,
four concurrent solvers, at most two model grades plus two deterministic SQL
grades. No reruns. CPU8/four numerical threads, DeepSeek Flash/high, HDR 1800s.
Canonical configured solver slots remain eight (only four jobs), judge slots two.
Web-v3 uses local Clash fetch, compact ten-result search and 20 successful shared
web calls / 40 logical attempts per run. Estimated admission CNY10, factor1.5,
reserve CNY5, not a hard invoice cap.

Frozen source: `/home/zhoujunye/mas-stages/20261107-hdr2-network-01`, based on
commit `86bc64e`. Raw run: `/home/zhoujunye/mas/outputs/hdr2-network-20261107-01`.
Export: `/home/zhoujunye/mas-data/receipts/hdr2-network-20261107-01/`.
Comparison source: `threebench2-engineering-20261107-01`, same frozen tasks.

| Task | Condition | Previous CLI Min | New CLI Min | New Score |
| --- | --- | ---: | ---: | ---: |
| parallel_016 | Structured | 30.01 (timeout) | 20.97 | 0 |
| parallel_016 | FULL | 23.55 | 21.25 | 0 |
| s2sql_024 | Structured | 26.20 | 17.34 | 0 |
| s2sql_024 | FULL | 30.01 (timeout) | 20.71 | 0 |

All four solvers exited normally; both authorized model grades completed, no
automatic recovery. Structured average fell from 28.11 to 19.15 minutes, FULL
from 26.78 to 20.98. Total batch wall time was 21.51 minutes. Both conditions
remain zero out of two; FULL consistency-gate acceptance is not correctness.

The gateway recorded 331 model responses with HTTP200, 29 successful-HTTP search
responses, 22 successful fetches and four fetch failures. There were no model 5xx,
proxy-unavailable records, balance pause or monitor failures. The four fetch
failures entered local-Clash transport handling, were recorded as ValueError and
released success reservations. The wrapper's HTTP502 is not the original website
status. Its logs do not distinguish target HTTP errors, unsupported content,
redirect/security rejection or size limits; specific causes are unverified.
The frozen code was not changed or failures automatically retried during the run.

Shared-account snapshots changed CNY43.60 to CNY36.86, an interval delta CNY6.74,
not a per-condition attributable invoice. Some request usage is incomplete, so
per-condition full token-cost estimates remain unknown, not zero. No OOM or CPU
throttling was observed; all owned containers were removed.

This is a repeated two-question validation smoke, not benchmark-wide evidence.
The comparison changes the complete web infrastructure (transport, quota and
presentation), so the time difference cannot be attributed to the tunnel alone.
It supports improved completion in this sample, not improved semantic accuracy.
