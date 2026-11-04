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
removed. Historical comparisons and read-only checkpoint readers remain usable
without restoring its active runtime. See [retention](archive.md) and
[historical contracts](history/cli-adapters-through-deepagents-20261103.md).

## Strict Single

The built-in `--tools` surface excludes native delegation. `--disallowedTools`
also denies Agent/Task aliases, peer messaging, workflows and scheduled agents.
Skills and ambient MCP/settings are isolated. An opt-in native PreToolUse policy
denies delegation attempts; unexpected SubagentStart is a condition violation.
Other modes use record-only hooks, never permission grants.

Admission requires native start/end and policy observations, zero workers,
zero executed delegation and zero worker transcript evidence. Missing evidence
is not success. Shell/Python can access external services in a network-enabled
container, so this is not an adversarial sandbox; external agent/model calls are
also forbidden by the study instruction.

The existing installation passed a network-disabled denial probe with dummy
credentials: production tool restrictions and a deliberately relaxed diagnostic
surface separately rejected Agent and Task. Six loopback fake requests, zero
paid calls. Historical server receipt:
`archives/claude-single-agent-20261103/native-denial-01/proof.json`.

## Native Subagents

Uses `--print --verbose --output-format stream-json` and
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0` in environment and settings. It does not
install a roster by default. Native background delegation is supported; print
transport does **not** imply synchronous subagents. The retained scoped-judge
pilot's `archeology-easy-8` root transcript line 67 contains
`Agent(..., run_in_background=true)`.

The Subagents baseline uses orchestrator-worker lead prompt v4, adopted by the user
on 2026-11-04 ([prompt versions](studies/README.md)). The lead plans, splits the
work between itself and subagents (one by default) and synthesizes. It specifies
no specialist roster, judge role or cost-reduction policy.

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
Benchmark access and output requirements remain explicit. The bounded evidence-judge pilot is a separate
research intervention, only a signal of potential cost reduction, not a native
baseline result or a demonstrated general quality/cost improvement.

Custom research organizations can define native subagent prompts, descriptions,
tools, permission policies and handoff requirements without replacing Claude's
contexts/scheduler. A new organization is a new study condition; preserve the
baseline and freeze each prompt/configuration separately. See the official
[subagent guide](https://code.claude.com/docs/en/sub-agents),
[CLI options](https://code.claude.com/docs/en/cli-reference) and
[hooks](https://code.claude.com/docs/en/hooks).

Existing native wiring proof: `archives/claude-subagents-20261102/native-probe-01/proof.json`
on the server, one observed subagent start/stop, root end and no native Team,
four loopback fake requests, zero paid calls. Not benchmark quality evidence.

## Retired Agent Teams

The interactive Agent Teams adapter, launcher choice, and native probe were retired
on 2026-11-04. Historical results and evidence readers remain available; no Team
runtime is active. See [retention](archive.md).

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

Claude-only retirement verification (2026-11-03): **176 offline tests passed**
in server stage `/tmp/mas-claude-only-benchmarks.WoJDYt`, receipt
`pytest-results.xml`. Harness and new benchmark entry-point help checks also
passed. Active container arguments were tested to contain no dcode mounts or
Deep Agents environment/executable dependency. No production sync or uninstall.

For the subsequent benchmark-structure cleanup and current offline verification,
see [the adaptation audit](benchmark-adaptation.md#verification-receipt).
