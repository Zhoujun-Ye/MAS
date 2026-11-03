# Native CLI Integration Audit

## Scope And Evidence

This audit follows the 12-attempt CLI pilot and the user's explicit request to
replace the active Claude Code 2.1.177 installation, verify a moderately newer
version, audit the adapter, and run 104 tasks on each CLI. The full scope is
208 solver attempts and at most 20 independent Flash semantic-judge requests,
zero automatic retries, with no monetary cap. This authorization is run-specific.

The original pilot outputs, grades, raw profiles, source.tgz and corrected
report overlays remain unchanged. Source before this audit is preserved in
`archives/native-cli-audit-20261102/local-source-before.tgz` locally. The old
server binary is retained only as historical evidence under the matching server
archive, not as the active launcher. Its auxiliary installer receipts remain
historical files, not a second active CLI.

## Findings And Repairs

1. **Wrong interface to carry forward as an Agent Team baseline.** The old
   adapter used `--print`. Current official documentation explicitly excludes
   true teammates in print/SDK mode. Historical v177 traces and its team-tools
   calls alone do not establish equivalence to an interactive native team.
   This is an integration validity problem, not proof that every old failure
   was caused by the adapter. The new Team path uses a controlling terminal
   and the actual interactive CLI. Explicit legacy print mode is labeled
   subagents-not-team and has teams disabled.
2. **Obsolete closure policy.** v2.1.178 removed TeamCreate/TeamDelete and made
   each session's team implicit. The previous instruction to clean up teams
   encouraged manual runtime-state edits in all six Claude trials. The new
   request prohibits such edits and does not manufacture a TeamDelete step.
   Native idle/stop/end evidence and read-only config snapshots are retained;
   a final assistant claim is never treated as verified shutdown.
3. **Missing interactive transport validation.** The replacement transport
   uses util-linux script, not Python preexec_fn in batch threads. It supplies
   the complete request through a workspace file, captures raw terminal output,
   and records native hooks without granting tools or scheduling workers.
   Only known first-launch theme/security acknowledgments and trust for the
   owned disposable workspace are answered. Tool-permission and login-method
   dialogs are not automatically accepted; no bypass-permissions flag is used.
4. **Lifetime is not activity.** A persistent teammate may be alive but idle.
   The observer accounts for native TeammateIdle and approved shutdown events,
   rather than assuming every SubagentStart needs a process-lifetime Stop.
   The latest root Stop must follow observed worker activity before /exit is
   requested. Config reads racing native replacement/deletion do not crash the
   CLI. Observation is not a security boundary or a new scheduling protocol.
5. **Ambiguous output and currency handling.** Future pipelines have one
   explicit final-line contract: a JSON object with exactly `answer`. Answer
   grades remain separate from artifact formatting/replay. Balance differences
   are computed with Decimal per native currency; missing USD is null, not zero.
   Actual interval receipts are not allocated to cases or conflated with native
   Claude's unsuitable dollar price estimates.
6. **Full-run admission and evaluation.** A frozen 104-task manifest binds
   input/scoring/source hashes, installed CLI hashes, budgets and the successful
   network-disabled terminal probe. The astronomy canary runs once per backend
   within the 208 attempts. Only genuine named members, artifact validity,
   ordered native completion and no shell writes to team state release the
   remaining 206. No score or reference is used for admission. Provider
   authentication/balance errors stop admission and owned active containers.
   Gold evaluation/replay and separate one-request semantic judging follow
   solver drain. Failed attempts and failed judge receipts remain evidence.

## Version Choice

Selected **Claude Code 2.1.225**, rather than the current latest branch. It
includes v198 teammate failure reporting, v207 mailbox handling, v212 team
notifications/inter-agent context fixes, v224 failed mailbox-delivery reporting,
and v225 parked-message fixes. It precedes v232's default subagent-fork changes.
This preserves the native named-teammate/shared-task/direct-mail pattern, not
the removed TeamCreate/Delete API. No version pin guarantees a model will use
a particular organization or that all native bugs are fixed.

The Linux binary was downloaded locally from the official distribution, then
transferred to the server after the server's direct CDN connection timed out.
Verified official SHA-256:
`0a3be8d18cb0f5357d38ce2d588601753a60b44cc9c622579ed8b8405dee231e`.
Active launcher: `/home/zhoujunye/.local/bin/claude`.
Deep Agents remains external `deepagents-code==0.2.2`; no runtime is vendored.

