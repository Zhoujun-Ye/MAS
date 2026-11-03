# Historical Evidence

## Local Organization Cleanup (2026-11-03)

Completed study documents now live in [history/](history/README.md). Active
instructions, reusable prompts, analysis tools and regression tests are retained.

Local superseded `outputs/current/comparison/`, `comparison-3way/`, and
`reports/subagents-interim-20261103-01/` and
`reports/final-three-way-20261103-01/` were first relocated to a local archive,
then their local copies were deleted with the user's explicit approval after
confirming the four-way publication supersedes these summaries. The latest
four-way publication, current run copies and final audit/pilot reports remain
in `outputs/current/`. Server evidence and historical source snapshots are
untouched; this cleanup does not re-evaluate results.

Disposable `.cache/current-results-transfer/`, Python bytecode caches and
`.DS_Store` files are removed locally. Native CLI tools, source snapshots,
credentials, environments, prepared inputs and server files are untouched.

## README And Source Cleanup (2026-11-03)

Pre-cleanup local source, including the uncommitted delegation audit, is retained
in `archives/readme-cleanup-20261103/local-source-before.tgz`. No credentials,
environments, outputs, assets or upstream checkouts are included.

The dated `docs/native-cli-audit-20261102.md` and obsolete v177 pilot description
were removed from active documentation; their full text remains in this snapshot
and Git. Current CLI contracts and benchmark instructions stay in
`cli-adapters.md` and `kramabench.md`. The independent uncommitted delegation
audit is preserved. The unused legacy `llm_inputs` helper was removed; historical
run reading, validation, cache/statistics utilities and active reproduction tools
remain supported. No server source cleanup, deployment or paid call is implied.

The completed server `outputs/current/comparison-4way/` publication was copied
locally and summarized in README without changing source runs or grades.

## Claude Single Addition (2026-11-03)

Before adding the fourth adapter and sharing print-only transport helpers,
overlapping local source is retained at
`archives/claude-single-agent-20261103/local-source-before.tgz`.
Existing raw runs, frozen source stages and completed three-way comparisons
remain unchanged. The new study gets a separate namespace under `outputs/current/`.

## Current Results Retention (2026-11-02)

At the user's request, `outputs/` now exposes only `current/`. Its
`comparison/` contains the final matched Single 104 / Agent Team 104 publication,
and server `evidence/` retains copies of those exact 208 selected attempts.
Submission and native report hashes are checked during copying. The Team
condition is still 99 original + 5 repaired attempts, not a clean full rerun.

All previous output namespaces, including failed/superseded attempts, billing
receipts and historical CooperBench evidence, are moved without permanent deletion
to server `archives/output-cleanup-20261102/`. Historical `outputs/NAME` references
below now resolve to that archive's `NAME`. `relocation.json` records the map.
Frozen native logs are not rewritten. The derived current publication records
both original execution roots and archive locations. Local output copies are
likewise archived; full raw evidence stays on the server.

Before the adapter rename/addition, overlapping local source was preserved in
`archives/claude-subagents-20261102/local-source-before.tgz`.
The active Claude Team adapter is now `harness/claude_code_agent_team/`; the
separate native print-mode adapter is `harness/claude_code_subagents/`.

## CLI Results Cleanup (2026-11-02)

Overlapping uncommitted source before the latest cleanup is retained locally as
`archives/cli-results-cleanup-20261102/local-source-before.tgz`, SHA-256
`677e7ae4770c93d52f8efecf4367fec06dc173823a09d250e04a0ef73b2de637`.
No credentials, environments, checkouts, assets or outputs are in this snapshot.

Retired active entry points: cli_pilot.py, cli_batch.py, cli_rerun.py,
cli_report.py and cli_full_report.py under scripts/kramabench. The one-off
six-task, dual-backend and first-task continuation/replacement launch policies
remain reproducible from that archive and each experiment's frozen source.tgz.
They are not active launch defaults. Useful container/evidence helpers moved
to cli_runtime.py, native_evidence.py and run.py; results.py publishes corrected
snapshots without modifying raw experiments. Obsolete launcher/report fixtures
were replaced by current admission, scoring/publication and provenance tests.

