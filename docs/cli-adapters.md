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
exists. Live solvers use a host credential gateway that preserves native wire
protocols without model orchestration. Retired launchers and checkpoint readers
are removed; authorized paid comparisons remain read-only under [retention](archive.md).

## Strict Single

The built-in `--tools` surface excludes native delegation. `--disallowedTools`
also denies Agent/Task aliases, peer messaging, workflows and scheduled agents.
Skills and ambient MCP/settings are isolated. An opt-in native PreToolUse policy
denies delegation attempts; unexpected SubagentStart is a condition violation.
Other modes never receive permission grants from hooks. Native observations
remain record-only; the tool-loop detector has been retired.

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

The November 11 infrastructure review fix gives both adapters an explicit
`--tools` surface and `--disable-slash-commands`. Single retains twelve base tools;
Subagents adds only Agent/Task aliases, SendMessage and ListAgents. Native init
advertises Task (Agent remains an accepted alias), for fifteen observed tools,
zero skills and zero slash commands. Native and Structured share this surface.
Proof admission checks the observed surface and the environment/options digest,
in addition to image/binary identity and lifecycle evidence. Old proofs cannot
admit the updated configuration.

The Subagents baseline uses current orchestrator-worker lead prompt, frozen by the user
on 2026-11-04 ([frozen prompts](../scripts/common/prompts/README.md)). The lead plans, splits the
work between itself and subagents (at least one, scaled to complexity) and synthesizes. It specifies
no specialist roster, judge role or cost-reduction policy.

For inspection, `scripts/common/prompts/structured_subagents.py` holds this unchanged
default as `PROMPT`. FULL/OBS and their prompt-only ablations were retired on
2026-11-10. Their historical lead prompts are not launch choices. Single and
Structured remain the defaults.
The explicitly approved Krama Native study uses `native_subagents.py`: only the
Structured opening paragraph plus "Always deploy at least one subagent."
It uses this same adapter and audit, not a third runtime or unprompted CLI policy.
The Python files are not raw-text inputs for `--organization-prompt`.

Native facts this relies on, observed on 2.1.286:
- There is no TaskOutput tool. Background agents notify the lead on completion.
- In print mode the run stays open after the lead ends its turn while a background
  agent still runs. The lead is resumed on completion, and stdout then holds one
  result event per resumed segment; the adapter keeps the last one.
- Isolated settings (`--setting-sources ""`) do not auto-load workspace
  `CLAUDE.md` or `AGENTS.md` for any agent. Workers learn task rules only from the
  lead's brief and from tool output.

Admission requires observed native delegation and completion, not semantic
contribution. This is a prompted condition, not an entirely unprompted Claude
Code run. Benchmark access and output requirements remain explicit. There is no
backup prompt or specialist-judge study.

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

### Retired Tool-Loop Guard

On November 12 the user retired the loop detector, including observation-only
counting, warnings, worker stops, lead notices and host termination monitoring.
There are no loop-mode launch options or active loop-pilot drivers. Native hooks
now record events only, except for the existing strict-Single permission policy.
Default inference remains thinking disabled, temperature 1.0. This is not a
guarantee against repetition; ordinary task deadlines remain enforced.

Preserve the paid guard/T=1 pilots, frozen sources and raw receipts under
[retention](archive.md). Historical reporting may read recorded loop fields but
never reconstructs or executes the removed detector. Old native admission proofs
are stale: fresh proofs bind the current environment, tool surface and adapter
implementation hashes. See [retirement verification](studies/loop-guard-retirement-20261112.md).

DeepSeek request policy is configured by the native CLI and validated, not
rewritten, by the host gateway. Current defaults are thinking disabled and
temperature 1.0 (`--effort none`); actual reasoning effort is not applicable.
High/max explicitly enable thinking and are not silent defaults. Main/worker
request fields and remaining nondeterminism are documented in
[Reproducibility](reproducibility.md).

OPUS, SONNET, HAIKU and FABLE aliases all map to `deepseek-flash[1m]`.
Both conditions use a 600,000 ms default/max native Bash timeout. This reduces
implicit background handoffs; explicit background work or shorter tool-selected
timeouts remain native behavior, not a guarantee of SessionEnd or quiescence.
The outer solver deadline is unchanged. See the
[review fix record](studies/infra-review-fixes-20261111.md) for all dispositions.

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