## Verification And Limits

The real native CLI's version/help and network-disabled first-launch/exit were
checked in the existing data image. The successful probe is
`outputs/claude225-terminal-preflight-20261102-05/preflight.json` on the server:
normal process exit and native SessionEnd, dummy credentials, no provider
network and no model calls. Earlier failed offline probes are retained too.
They exposed first-launch terminal acknowledgments, not paid solver failures.

Offline regression covers actual controlling-terminal stub processes, root vs
member completion order, persistent-member idle handling, no tool-consent
automation, native-team admission, currency handling and single-call judge
failure semantics. Live canary admission and full-run completion are separate
facts, recorded in the run's admission-audit.json/progress.json/summary.json;
they must not be inferred from this source-level audit.

The frozen solver stage is `/tmp/mas-native225-source.Gc7DqV`; its pre-dispatch
regression passed 96 tests. The authorized run namespace is
`outputs/kramabench-native-full-20261102-01`. It runs in the dedicated
`mas-information-bench` tmux server, session `native-full-20261102`, so a client
disconnect does not terminate it. The source stage is not modified after freeze.
Its plan receipt is
`0e559c7ded4c46434b47d6b6ff3e5388832e2ee75f9628104378472d15052817`.

Read-only full-run reporting is staged separately at
`/tmp/mas-native225-report.yl79TU`; that stage passed 98 tests, including two
additional reporting fixtures. Session `native-full-report-20261102` waits up
to 24 hours for summary.json and writes FULL-REPORT-v1.md/full-report-v1.json.
It dispatches no model calls, judges or replay. Reporting groups binary and
continuous metrics separately, retains semantic-judge overlays and original
grades, and uses implicit-team evidence rather than retired TeamDelete calls.
These launch/report details do not establish full-run completion; inspect the
receipts above for the current result.

## Completed Full Run And Remaining Validity Issue

The 208 solver attempts finished, followed by 20 successful semantic verdicts,
with no replacement attempts. The final receipt is 2026-11-02 20:15:35 UTC
(15:15:35 America/New_York). Deep Agents had 104 normal exits and 104 matching
offline replays. Claude had 103 normal exits, one 3600-second timeout, and 99
matching offline replays. The actual account interval reduced CNY 147.36 during
solving and CNY 0.36 during judging; these are account-wide intervals, not
individually allocated bills.

**The interactive completion heuristic still is not sufficient.** Four normal
Claude exits have no submission: biomedical-easy-6, environment-easy-4,
legal-easy-12 and legal-easy-13. Their last root assistant text explicitly says
it is waiting for teammate reports. The adapter then sent /exit after native
Stop/idle met its two-second rule (`harness/claude_code/terminal.py`). Native
message delivery, model wait loops and premature adapter closure have not been
causally separated. Do not treat those four as clean solver-ability failures,
or infer benchmark/task completion from SessionEnd. The astronomy-hard-11
timeout is separate. No solver reruns or runtime edits were made during this
results inspection; all original invalid-submission grades remain unchanged.

The read-only report initially failed on a JSON scalar in terminal stdout;
that parser now requires a dictionary before reading event fields. The first
report revision also falsely flagged `/workspace/teams/...` analysis code as
native state mutation. Revision 2 narrows detection to native profile paths;
no native-state write commands were detected by that heuristic. Both revisions
and original receipts remain on the server. Reporting uses the already
installed dcode tool Python for its read-only ormsgpack decoder, not a new
dependency installation. Its final regression passed 100 server tests.
Use FULL-REPORT-v2.md/full-report-v2.json, not revision 1, for the audited summary.

## Corrected Single Baseline And Targeted Repair Run

The user clarified that Deep Agents must be strictly single-agent and authorized
104 fresh Single attempts plus at most 10 semantic verdicts. Claude is limited
to fresh attempts on the five identified problem tasks (four missing-submission
cases and astronomy-hard-11), not a new 104-task Team run. Both remain Flash,
zero automatic retries, with no replacement attempts. The old 104-task dcode
run delegated in 77 tasks and must not be labeled Single.