The final published snapshot is
`outputs/kramabench-final-104-v3-20261102-02/`: fresh strict Single 104 and
Claude 99 original + 5 repaired. Revision 01 is retained; revision 02 adds the
linked Single diagnostic expenditure ledger, without changing selected answers.
All failed/superseded attempts and original scoring receipts remain intact.
Local active code was cleaned and checked in a fresh server source stage;
production/frozen server source and experiment directories were not pruned.

## CooperBench Retirement

CooperBench was retired from active source on 2026-11-01 at the user's request.
Results remain at `/home/zhoujunye/MAS-information/outputs/cooperbench/` on the server.
Observed directories: `team20-20261030-01`, `team20-20261030-parallel-01`,
`lite100-20261030-03`, `lite100-20261030-04`, `repair-20261031-01`, `lite100-current`.
This is an inventory, not a re-evaluation or endorsement of historical scores.

Archive: `/home/zhoujunye/MAS-information/archives/leader-subagent-20261101/`.

- `server-source-before.tgz`: pre-cleanup server source, configs, docs and tests.
- `local-source-before.tgz`: local equivalent, including pre-existing README/AGENTS
  edits. No credentials, outputs, environments, assets or checkouts are included.
- `results-before.sha256`: per-file checksums before refactoring.
- `removed-source.txt`: exact retired tracked paths used for scoped cleanup.

Results are not moved or rewritten. At retirement, historical Docker images,
containers, ignored upstream checkouts and prepared assets were not pruned; they
can be needed for audit and overlap shared resources. The subsequently authorized
CooperBench image deletion is recorded below. No active launcher references them. Reproduce old
studies from archived source, not from the new runtime. Retained run readers
describe historical schemas, not the new study's criteria.

Local follow-up cleanup removed `benchmarks/cooperbench/upstream/` (a clean
checkout) and `.cache/cooperbench-images/` (approximately 59 GiB of downloaded
image caches). The retention statement above describes server resources at
retirement, subject to the image-cleanup exception below; local historical reports
and unrelated caches remain untouched.

## CooperBench Image Cleanup

On 2026-11-02, the user explicitly authorized deleting server CooperBench images.
The scoped cleanup removed 45 unused images and 47 tags under
`mas-information/cooperbench-prepared`, `akhatua/cooperbench-*`, and the
`docker.1ms.run/akhatua/cooperbench-*` mirror. No running or stopped container
referenced these images. Each exact tag and its container references were checked
again before removal; no force, global prune, parent prune, or build-cache cleanup
was used.

All 10 non-CooperBench images and all 83 existing containers were retained.
Docker-reported image size changed from 91.91 GB to 7.668 GB; these are Docker's
aggregate image statistics, not a measurement of physical blocks reclaimed.
KramaBench, `/home/zhoujunye/agent-team`, historical results, archives, checkouts
and prepared asset files were not modified by this cleanup. Reproducing retired
CooperBench runs now requires recovering their deleted images separately.

The before/after inventories, deletion plan, per-tag operation log, and summary
are retained at
`/home/zhoujunye/MAS-information/outputs/cooperbench-image-cleanup-20261102-01/`.

Analysis follow-up retired `analysis/criteria.py` (old P1-P4 thresholds),
`analysis/loss_judge.py` (unused model-judge helper), and `analysis/information.py`
(retired peer-team transport/evidence schema), together with `scripts/feedback.py`
and their tests. Historical implementations remain in the source archives above.
`analysis/cache.py` and `analysis/stats.py` remain reusable utilities;
`analysis/runs.py` and `scripts/analyze.py` remain read-only historical report tools
for scheduler-based manifests, not Leader-Subagent session outputs. At the user's
request, this cleanup is also synchronized to server source using explicit paths;
archives and experiment evidence remain untouched.

