# Team Runtime Audit And One-Task Pilot

2026-11-01. Scope: snapshot foreground subagents, replace the active engine with
Leader-led Team, audit on the project server, and run one authorized paid attempt.

## Findings And Disposition

1. **Final code was not the executed Worker artifact. Fixed in v1.1, offline verified.**
   The paid v1 Leader submitted 9,662 characters of condensed code instead of the
   23,334-character Worker file. Both byte hashes and Python ASTs differ; this is
   not just whitespace. The original run remains unchanged and is not labelled
   as a verified execution of the submitted script. Team submit now checks the
   code's UTF-8 SHA-256 against regular files in the frozen workspace snapshot.
   Missing/symlink snapshots and rewritten code fail closed; no-code submissions
   require null answer and explicit unfinished work. This guard proves artifact
   identity, not correctness or trusted execution. Single's inline-code contract
   is unchanged and this mode difference is recorded in the manifest.

2. **A peer message was queued but never exposed. Receipt clarity fixed; scheduling policy retained.**
   Worker-2 returned at 206.839 seconds. Worker-1 sent it an info message at
   213.981 seconds, asking it to flag discrepancies, but left `needs_reply=false`.
   Under the frozen policy ordinary info does not wake an idle member. The message
   remained queued until closure and was explicitly recorded as undelivered.
   Thus this run has one peer route and zero peer model exposures, not a successful
   peer exchange. V1.1 acknowledgements now report recipient state, no-idle-wakeup
   and how to request a response. No semantic intent is inferred by the runtime.

3. **Final evidence overstates independent checking. Unfixed model behavior.**
   The Leader's submission attributes the complete region-count and source checks
   to two independent agents. Worker-2 explicitly reports that only rows 1-300
   were tallied for per-region counts; later rows were checked for distinct-value
   presence only. It also leaves global climate coverage checks unverified.
   Agreement on some cells does not independently verify every aggregate.
   A runtime must preserve this discrepancy, not silently promote the final prose
   to an evaluator verdict or automatically rewrite it.

4. **Capability selection and coordination remain inefficient or at least costly.**
   The read-only explorer was assigned whole-file aggregate checks, consumed all
   24 domain calls on paging, and still returned unchecked coverage. Its handoff
   incorrectly said the domain ceiling prevented peer messaging; no send was
   attempted by that member, and messaging uses a separate quota. V1.1 clarifies
   the distinction. The Leader used 16/46 model calls and its largest prompt was
   49,203 tokens. Work briefs overlap discovery/checking; whether this is useful
   independent checking or redundant work needs broader, controlled evidence.

5. **Six rejected control/tool attempts were recoverable, not infrastructure failure.**
   Empty list path, two absolute/prose write scopes, a 180-second wait above the
   120-second maximum, and two mixed-batch task updates were refused. The model
   corrected them. They remain in the error history; the run's `infra_affected`
   remains false. V1.1 improves field and sole-call descriptions without relaxing
   validation or deleting these failures.

## Source And Protocol

- Foreground snapshot: commit `f9c9a4a`, not pushed. The original 207 server tests
  passed before replacement. No active `harness/subagents.py` or foreground demo
  remains; obsolete foreground-only tests were replaced, not maintained as another
  engine. Old `mas`/`delegated` modes fail explicitly. Single remains available.
- Active protocol: `docs/agent-team-design.md`; fixed worker/explorer grants,
  Leader-only task authority, persistent local histories, direct mail, versioned
  handoffs, bounded asynchronous turns and open/draining/frozen submission.
- Paid v1 source digest: `ddf28c92a931e5da`.
- Paid source/tests archive SHA-256:
  `2765c86aecd3f4d6a75fd53a3315534341d9cc4e97682716d84d5c1cd3e78107`.
- Current v1.1 source digest: `ef1eab61e09a7193`. Its post-pilot binding and receipt
  changes were tested offline only; **there was no second paid attempt**.
- New source remains uncommitted after the requested foreground snapshot.

The pre-run audit also repaired shared final-call reservation races, stop-time
missing tool replies, terminal activation cleanup, stale task/owner updates, and
key/balance preflight that could previously continue despite a known fatal error.
Provider failures, tool failures, limits and historical recoverable errors are
separate from lifecycle state and infrastructure impact.

## Server Verification

Tests ran only in `/home/zhoujunye/MAS-information`, after checking process/CPU
ownership. No environment install, image build, unrelated project change or paid
judge was performed.

- Paid v1 preflight: **136 passed**; its 20 Team protocol cases passed 10 repeated
  runs (200 case executions), including concurrent writes during drain/fatal stop.