Closer inspection isolated an observer race: in all four missing-submission
cases, a native teammate-message user record was appended just after root Stop.
Those automatic inputs did not emit UserPromptSubmit. The old hook-only observer
therefore sent /exit two seconds after a stale Stop while new native input was
pending. For example, biomedical-easy-6 recorded Stop at 18:05:14.257 UTC and the
teammate packet at 18:05:14.307 UTC; legal-easy-12 recorded Stop at 18:55:53.635
and the packet at 18:55:53.688. A read-only replay of all four identifies pending
input under the new observer. This pinpoints a transport completion bug, not a
general inability of teams to solve the tasks.

The repaired transport incrementally observes native root transcript user
records and invalidates the preceding Stop until a newer Stop follows them.
It never reads a mailbox to inject messages, schedules workers or changes native
state. Benchmark runs also require a submission file before automatic /exit.
The request now explains native turn yielding and forbids sleep/poll waiting;
there is still no fixed roster or custom decomposition. Claude stays at 2.1.225.

Frozen source for these new runs: `/tmp/mas-single-repair-source.pnw1TC`, with
113 offline server tests passed, including a real-TTY regression where automatic
input arrives after Stop while a reply is still in flight. The installed dcode
also passed a no-network, dummy-key, fake-provider test deliberately trying to
delegate: native PreToolUse denied task, no SubagentStart, and the denial returned
to the same root model. No SDK was imported or patched by this adapter.

Run namespaces are `outputs/kramabench-single-deepagents-20261102-01` (104 + 10)
and `outputs/kramabench-claude-repair5-20261102-01` (5 + 0). Dedicated tmux server:
`mas-single-repair`. Single runs first; Claude waits for its final receipt, keeping
their account intervals separate. Each uses an included admission task before
releasing remaining tasks. Separate read-only report jobs wait for final progress,
not just the existence of a partially written summary. Their results must be
read before claiming successful completion or a general quality improvement.

The first strict Single attempt used dcode's implicit 50-turn safety default.
It wrote a valid, replayable submission but exited 124 at that native limit;
its native hooks still prove zero subagents. The admission gate stopped the
remaining 103 before dispatch. This is a retained failed lifecycle attempt,
not a discarded test, and it is not retried. A separate continuation manifest
binds that exact prior summary and excludes astronomy-easy-1 before dispatching
the other 103 tasks with an explicit 500-turn native cap and the same 3600-second
wall-clock limit. This mixed-cap limitation must remain in any combined report.
The continuation has at most 10 judges (the first task used none). Total Single
solver attempts remain 104. It waits for the five-case Claude repair interval
to finish so balance intervals remain disjoint. Frozen continuation source:
`/tmp/mas-single-cont-source.8bIpKo`; output namespace:
`outputs/kramabench-single-deepagents-cont103-20261102-01`.

Subsequent user directions supersede that initial scheduling/retention plan:
the waiting session was removed and the 103-task continuation was started
immediately while the last Claude repair case was still active. Its admission
passed, and twelve Single containers were observed running simultaneously.
The continuation's account interval therefore overlaps Claude; its balance
delta cannot be attributed to Single alone or added to the overlapping Claude
delta as a total bill. Native visible-token estimates remain separate.

The user then explicitly authorized rerunning the first task too. A fresh
`single-repair1` plan uses the same 500-turn native options, instructions, CLI
hashes and Single guard as the 103-task continuation. It runs after those 103
finish, with no additional semantic judge. Output:
`outputs/kramabench-single-deepagents-first500-20261102-01`; frozen source:
`/tmp/mas-single-first-source.VL6ZPT` (115 server tests passed).
The formal baseline now joins this fresh first task with the other 103 tasks,
and excludes the older 50-turn diagnostic. Total actual Single dispatches
including that retained diagnostic are 105, not 104. The old diagnostic is not
overwritten or silently removed. The read-only combined report validates that
native options/instructions/CLI hashes match before joining the fresh first
task; it does not modify either solver summary or original grades.

## Scale-Aware Numeric Scoring Repair

The user authorized fixing the tiny-number scoring defect while the strict
Single run was already active. Local future scoring now defaults to
`scale_aware_v3`: binary numeric success uses target-relative tolerance 1e-4,
no absolute epsilon, and exact zero for a zero target. The original relative
scale is retained, not tuned to the observed 10.12% error. Other metrics are
unchanged, and `upstream_v2` remains explicit for reproducing old evidence.
This corrected local metric is not labeled an unchanged official score.

