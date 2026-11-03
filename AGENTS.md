# Project Instructions

The user reset the runtime on 2026-11-02. The active harness contains four
adapters for two externally installed CLIs: Deep Agents Single, Claude Code
Agent Teams, Claude Code Subagents and Claude Code Single Agent. Research orchestration remains separate. Do not
restore the retired custom Team runtime, provider relay, Single/Team launchers,
coordinator/full modes, capability catalogs, or custom scheduling semantics.

## Ownership And Scope

- `harness/deepagents/`: Deep Agents Code (`dcode`) arguments and CLI adaptation.
- `harness/claude_code_agent_team/`: interactive native Claude Code Agent Teams adaptation.
- `harness/claude_code_subagents/`: print-mode ordinary native Claude subagents, with Teams disabled.
- `harness/claude_code_single_agent/`: print-mode strict Single, with native delegation tools removed and denied.
- `harness/_claude_cli.py` and `_claude_hooks.py`: shared native arguments/observations and opt-in Single permission policy.
- `harness/_cli.py`: CLI preflight, process lifetime, stdin and raw evidence only.
- Agent contexts, tools, communication and scheduling belong to the external CLI.
- Do not clone or vendor either upstream runtime, or import its SDK here.
- Do not silently equate Deep Agents subagents with Claude Code Agent Teams.
- Do not turn the Team adapter into print mode or label ordinary subagents as a native Agent Team.
- For the active KramaBench comparison, Deep Agents and Claude Single are strict single-agent
  baselines. Use explicit native single policies, not prompt-only discouragement
  or default dcode delegation. Earlier runs with subagents are not single baselines.
- Do not impose a new roster, decomposition policy, benchmark protocol or solver
  prompt as part of CLI adaptation.
- `benchmarks/` owns task data and evaluation, independently of the adapters.
- `analysis/` retains generic utilities and read-only historical-schema readers.
- CooperBench is retired; preserve its evidence and retention exceptions in
  `docs/archive.md`, not an active dependency.
- Preserve unrelated changes and historical evidence. Snapshot overlapping
  uncommitted source before removing it; Git alone does not preserve that work.

See `docs/cli-adapters.md` for pinned versions, references and limitations.

## Server Operations

- Local `/Users/zhoujun/Desktop/MAS-information`; server
  `zhoujunye@10.123.4.30:22`, `/home/zhoujunye/MAS-information`.
- Run tests and experiments on the server, not locally. Inspect live processes and
  CPU ownership first. Never modify `/home/zhoujunye/agent-team` or its resources.
- Use `scripts/server/sync.sh` for scoped source only. Never sync credentials,
  environments, caches, checkouts, assets, archives or outputs; never `--delete`.
- A sync does not remove retired files. Remote source cleanup or deployment needs
  explicit authorization; local cleanup is not automatic remote deployment.
- `.env` stays ignored and mode 0600. Never print or commit credentials.
- Installs use the Tsinghua PyPI mirror. Do not provision environments, CLIs,
  Docker or cloud resources implicitly. Preserve historical images/assets and runs.
- Deploy, launch jobs and clean server files only within user authorization.

## Runtime And Evidence

- No paid agents, judges, simulators or retries without run-specific authorization
  and size. Offline tests use fake CLIs and must not invoke a paid provider.
- Planning is the default; execution requires an explicit `execute=True` or
  `--execute` plus run-specific user authorization.
- Never automatically bypass CLI permissions. A shell allow-list is neither a
  sandbox nor a guarantee of read-only behavior.
- Use exact CLI pins and disable automatic updates. Record native version output
  and raw stdout/stderr; a launcher hash is not a dependency/environment lock.
- Request retries=0 in native CLIs and do not retry in the adapter. Provider
  retry semantics and fatal key/balance handling need native-runtime validation
  before paid studies; do not recreate a provider client to claim enforcement.
- Keep failed attempts. Native context/output exhaustion is incomplete work.
- Lifecycle status, CLI final text and enabled team flags do not establish
  correctness, actual team creation, member shutdown or workspace quiescence.
- No old frozen-artifact, shared-budget, bounded-team or append-only-message
  guarantee carries over automatically to the native CLIs.
- New studies must freeze settings and bind evaluation to exact artifacts.
  Historical results, static inspection and fake-CLI tests do not establish gains.
- Report prompt lengths, token-weighted cache reuse by role, estimated/actual
  costs and unverified behavior when native evidence makes them available.
  Missing accounting is unknown, never zero.
