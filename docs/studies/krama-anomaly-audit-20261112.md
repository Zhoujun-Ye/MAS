# Random20 Anomaly Audit

Scope: investigate the retained `krama-random20-20261112-01` anomalies, fix
confirmed harness defects, and validate for free on the server. No paid solver,
judge, resume or retry is authorized. Frozen paid source, raw evidence and answer
grades remain unchanged. Times below use America/New_York on November 12.

## Attribution

| Attempt | Finding | Attribution |
| --- | --- | --- |
| Native astronomy-easy-5 | Mandatory-delegation prompt present; delegation tools available; no permission denials; only Bash/Write used and native spawned=0 | Model did not follow the delegation instruction |
| Structured biomedical-hard-8 | Lead stopped at 01:03:41 while waiting; CLI terminated active worker at 01:13:41, despite outer timeout 3600s | Harness omitted native print background-wait configuration |
| Native biomedical-hard-7 | Script requests a nonexistent Excel sheet; solver hid stderr, then saved an answer despite the failed run | Model-generated pipeline defect; secondary harness diagnostic masking |
| Native legal-hard-24 | Model's own pipeline output equals replay output, but answer is an object while submission answer is a string | Model failed to reconcile submission and pipeline |
| Structured wildfire-hard-18 | Final edit removed numpy scalar repr from a formatted answer; submission kept the previous string | Model changed pipeline without updating submission |
| Native legal-easy-25 stream cancellation | Stream closed during the lead's successful TaskStop; valid submission/replay remained | Expected native cancellation, not provider outage or harness timeout |

The absence of a submission in biomedical-hard-8 was previously described too
broadly as a model/native-flow failure. Its direct termination cause is now
confirmed as a harness configuration omission. This does not establish that the
worker would eventually solve the real question correctly with more time.

## Confirmed Harness Fixes

### Print Background Wait

The paid stderr explicitly says:

```text
Background tasks still running after 600s; terminating. Set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 to wait indefinitely.
```

