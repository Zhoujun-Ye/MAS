# Project Instructions

Target a benchmark-independent Leader-led Agent Team: the Leader assigns tasks
and maintains team state, Workers communicate directly, key progress/risks/results
reach the Leader, and communication is retained. See `docs/agent-team-design.md`
for the implemented protocol. Foreground subagents were archived at commit
`f9c9a4a` and removed from active source; old `mas`/`delegated` flags are rejected.
Use fixed capability templates and task-adaptive membership/delegation, not generated
role permissions, fixed peer teams, or RSI. Independent contexts are context management,
not strict information isolation. Shared workspaces are allowed through tool grants.
Use bounded parallel execution. No fork or automatic full-task injection: initial
Worker contexts contain the leader's local brief/context and fixed shared project
instructions. Subsequent peer messages are explicit, logged context additions.
All messages may wake idle members with unchanged template grants; there is no
read-only-after-wakeup variant. The main Team baseline defaults to a coordinator
Leader with no domain tools, including readers. Full Leader grants require an
explicit comparison setting. Both Leader conditions prioritize coordination and
meaningful decomposition; full permits domain work, coordinator delegates it all.
Checks and repairs must precede closure. The leader-pair entry point selects these
two Team conditions explicitly; it does not authorize paid execution.
The Leader actively seeks meaningful multi-member decomposition with complementary
specialists, distinct deliverables and explicit interfaces, not a default single
end-to-end owner. Do not force duplicate work or a fixed roster to meet a quota.
Only explicit completed claims on normally returned assignments release dependencies,
without mandatory acceptance. Plain final text is an unclaimed handoff, not verified
completion. Dependency-waiting members may process messages with unchanged grants;
this does not start or complete their pending assignments. Single and
Team submit artifact paths under a common frozen-hash/selected-file export contract,
not inline model-copied code. Freeze records metadata/hashes; only the selected path
is exported at submit. Closing exposes the frozen file inventory, not file content. Put generic
domain checklists in shared project instructions, not a root-only prompt.
Runtime status describes lifecycle, never correctness or the absence of past errors.
Keep error history and infra_affected separate; recoverable errors must not poison
later reports. Shared-workspace audit intervals are not exclusive write attribution.

## Ownership

- `harness/team.py`: task authority, persistent members, scheduling and final drain.
- `harness/messaging.py`: direct mail, request linkage and delivery receipts.
- `harness/session.py`: shared session evidence, audits and budgets.
- `harness/agent.py`: append-only context, validation and tool execution.
- `harness/llm.py`, `trace.py`, `accounting.py`, `runner.py`: shared infrastructure.
- Adapters supply domain tools/evaluation; orchestration belongs in `harness/`.
- `analysis/` retains cache/statistics utilities and historical run readers, not
  study-specific criteria or retired peer-team attribution tools.
- CooperBench is retired. Server evidence and source archives are documented in
  `docs/archive.md`; do not restore it as an active dependency.

## Server Operations

- Local `/Users/zhoujun/Desktop/MAS-information`; server
  `zhoujunye@10.123.4.30:22`, `/home/zhoujunye/MAS-information`.
- Run tests and experiments on the server, not locally. Inspect live processes and
  CPU ownership first. Never modify `/home/zhoujunye/agent-team` or its resources.
- Use `scripts/server/sync.sh` for scoped source only. Never sync credentials,
  environments, caches, checkouts, assets, archives or outputs; never `--delete`.
- `.env` stays ignored and mode 0600. Never print or commit credentials.
- Installs use the Tsinghua PyPI mirror. Do not provision environments, Docker or
  cloud resources implicitly. Preserve historical images/assets and immutable runs.
- Deploy, launch jobs and clean server files only within user authorization.

## Runtime And Evidence

- No paid agents, judges, simulators or retries without run-specific authorization
  and size. Offline tests use scripted clients; paid settings require retries=0.
- Templates and permissions are fixed per session. Children cannot grant tools to
  themselves. A shell grant is neither a read-only permission nor a security sandbox.
- Keep histories append-only and reasoning_content verbatim. Do not inject volatile
  timestamps or trace IDs into prompts. Resume retains child history and tool budget.
- Runtime owns scheduling, transport, permissions, budgets and lifecycle. Distinguish
  partial work, tool errors, provider errors and independently verified success.
- Key/balance errors stop further calls. Context/output exhaustion is incomplete
  work. Never omit failed attempts to improve scores; evidence is immutable.
- A final report is not an evaluator verdict. New studies must freeze settings and
  bind evaluation to exact artifacts. Historical results do not establish new gains.
- Report prompt lengths, token-weighted cache reuse by role, estimated/actual costs,
  and unverified behavior. Do not claim causality from implementation or smoke tests.