Running/frozen solver stages were not modified. A separate offline scorer stage
`/tmp/mas-score-v3-source.GH2kd6` passed 126 server tests, including sign/scale
invariance, tiny references, zero, numeric strings, legacy differential checks,
immutable overlays and artifact-bound semantic-verdict reuse. The rescorer first
reproduces each original grade from the exact exported artifact and pinned
reference, then writes corrected grades into a fresh namespace. It never invokes
a model, judge, CLI solver or submitted pipeline.

Completed overlays:
- `outputs/kramabench-claude-repair5-scale-aware-v3-20261102-01`: one score
  changed; the astronomy-hard-11 approximation is now 0, yielding four binary
  passes out of five. The other four answers remain equal to their references.
- `outputs/kramabench-native-full-scale-aware-v3-20261102-01`: five historical
  scores changed (three dcode, two Claude). All 20 existing semantic verdicts
  were reused, with zero new judge calls. The historical dcode arm allowed
  subagents and still must not be called Single.

The new 104-task Single overlay waits for both the 103-task batch and fresh
500-turn first task to finish: tmux server `mas-score-v3`, session
`single-v3-overlay`. Output will be
`outputs/kramabench-single-scale-aware-v3-20261102-01`; its controller log is in
the 103-task run as `v3-score-controller.log`. It excludes the old 50-turn
diagnostic and reuses the authorized ten semantic verdicts without calling a
judge again. Until that receipt exists, full corrected Single results are not
complete. Neither the numeric correction nor a successful pipeline replay
certifies an exact scientific-model implementation.

## Final Publication And Source Cleanup

All fresh strict Single 104 attempts and ten semantic verdicts finished. Every
attempt has native zero-subagent evidence, zero checkpoint member messages and
a matching offline replay. The old 50-turn first task remains a diagnostic;
the formal baseline includes the user-authorized fresh 500-turn first task.

At the user's request all five repaired Claude cases now replace their old
entries in the formal 104-task result snapshot. The publisher applies every
specified replacement, not best-of-score selection, and retains old/new source,
artifact hashes, status and scores in replacements.json. V3 scores are 55/84
binary successes for Single and 61/84 for the merged Team snapshot. The other
20 tasks retain their separate continuous metrics. This Team snapshot is
99 original + 5 repaired, not a clean new full study.

Formal output: `outputs/kramabench-final-104-v3-20261102-02/`. The prior
publication revision is retained. Current code uses run.py for native benchmark
launching, results.py for checked publication, cli_runtime.py for shared
container/artifact helpers and native_evidence.py for read-only readers. Fixed
six-task/dual-backend launchers, special first-task continuation branches and
duplicate historical report writers were archived and removed from active
source. README, benchmark documentation and tests were updated accordingly.
No new model/judge calls were made during merging or cleanup.

Final cleanup verification used the isolated server stage
`/tmp/mas-results-cleanup-source.4ECA4W`: 126 tests passed, all six retained CLI
entry-point help checks passed, and git diff --check passed locally. Source
archives and frozen experiment stages were not changed. The publisher verified
208 selected rows, 104 unique task IDs per backend and exactly five Team
replacements. Diagnostic/superseded expenditure is retained separately: 105
linked Single solver attempts and 109 Team attempts have visible-message cost
estimates, rather than pretending only the selected artifacts were paid for.

Native contexts, workers, prompts, compaction and provider behavior differ
between CLIs. Neither strict information isolation, a hard shared team budget,
exact per-request failed-call accounting nor causal architecture superiority is
claimed. Semantic judging covers the 20 text answers, not additional official
pipeline/subtask evaluation. Any future rerun needs fresh authorization.

## Primary References

- [Official Agent Teams documentation](https://code.claude.com/docs/en/agent-teams)
- [v2.1.178 protocol change](https://github.com/anthropics/claude-code/releases/tag/v2.1.178)
- [v2.1.225 release](https://github.com/anthropics/claude-code/releases/tag/v2.1.225)
- [v2.1.232 fork changes](https://github.com/anthropics/claude-code/releases/tag/v2.1.232)
- [Reported lifetime/activity ambiguity in native hooks](https://github.com/anthropics/claude-code/issues/85955)
