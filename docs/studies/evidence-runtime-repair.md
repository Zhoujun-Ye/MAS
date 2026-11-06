# MAS Evidence Runtime Repair

2026-11-05. Diagnose and repair the completed Validation20 pair without paid
solver/judge calls. Original artifacts, degradation markers and scores remain
unchanged. Frozen baseline prompts/adapters were not modified.

## Delegation Root Cause

Among 114 newly started attempts, 36 Observation and 7 Full runs recorded no
SubagentStart. Full includes one timeout plus six normal-but-unverified exits.
All 43 native init records advertised Task/Agent and defined evidence-worker;
all 43 had zero delegation tool calls. Thus this was not a tool-permission
rejection or blanket MCP configuration failure. The native pin exposes Task.

Our opt-in lead policy allowed opting out: Full said to delegate when useful;
Observation primarily described raw retrieval and appended a weaker when-useful
delegation sentence. Neither required an executed MAS. They did not share the
frozen baseline's orchestration policy. Treating every attempt as an executed
multi-agent condition was unjustified. This policy defect is confirmed; its
causal effect on a stochastic model's rate is not established by inspection.

Both evidence modes now prepend the exact same COLLABORATION_PROMPT: delegate
at least one meaningful analysis/check through the native tool, assess its results,
and do not finish alone. Decomposition/count remain task-dependent; no fixed
specialist roster, dummy work, scheduler, retry loop or automatic submission.
Explicitly denying Task/Agent now fails configuration rather than silently
launching an agentless MAS. Baseline branches remain unchanged.

Audits additionally require a completed native worker, its successful tool
observation, and a lead read of that observation. Root-only MCP reads cannot mark
the condition verified. Method coverage is recorded separately. These are
structural/data-handoff checks, not proof of contribution, comprehension or
OS-authenticated identity. Real-model compliance after this change is unverified.

Diagnosis: `/home/zhoujunye/mas-data/receipts/evidence-delegation-diagnosis-20261105/diagnosis.json`.

## Capture Root Cause

Offline replay reproduced all 13 errors across nine affected profiles: Full
seven profiles/eight errors; Observation two profiles/five errors. Every error
was PostToolUse SendMessage rejected as Conflicting tool call identity.

Native 2.1.286 PreToolUse includes canonical to/summary/message plus compatibility
type/recipient/content fields. PostToolUse removes the compatibility fields while
retaining all canonical values unchanged. We incorrectly required identical raw
input objects at both phases. This is not a diagnosed database-lock failure.

The fix recognizes only this exact field-set transformation with equal canonical
values. input_ref retains the raw Pre snapshot; terminal_input_ref independently
retains the raw Post snapshot; input_transform explains their difference. No raw
fields are normalized away or silently overwritten. Reverse commit ordering and
concurrent duplicate delivery are tested. Changed canonical values, unexpected
fields, other tools, or conflicting terminal results still fail. A terminal
failure with missing output can no longer be silently overwritten either.

Degradation diagnostics now retain safe error codes, event/tool names and an event
hash, never arguments/message contents. Invalid/nonfinite events still yield a
permission-neutral reply. Existing native evidence remains authoritative history.

`scripts/probes/replay_observations.py` replays affected event logs into temporary
stores, without executing captured tools or modifying original records. Fixed
replay: **9/9 profiles passed, 13 transitions reconciled, zero capture errors,
all integrity checks ok**. No private HDR payload is published.
Proof: `/home/zhoujunye/mas-data/receipts/evidence-capture-replay-fixed-20261105/proof.json`.

## Grading Eligibility

The pending Krama judge was skipped because native_condition_unverified was
excluded from the grading gate despite a retained evaluable answer. The shared
grader now separates organizational validity from answer eligibility. Authorized
pending semantic grades can use that status; judge_once still validates the
artifact before dispatch. Tests use mocked judges. The existing pending result
was not graded, and no old score changed.

## Verification

Source stage: `/home/zhoujunye/mas-stages/20261105-evidence-engineering-audit-fix`.
Server regression: **495 passed in 13.85s**. Tests cover shared delegation policy,
agentless audit rejection, input pruning, genuine conflicts, ordering/concurrency,
safe diagnostics, terminal immutability and grading scope.
After checking that the six overlapping active-server modules matched the prior
frozen source, a source-only snapshot was saved and the repair was deployed to
`/home/zhoujunye/mas`. The active repository also passed **495 tests in 15.15s**.
No job was launched by this deployment. Source snapshot:
`/home/zhoujunye/mas-data/receipts/evidence-engineering-repair-deploy-20261105/pre-fix-source.tar.gz`.

Native Claude 2.1.286 fake-provider probes passed for both modes, including real
worker lifecycle/tool observations and both-role MCP reads; Full also exercised
candidate/evidence/selection handoff. No degraded capture; both probe containers
removed. Receipts:
`/home/zhoujunye/mas-data/receipts/evidence-engineering-audit-fix-native-20261105`.

No paid solver, paid judge, installation or environment change. Updated prompt
and audit contracts have new configuration/proof hashes. Old source stages and
experiment results are unchanged; these repairs do not retroactively validate
the prior comparison or demonstrate accuracy gains.
