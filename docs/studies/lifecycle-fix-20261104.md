# Native Lifecycle Engineering Fix

The current prompt and frozen tasks are unchanged. No solver, web or judge calls
were authorized or launched for this fix. Historical run artifacts and scores
remain unchanged.

## Changes

The lifecycle reader now reconciles unmatched Stop hooks against native killed
counts only when the root session matches, the CLI exited successfully, the
native terminal reason is completed, and unique start/stop counts match native
spawned/completed counts exactly. All remaining workers must be accounted for
by nonnegative parent/user/system killed counts; failed workers do not qualify.
Missing or contradictory evidence still fails closed. Teams remain forbidden.

Hook-unclosed IDs are retained in `active_subagent_ids`; this is hook evidence,
not a claim that those processes remain alive. Aggregate termination accounting
does not identify individual killed workers or prove workspace quiescence or
substantive worker contribution. A killed worker is not a successfully completed
worker, and a system kill's underlying cause remains unknown.

Outcome export now preserves valid, hash-bound submissions from successfully
exited CLIs even when organization admission is unverified. Their original
audit/status remains separate. Scoring verifies the frozen hash and answer
equality for these submissions too. Timeouts, cleanup failures and single-agent
policy violations remain ineligible. No automatic retry/resume is introduced.

## Verification

Source stage: `/home/zhoujunye/MAS-information-stages/20261104-lifecycle-fix`.
Server full-suite receipt:
`/home/zhoujunye/MAS-information-data/receipts/lifecycle-fix-20261104-pytest.xml`.
All 382 tests passed on the server, including termination-count reconciliation,
fail-closed evidence checks, hash-bound answer export and tamper rejection.

Read-only re-audit of the existing existing artifacts reconciled:
- HDR `sql2s_103`: one completed, one system-killed worker.
- HDR `parallel_009`: two completed, one parent-killed worker.
- Krama `wildfire-easy-3`: one completed, one parent-killed worker.

These are revised lifecycle interpretations only, not new grades. Rebuilding
historical predictions/reports requires separately labeled derived artifacts;
paid regrading requires fresh authorization. Do not overwrite original evidence.
