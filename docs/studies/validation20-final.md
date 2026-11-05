# Validation20 Run

Authorized on 2026-11-04: freeze the user's supplied prompt as the current prompt and rerun
Strict Single versus native Subagents on all 20 fixed questions per active
benchmark. This is the reused development/validation set, not a final held-out test.

## Frozen Configuration

- Claude Code 2.1.286; DeepSeek Flash; lead/worker effort high; Teams disabled.
- 3 benchmarks x 20 questions x 2 conditions = 120 solver attempts, one each.
- At most 106 paid grading calls; remaining HDR tasks use SQL evaluation.
- No retries or replacement attempts; preserve failures and audit exceptions.
- Solver concurrency 6, grading concurrency 2, isolated workspaces/outputs.
- DataClaw 1200 s, HDR 1800 s, Krama 3600 s; shared web request cap 4 where enabled.
- No project-defined output token cap. Both native offline probes requested
  max_tokens=32000 with the cap absent; this is a native default, not unlimited.
- The original task manifest is unchanged, SHA-256
  `fc39ad8539e2af0b140a6b9a8b3144d241742b2c3b2424b6d74ae03f1829e0a5`.
- New protocol: `validation20-final-protocol.json`, SHA-256
  `98e093d9ca5c78728d6c381cc881640108f7d0c8526cfc49c2f6c3a66bd4c001`.
- Final prompt UTF-8 SHA-256 (no trailing newline):
  `31ff6e4176a25d961866f644adb4d7b97cb4b00228e696c0e4e38a52b9485a95`.

## Server Receipt

Source: `/home/zhoujunye/MAS-information-stages/20261104-final-v5`.
Offline proofs: `/home/zhoujunye/MAS-information-data/receipts/final-v5-native-default-offline-01`.
All 374 server offline tests passed; both native gateway probes passed with zero
paid calls. These checks do not establish solver accuracy or real-provider behavior.

The detached driver is `scripts/studies/run_validation20_final.sh`. It runs the
fixed matrix, then exports a report even when individual attempts fail, provided
the matrix summary is available. It records both exit codes separately. It does
not resume or retry a failed batch.

Output prefix on the server:
`/home/zhoujunye/MAS-information/outputs/claude-validation20-final-v5-20261104-01`.

- Prefix directory: authorization, progress, private solver/grading evidence, summary.
- `<prefix>.driver.log`: background driver log.
- `<prefix>.driver-status.json`: matrix/report exit codes, present after driver ends.
- `<prefix>-report/REPORT.md`: human-readable comparison.
- `<prefix>-report/task-results.csv`: per-task results.
- `<prefix>-report/summary.json` and `<prefix>-export.json`: scores and accounting.

Reports retain unknown scores/costs rather than converting them to zero. Token
prices are off-peak estimates, not invoices; the account balance delta spans the
shared account interval and cannot be attributed exactly to either condition.
Native delegation lifecycle audits do not establish substantive worker contribution.
Questions, gold SQL, answers and private evaluation logs remain on the server.