The worker was still issuing computation tools at 01:12:40. The adapter had not
hit its 3600-second deadline. This matches the documented native
[print-mode background wait](https://code.claude.com/docs/en/headless#background-tasks-at-exit).
The installed 2.1.286 binary contains the setting and its own notice recommends
the same override; no CLI upgrade or vendoring was needed.

Set `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` for both adapters and container
environments. The existing outer task deadline still bounds execution. No new
polling, scheduler, resume, warning hook or model feedback was added. Thinking
off/T=1.0, task limits, tools, prompts and zero-retry policy are unchanged.
Native runtime proofs bind the changed environment and adapter hashes; prior
proofs cannot admit future execution.

The evidence reader no longer treats this specific system-termination notice
plus matching native kill statistics as completed delegation. It separately
retains termination accounting and the original audit. Ordinary model-initiated
TaskStop remains distinct; aggregate kill counts never prove substantive work.

### Replay Diagnostics

Previously, a nonzero pipeline exit followed by non-JSON stdout raised a JSON
parse error, hiding the useful root cause. Record execution failure before
parsing stdout, preserve stderr/exit code, and expose typed `pipeline_replay`
statuses for missing/invalid submission, execution failure, malformed output,
answer mismatch, replay timeout and harness failure. No automatic answer repair,
normalization, extraction or scoring-policy change is introduced.

An independent network-disabled replay of the untouched biomedical-hard-7
pipeline reproduced exit 1 and the same missing-worksheet error. Original,
frozen-file-manifest and replay script SHA-256 values agree. The wrong worksheet
is in the model's script, not a changed replay environment. The solver used
`2>/dev/null` and a later successful shell command, masking its own error.

The two mismatch cases also retain identical source hashes. Legal-hard-24 had
already printed the same mismatching object during solving. Wildfire-hard-18
changed `[np.float64(...)]` formatting to ordinary floats in its final pipeline
edit but did not refresh the submission's text. Do not relax exact output
consistency to hide either defect.

### Reporting

The report now labels the existing compliance score as Single-policy-only,
rather than implying Native/Structured compliance. It includes replay statuses,
exit/match fields and a dedicated pipeline diagnostics section. The refreshed
background-wait audit is reported alongside the original recorded audit.
Original answer means remain 53.33%/80.00%/71.67%; no question is selectively
dropped and no historical grade is changed. Corrected lifecycle audit counts
are Single 20/20, Native 19/20, Structured 19/20, versus the old Structured 20/20.
Structural audit is still not evidence of semantic contribution or correctness.

## Free Verification

Independent source: `/home/zhoujunye/mas-stages/20261112-anomaly-audit-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/anomaly-audit-20261112-01`.
The production tree and frozen paid source were not overwritten by this fix.

- Full server suite: 1011 tests passed, no skips.
- Two normal native admission checks passed for Single/Subagents, with the same
  thinking-off/T=1.0 wire policy and background wait override observed.
- Shortened-ceiling control: a synthetic 12-second worker was killed before
  completion; the lead never resumed. The audit correctly fails.
- Fixed configuration: the same synthetic worker completed, native notification
  resumed the lead, and the lead wrote the expected marker (about 15 seconds).
- Outer-deadline check: a 5-second host deadline still stopped the session and
  all owned containers/sockets were removed. No indefinite process was left.
- Three complete Krama fake-provider workflows and three one-request HTTP503
  checks passed for Single/Native/Structured, including zero native retries.
- One isolated offline artifact replay reproduced the model's worksheet failure.

This is 11 free native checks plus the artifact replay, not real-model recovery
evidence or a replay of the paid attempts. The shortened control validates the
same native setting mechanism, not a new paid ten-minute experiment. Injection
proofs are explicitly rejected for paid admission.

`original-evidence-before.json` and the final verification bind 62 original
evidence files and all frozen paid source files. The corrected report is in a
fresh `derived-report/` directory; previous exports and raw results are retained.
One cancelled stream's complete usage/charge remains unknown, not zero.

## Timeout Policy And Diagnostics

Outer solver timeouts still score zero even if an answer exists; retained
`artifact_grade` is diagnostic. Do not assume a historical attempt would recover
under the new wait setting without a separately authorized run.

The CLI records `native_started_at` and `timeout_observed_at`, the latter before
cleanup. Krama's `timeout_diagnostic` and report/CSV expose `lead_idle_waiting`,
`submission_schema_valid`, `submission_present_at_deadline` and
`lead_waiting_with_valid_submission` separately from scores.

Waiting means a recorded root Stop had pending workers and no later lead activity
before the host timeout. Cleanup events after that boundary are excluded.
Submission validity means non-null answer plus the existing schema/path checks,
not correctness; timing uses post-cleanup file mtime. Missing/malformed timestamps
give unknown. This is cooperative evidence, not adversarial timestamp integrity.
No polling, intervention, submission selection or retry was added.

## Docker Replay Attribution

[Docker exit statuses](https://docs.docker.com/engine/containers/run/#exit-status)
125/126/127 can also come from a submitted process. Replay retains its stopped
container until inspecting structured `.State` (start time, status, error and
actual exit), then removes the owned container in finally. A verified process
exit is `runtime_error`; Docker launch failure or unverified execution origin is
`harness_error` with `DockerExecutionError`, not model blame. Historical reserved
exits without this evidence are `execution_origin_unverified`. Answer metrics
remain unchanged.

## Paired Native-Audit View

`paired_native_audit` requires exactly one row and a passed native audit per
condition/task. Failed/unmeasured audits or missing conditions remove the whole
task from this additional view. Authorized selections define expected cells;
duplicates make the view unavailable. Excluded IDs/reasons are listed; original
scores, main denominators and all incurred costs stay intact. Legacy guard-based
Primary columns are not renamed into a new headline metric.

For `krama-random20-20261112-01`, astronomy-easy-5 and biomedical-hard-8 are
excluded from all conditions:

| Condition | Same Tasks | Answer Score Sum | Answer Mean |
| --- | ---: | ---: | ---: |
| Single | 18 | 9.6667 | 53.70% |
| Native | 18 | 14.0000 | 77.78% |
| Structured | 18 | 14.3333 | 79.63% |

This is an audit-filtered sensitivity view on a reused diagnostic set, not a
causal organization comparison, independent test or selective replacement.

## Partial Cost Display

Incomplete totals remain null in JSON. Markdown shows a lower bound from every
known request subtotal plus known web/judge components, not only fully costed
attempts. Unknown request counts/components remain explicit; wholly unmeasured
costs stay unknown, not zero.

Native's known model subtotal is USD0.215011254 with one unknown request. Including
grading, the known subtotal is USD0.215052654, displayed as
`>= $0.215053 (1 unknown model request)`, not an invoice or conversion of the
account-wide CNY balance change. CSV retains these subtotals/counts.

## Follow-Up Verification

Historical source stage: `/home/zhoujunye/mas-stages/20261112-anomaly-followup-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/anomaly-followup-20261112-01`.
The second free verification passed **1032 server tests, no skips**, six real
Docker failure/process-exit fixtures, two native admission checks, one native
outer-deadline check and three Single/Native/Structured synthetic workflows.
All owned containers/sockets were removed. Timeout tests retain zero primary
credit and preserve diagnostic artifact grades.

`verification.json` binds the same 62 original evidence files, 202 frozen paid
source files and unchanged answer scores. `report-final/` has identical
eighteen-task cohorts and explicit partial-cost bounds. Paid calls: zero.
Production was not deployed by either anomaly investigation. Regression checks
live in `tests/test_krama_anomalies.py`; the receipts retain historical verification.