- Final v1.1 regression: **144 passed**. Includes exact artifact binding,
  unfinished/missing/symlink/empty-file rejection, idle send acknowledgements and
  detection of unanswered tool calls at the end of a transcript.
- Independent Single/Team synthetic adapter fixtures passed before and after the
  audit; no network/model/evaluator calls. Both return the fixture average 4.
- Final XML: `outputs/team-design-audit-20261101-01/team-v1.1-final.xml`.
- Post-audit fixture: `outputs/team-fixture-postaudit-20261101-01`.
- Local static check: `git diff --check` clean. No local runtime/test claim.

## Authorized Paid Attempt

Evidence directory, mirrored locally from the server:
`outputs/kramabench-paid-team-v1-20261101-01`.

One `archeology-hard-1` Team attempt; no Single arm, retry, paid judge or additional
task. Model: deepseek-flash, thinking enabled, high effort, max output 16,384,
context 1,000,000, retries 0, request timeout 180 seconds. Shared ceilings:
64 model calls, 120 domain calls, 1800 execution seconds, 120 audit seconds;
8 identities, 16 activations, 4 parallel Workers, 128 explicit messages/reports,
8192 UTF-8 bytes per explicit message.

Existing image ID:
`sha256:e853321226dc4653164fff8f7e723a86df1a9e2aca282e649dfe2a9a1b144f6c`.
Upstream: `b2e0d77540263f8b6119f977fe79a8c4386b5a02`.
Only the run-owned container was created and removed; cleanup return code 0.
Input data was read-only, network disabled, workspace fresh, 2 CPUs / 4 GiB.

| Measurement | Observed |
|---|---:|
| Model requests / successes / provider failures | 46 / 46 / 0 |
| Domain calls: Leader / worker / explorer | 6 / 17 / 24 |
| Total domain calls | 47 |
| Runtime | 272.577 seconds |
| Prompt / completion tokens | 939,591 / 66,648 |
| Token-weighted input cache reuse | 88.440% |
| Largest prompt | 49,203 tokens |
| Estimated token cost | USD 0.058773978 |
| Trace integrity errors / infrastructure affected | 0 / false |
| Explicit messages / peer routes / peer exposures | 2 / 1 / 0 |

| Role | Calls | Prompt tokens | Completion tokens | Max prompt | Weighted cache reuse |
|---|---:|---:|---:|---:|---:|
| Leader | 16 | 355,080 | 15,650 | 49,203 | 88.967% |
| Worker | 20 | 402,859 | 22,527 | 38,297 | 87.503% |
| Explorer | 10 | 181,652 | 28,471 | 37,262 | 89.490% |

Cost uses the frozen [official pricing table](https://api-docs.deepseek.com/quick_start/pricing/),
checked 2026-11-01. Account balance snapshots exist, but a shared-account delta is
not attributable actual run cost. No attributable actual charge is established.

Submitted answer: **8347.1887**. Pinned numeric target: **8577.5298**. Raw numeric
grade: **0**, retained unchanged. The alternative interval mean reported by the
team is 8477.8648. The previously investigated reference/estimand disagreement is
unresolved; this score alone does not identify a scheduling or communication cause.

## Exact Evidence Pointers

- `team/manifest.json`, `preflight-manifest.json`: frozen source/model/grants/inputs.
- `team/report.json`, `team/cost.json`: usage, cache, integrity and cost estimate.
- `team/outcome.json`: full error history, both handoffs and accepted task states.
- `team/trace.jsonl`: explorer handoff t=270; peer send t=289; producer handoff
  t=311; frozen barrier t=360; session end t=371. All are run-local event indices.
- `team/submission.json`, `team/grade.json`: exact answer/code and bound numeric score.
- `workspaces/team/worker/pipeline.py`, `pipeline_run.log`: produced script and
  recorded execution evidence. Fourteen terminal calls returned exit code 0.
- Submitted code SHA-256:
  `35fe41dc054078b132c78582641edc957acf223595d294c42e9195536645d8fb`.
- Worker artifact SHA-256:
  `285c9bc27d2cf0baf8aa84f9274f61310be16d0f7602c01292340e8dbd430928`.
- `container-cleanup.json`, `source-and-tests.tar.gz`: cleanup and exact paid source.

No trusted re-execution of the submitted pipeline occurred. The completed paid v1
attempt is evidence about protocol behavior and failure modes, not a clean pass
for final code provenance, a held-out benchmark result, or a measured MAS gain.
Next experiments should freeze v1.1, distinguish information from response requests,
measure Leader overhead and coverage inflation, and vary communication on the same
scheduler rather than treating the retired foreground engine as a routing ablation.