## Foreground Baseline

The retired foreground protocol and its baseline-provenance discussion are
preserved at commit `f9c9a4a` in `docs/leader-subagent.md` and in the source
archives above. That document was removed from the active tree because its
delegation API, mode flags, scheduling and inline-submission instructions no
longer describe the then-implemented Team runtime. That runtime was itself
retired by the CLI reset below. Superseded tracked audit documents remain in Git rather than
the active documentation tree; retained server evidence is listed separately.

The subsequent source cleanup removed the unreferenced YAML configuration loader
and its PyYAML dependency, unused imports, and unreachable child assertions in
Single-only tests. Active regression scenarios and historical diagnostics remain.
Server verification after this cleanup: 218 passed, 5 skipped (existing-image
Docker opt-ins were not enabled). No paid calls, installs or image operations.

## Refactor Verification

Server regression: 35 scripted/mock tests passed. The foreground delegation demo
at `outputs/subagent-demo-20261101-01/` completed with zero trace integrity errors.
All files in `results-before.sha256` passed SHA-256 verification after cleanup.
No paid model calls, Docker provisioning or benchmark re-evaluation was performed.

After the analysis cleanup was synchronized, the server regression passed all
92 tests. Historical results again passed `results-before.sha256` verification.
No paid calls or benchmark re-evaluation were performed for this follow-up.

## Authorized Pilot Cleanup

On 2026-11-02 the user explicitly requested deletion of only the latest four
six-question pilots, including their matching local copies, adjacent logs and
source snapshots:

- `outputs/kramabench-engineering6-20261101-01`
- `outputs/kramabench-engineering6-rerun-20261101-01`
- `outputs/kramabench-engineering6-fixed-20261102-01`
- `outputs/kramabench-checkpoints6-20261102-01`

This is a user-authorized retention exception, not filtering failed attempts to
improve a score. Other experiment outputs, preparation records, input checkouts,
assets, images, caches and `archives/leader-subagent-20261101` are outside the
deletion scope. The unrelated `/home/zhoujunye/agent-team` is never touched.
Dated pilot reports were removed from active docs along with obsolete protocol
audits. Runtime documentation mentioned here describes the pre-reset source. The
single-question archeology diagnostic and its dedicated numerical tests were
retired; generic transport, submission, scheduling and budget regressions remain.

The cleanup does not authorize any new paid benchmark, judge or retry. A full
104-task preflight is read-only with respect to data and uses no paid calls.

## External CLI Reset (2026-11-02)

At the user's request, the custom harness, domain-tool loop, provider clients,
team scheduler/mailboxes, role catalogs, semantic-judge client and their launchers,
documentation and tests were removed from active local source. Only external
Deep Agents Code and Claude Code Agent Teams CLI adaptation remains in `harness/`.
Current contracts and limitations are in [cli-adapters.md](cli-adapters.md).

Before deletion, the complete local source tree, including the pre-existing
uncommitted Claude CLI/relay/transport work, pilot/batch rewrites, legacy launcher
copies and test/doc edits, was preserved at:

`archives/cli-reset-20261102/local-source-before.tgz`

SHA-256: `ca05694ed7efb629f67be98b1fb185ba2f14cf3859b6f976e31381a0ae3f67ac`.
Base Git revision: `c966f0e96a5df787264eb72d8c85f1d2f099cc8e`.
This ignored local snapshot contains source, example config, docs and tests only;
it excludes real credentials, environments, outputs, assets, checkouts and caches.
Tracked historical versions also remain in Git. `analysis/legacy_trace.py` is
read-only compatibility code for old evidence, not a surviving agent runtime.

Historical experiment evidence and preparation resources were not removed or
rewritten. No production server source was synchronized or cleaned by this reset.
Server tests use a fresh temporary source directory and the existing project
Python environment. No paid run, CLI install/upgrade, environment provisioning,
image operation or deployment is authorized by this refactor.
