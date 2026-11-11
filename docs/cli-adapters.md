# Claude Code CLI Adapters

## Active Runtime

The externally installed Claude runtime is pinned to **Claude Code 2.1.286**.
Codex adapters and launch choices were retired at the user's request.

| Condition | Adapter | Native Transport |
| --- | --- | --- |
| Strict Single | `ClaudeCodeSingleAgentCLI` | print, delegation tools removed/denied |
| Subagents | `ClaudeCodeSubagentsCLI` | print, native Agent with Teams disabled |

Shared code in `_claude_cli.py`, `_claude_hooks.py` and `_cli.py` handles native
arguments, observations, version preflight, stdin, process lifetime and raw logs.
No semantic provider relay, model loop, SDK import, custom scheduler or vendored runtime
exists. DataClaw/HDR use a host credential gateway that preserves native wire
protocols without model orchestration. Deep Agents launchers, options, mounts and executable requirements are
removed. Historical comparisons and retired checkpoint readers have been removed. See [retention](archive.md).

## Strict Single

The built-in `--tools` surface excludes native delegation. `--disallowedTools`
also denies Agent/Task aliases, peer messaging, workflows and scheduled agents.
Skills and ambient MCP/settings are isolated. An opt-in native PreToolUse policy
denies delegation attempts; unexpected SubagentStart is a condition violation.
Other modes use record-only hooks, never permission grants.

Admission requires native start/end and policy observations, zero workers,
zero executed delegation and zero worker transcript evidence. Missing evidence
is not success. CLI tool denial is not an adversarial shell sandbox. Live benchmark
containers use network=none and the host credential gateway; a same-UID process
holding its run token is not authenticated as the native model process.

## Native Subagents

Uses `--print --verbose --output-format stream-json` and
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0` in environment and settings. It does not
install a roster by default. Native background delegation is supported; print
transport does **not** imply synchronous subagents. Native background agents notify
the lead on completion; admission and retained transcripts establish only the
observed structural behavior, not substantive contribution.

The Subagents baseline uses current orchestrator-worker lead prompt, frozen by the user
on 2026-11-04 ([prompt versions](studies/README.md)). The lead plans, splits the
work between itself and subagents (at least one, scaled to complexity) and synthesizes. It specifies
no specialist roster, judge role or cost-reduction policy.

For inspection, `scripts/common/prompts/structured_subagents.py` holds this unchanged
default as `PROMPT`. FULL/OBS, their Native alternative prompt and prompt-only
ablations were retired on 2026-11-10. Single and Structured remain the defaults.
The explicitly approved Krama Native study uses `native_subagents.py`: only the
Structured opening paragraph plus "Always deploy at least one subagent."
It uses this same adapter and audit, not a third runtime or unprompted CLI policy.
The Python
files are not raw-text inputs for `--organization-prompt`.

Native facts this relies on, observed on 2.1.286:
- There is no TaskOutput tool. Background agents notify the lead on completion.
- In print mode the run stays open after the lead ends its turn while a background
  agent still runs. The lead is resumed on completion, and stdout then holds one
  result event per resumed segment; the adapter keeps the last one.
- Isolated settings (`--setting-sources ""`) do not auto-load workspace
  `CLAUDE.md` or `AGENTS.md` for any agent. Workers learn task rules only from the
  lead's brief and from tool output. Admission requires observed native delegation and
completion; it does not establish semantic contribution. This is a prompted condition,
not an entirely unprompted Claude Code run.
Benchmark access and output requirements remain explicit. Only the current
lead prompt remains the default; no backup prompt or specialist-judge study is active.

Custom research organizations can define native subagent prompts, descriptions,
tools, permission policies and handoff requirements without replacing Claude's
contexts/scheduler. A new organization is a new study condition; preserve the
baseline and freeze each prompt/configuration separately. See the official
[subagent guide](https://code.claude.com/docs/en/sub-agents),
[CLI options](https://code.claude.com/docs/en/cli-reference) and
[hooks](https://code.claude.com/docs/en/hooks).

Retired Agent Teams adapters and historical readers are not available. Current
native proofs are regenerated offline and bound to the active configuration;
see [active infra](studies/evidence-infra.md). No native Team runtime is active.

## Execution And Evidence

All adapters expose `command(model, ...)` and `run(..., execute=False)`.
Default planning starts no subprocess and writes no output. Execution needs an
existing workspace, a fresh non-overlapping output directory and run-specific
authorization. Native retries are requested as zero; adapter retries are zero.
Automatic updates are disabled. Exact native version stdout is retained, but
the executable hash is not a complete dependency/environment lock.

Retain `launch.json`, normalized/hash-bound `prompt.txt`, `cli-version.json`, raw
stdout/stderr and `result.json`, including failures. Only fixed non-secret launch
environment overrides are recorded. Native logs can contain private data.
Timeout/interrupt cleanup terminates the POSIX process group, not arbitrary
detached services. CLI exit, final text and hooks do not establish correctness,
workspace quiescence or complete member accounting. Missing costs are unknown.

Research orchestration and benchmark evaluation remain outside `harness/`.
Offline stub tests do not establish real-model quality or provider retry behavior.
Tests run on the server in fresh source stages; no production deployment or paid
run is implied. See [additional benchmark adapters](research-benchmarks.md).
