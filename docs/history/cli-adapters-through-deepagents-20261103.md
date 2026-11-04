# Historical External CLI Adapters

Superseded on 2026-11-03 when the user retired Deep Agents. This document records
the prior contracts and installation evidence; it is not an active dependency
or deployment instruction. See [current contracts](../cli-adapters.md).

## Boundary

The repository contains five condition adapters for two external CLIs, not embedded agent frameworks:

| Class | External Executable | Pinned Version |
| --- | --- | --- |
| `DeepAgentsSingleAgentCLI` | `dcode` (`deepagents-code`) | 0.2.2 |
| `DeepAgentsSubagentsCLI` | `dcode` (`deepagents-code`) | 0.2.2 |
| `ClaudeCodeAgentTeamCLI` | `claude` | 2.1.225 |
| `ClaudeCodeSubagentsCLI` | `claude` | 2.1.225 |
| `ClaudeCodeSingleAgentCLI` | `claude` | 2.1.225 |

Each builds native arguments and invokes an installed executable once. Shared
code handles stdin, version checks, process groups and raw logs. No upstream
checkout, SDK dependency, custom tool loop, scheduler, message bus, provider
translation proxy, model routing or benchmark-specific solver prompt is added.

The reference is CoCoder's
[external CLI runtime](https://github.com/Flitternie/CoCoder/blob/main/code_team/claude_code_agent_team/runtime.py),
not its OpenHands implementation. Its runtime installs project subagent files
and invokes `claude --print`; that code alone is not proof of native peer-team
execution. We reuse the subprocess boundary, not its fixed roles or
`--dangerously-skip-permissions` behavior. No CoCoder source is copied.

## Deep Agents Version Decision

Checked on 2026-11-02 against PyPI metadata and pinned upstream source.

- The former coding CLI package name is misleading today:
  [`deepagents-cli==0.3.0`](https://pypi.org/project/deepagents-cli/0.3.0/)
  is deprecated deployment tooling. It is not the coding-agent CLI we need.
- Selected [`deepagents-code==0.2.2`](https://pypi.org/project/deepagents-code/0.2.2/),
  executable `dcode`, with upstream SDK dependency `deepagents==0.7.32`.
  It supplies headless input, explicit models, native subagents and no-retry
  flags without rebuilding agent logic in this project.
- Its [release notes](https://github.com/langchain-ai/deepagents/blob/42e4f08af802f61813b6107b857d0d2cca965f9a/libs/code/CHANGELOG.md)
  include project dotenv/trust fixes, subagent-failure containment, headless
  sandbox lifetime fixes and performance improvements. This makes it the
  preferred starting pin, not evidence of better benchmark performance.
- Version 0.1.88 is the last release before the Python-3.14 requirement and is
  compatible with Python 3.12. It is not the default recommendation because it
  predates the 0.2.2 fixes. Do not silently fall back to it.
- Version 0.2.2 requires Python `>=3.14,<3.15` in its own CLI environment.
  Out-of-process invocation allows the research project to remain on Python
  3.12/3.13. The reset itself did not install that runtime; the separately
  authorized installation is recorded below.

Source pin:
[`42e4f08af802f61813b6107b857d0d2cca965f9a`](https://github.com/langchain-ai/deepagents/tree/42e4f08af802f61813b6107b857d0d2cca965f9a/libs/code).
Native `--version` output records the CLI and SDK facts when actually available;
the adapter checks the CLI version, not the complete transitive environment.

The command uses `--stdin --quiet --no-stream --model MODEL --max-retries 0`.
Shell is disabled unless `shell_allow_list` / `--shell-allow-list` is explicit.
This does not make other tools read-only or network-free. No `--auto-approve`
flag is added: upstream headless approvals differ from its interactive mode.
Automatic app/plugin/pricing updates and LangSmith tracing are disabled through
launch environment overrides. Native local state is still managed by dcode.

## Claude Code Contract

The active pin is now **2.1.225**, replacing the old 177 launcher after the
user's explicit upgrade request. The Team adapter defaults to a controlling
terminal, never `-p`. Native hooks record start/idle/stop/end observations but
do not direct agent scheduling, inject context or grant permissions. The
complete request is a deterministic workspace file, not raw task text in argv.
The adapter sends the native `/exit` command only after ordered native completion.

The full-run audit found that automatic teammate messages can append to the
root transcript after Stop without UserPromptSubmit. The transport now observes
those native user records too: a pending native input invalidates the old Stop
until a newer Stop follows it. Benchmark launches also require a nonempty,
non-symlink submission file before /exit. Neither idle nor Stop alone proves
benchmark completion. No messages are replayed, injected or routed by this code.

## Strict Single Condition

The user's corrected Deep Agents baseline is strictly single-agent. Earlier
pilot/full runs allowed native delegation and are **not single baselines**.
The new benchmark launcher explicitly passes `single_agent=True` and prepares
an independent native hooks.json. Dcode 0.2.2 has no documented no-subagents
CLI flag. Its native PreToolUse hook denies task/Agent and asynchronous-task
delegation; SubagentStart is a condition violation. MCP, the JS interpreter
and extension discovery are disabled. The hook executable and native hook file
are mounted read-only. No SDK or upstream code is imported or patched here.

This is a native delegation policy, not an adversarial shell/network sandbox.
The prompt also forbids external model/CLI calls through shell or Python.
Every attempt must retain SessionStart/End, zero SubagentStart and zero executed
delegation tools, with zero member messages in retained native checkpoints.
Missing policy evidence is not a pass. A failed admission probe prevents the
remaining paid workload from starting; no replacement attempts are automatic.

The real installed CLI was tested in a no-network container with dummy
credentials and a loopback fake provider deliberately returning a task call.
That call was denied before execution, its denial returned to the root model,
and native subagent starts remained zero (two fake requests, no paid calls).
Receipt: archives/output-cleanup-20261102/single-native-guard-probe-20261102-01/proof.json on the server.

v178 removed TeamCreate/TeamDelete. An implicit native session team plus named
Agent teammates, task tools and direct messaging is the supported pattern.
Current docs explicitly exclude true teammates from print/SDK mode. The separate
`harness/claude_code_subagents/` adapter uses print mode with Teams explicitly
disabled. It is a distinct experimental condition, not the Team baseline.

Only first-launch theme/security acknowledgments, an environment-key choice if
shown, and trust for the owned disposable workspace are answered automatically.
Tool permissions, auth-method selection and billing consent are not bypassed.
Native `--max-budget-usd` is print-only and is rejected for interactive Team
runs, rather than presented as an enforced shared budget. Full-run costs have
their own explicit authorization.

Historical transport audits and the retired v177 pilot description are retained
in the source snapshots listed in [archive.md](archive.md), not active contracts.

## Invocation And Evidence

All five condition classes expose `command(model, ...)` and
`run(prompt, model=..., workspace=..., output=..., execute=False, ...)`.
The default returns a plan with no subprocess or output writes. The
`python -m harness` entry point follows the same default; `--execute` must only
be used after explicit run-specific paid authorization.

Execution requires a non-overlapping existing workspace and fresh output
directory. Leading/trailing prompt whitespace is normalized before hashing and
dispatch. The task is passed through stdin, never a shell command or argv string.

Each execution retains `launch.json`, `prompt.txt`, `cli-version.json` when
preflight succeeds, raw `stdout.log` / `stderr.log` when launched, and
`result.json`, including failures. Only fixed non-secret environment overrides
are recorded, never the full inherited environment. Native tools can themselves
print sensitive data; raw logs must be treated as private research evidence.

Timeouts and interruptions terminate the POSIX process group. Detached services
are outside that guarantee; this is not a sandbox, container lifecycle manager,
workspace freeze or proof of quiescence. Native profiles and their project/user
settings are not isolated or copied by the adapters.

## Research Limits

Deep Agents' hierarchical/native subagents are not automatically equivalent to
Claude Code's peer teams. CLI pins do not freeze provider models, dependencies,
profiles, permissions, automatic context handling, worker models or prompts.

The retired runtime's coordinator condition, task authority, shared budget,
bounded membership, append-only message instrumentation and artifact-export
contract have deliberately not been recreated. Resource limits, role-level
tokens/cache/costs, native fatal-error behavior, actual team formation, backend
comparability and benchmark correctness require new design and live validation.
Unavailable accounting remains null. Fake CLI tests verify adaptation only.

## Native Subagents Condition (2026-11-02)

`claude-code-subagents` uses `--print --verbose --output-format stream-json`,
with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0` in both the launch environment
and native settings. It does not install a roster or modify the upstream CLI.
Workers use the native Agent tool and return findings to the parent; this is
not the peer communication model of [Agent Teams](https://code.claude.com/docs/en/agent-teams).
See also the [native subagents documentation](https://code.claude.com/docs/en/sub-agents).

The installed 2.1.225 executable passed an offline loopback-provider probe in
an existing container with network disabled and dummy credentials: one native
SubagentStart, one SubagentStop, root SessionEnd, successful stream result,
zero native team configurations and zero TeammateIdle events. Four fake model
requests incurred zero paid calls. Receipt on the server:
`archives/claude-subagents-20261102/native-probe-01/proof.json`.
This establishes native wiring, not DeepSeek behavior or benchmark quality.
The full run must separately record actual delegation and lifecycle observations
per task; native final result accounting does not guarantee worker coverage.

Current adapter/benchmark regression is checked in the isolated server source
stage `/tmp/mas-claude-subagents-source.2lL0GI`; its `pytest-final.xml` is the
current receipt. This does not deploy changes over any frozen experiment source.

## Claude Single Condition (2026-11-03)

`harness/claude_code_single_agent/` adds a fourth condition, using the same
external Claude 2.1.225 executable and print transport as Subagents. Native
`--tools` restricts the built-in surface to file/shell/self-task tools, while
`--disallowedTools` explicitly denies both Agent and the Task alias, peer
messaging, workflows and scheduled agents. Skills are disabled; settings and
MCP configuration are isolated. No permission bypass is enabled.

An opt-in PreToolUse hook denies delegation attempts; unexpected SubagentStart
requests native stop and is retained as a condition violation, never counted as
a successful Single attempt. Other modes keep
record-only hooks. Admission requires SessionStart/End, Single-policy hook
observations, zero exposed delegation tools, zero starts/executed delegation,
zero worker transcript files and no native Teams. Post-run transcript accounting
must also observe zero member messages. Missing evidence is not success.

The hook/permissions are native CLI adaptation, not a provider loop, custom
scheduler, or adversarial OS/network sandbox. Shell/Python could otherwise
access external services; the Single study forbids external agent/model calls.
Native compaction/helper requests are not represented as worker delegation.
The study uses unchanged common task/artifact instructions and the same Single
condition instruction as Deep Agents; no fixed agent roster is introduced.

References: [CLI tool controls](https://code.claude.com/docs/en/cli-reference)
and [native permission hooks](https://code.claude.com/docs/en/hooks).
Pinned native help and a no-network denial probe, not latest docs alone, must
validate this installation before paid dispatch.

The installed executable passed two network-disabled, dummy-credential probes:
the production Single arguments rejected forced Agent/Task calls without exposing
either tool, and a deliberately relaxed diagnostic tool list verified that the
PreToolUse guard separately denied both aliases. Neither started a worker; six
total loopback model requests incurred zero paid calls. The diagnostic case is
not a production Single configuration. Receipt:
`archives/claude-single-agent-20261103/native-denial-01/proof.json` on the server.
Server stage `/tmp/mas-claude-single-source.o90QUT` passed 173 offline tests.

Tests must use offline stub executables, not either real model-running CLI.
For this reset, server verification uses a separate temporary source directory,
not a deployment into the active server project.

## Historical Reset Verification (2026-11-02)

Server source staging: `/tmp/mas-information-cli-check.au04lo`, using the existing
project Python 3.12.15 environment. Final offline regression: **77 passed**.
JUnit receipt: `/tmp/mas-information-cli-check.au04lo/pytest-results.xml`.
Tests read the existing pinned KramaBench checkout through a symlink for workload
and metric-differential checks; there were no skipped reference tests. Shell syntax
checks and all retained command-line `--help` entry points also passed.

Real-Claude inspection was limited to offline `--version` / `--help`.
Deep Agents adaptation was checked against pinned upstream source, not a live
installed dcode. Neither backend's model execution, native team/subagent behavior,
provider retries, sandboxing or end-to-end benchmark performance was tested.
No installation, production deployment, paid call or image operation was run.

## Authorized Server Installation (2026-11-02)

After the reset, the user separately authorized installation of the selected
Deep Agents CLI. The install used the existing uv 0.13.1 and the Tsinghua PyPI
mirror, without cloning source or modifying the project's Python environment:

```sh
/home/zhoujunye/.local/bin/uv --no-config tool install --python 3.14 \
  --default-index https://pypi.tuna.tsinghua.edu.cn/simple \
  'deepagents-code==0.2.2'
```

- Executable: `/home/zhoujunye/.local/bin/dcode`.
- Independent tool environment: `/home/zhoujunye/.local/share/uv/tools/deepagents-code`.
- Tool Python: 3.14.8; project Python remains 3.12.15.
- Confirmed CLI: `deepagents-code 0.2.2`; SDK: `deepagents 0.7.32`.
- `uv pip check` verified all 157 installed packages are compatible.
- Automatic app updates were persistently disabled through the native CLI's
  configuration helper. `dcode config get update.auto_update --json` confirmed
  `false`, sourced from `config.toml`, without an environment override.
- Native `--version` and `--help` succeeded. The existing adapter's real version
  preflight also accepted this executable without dispatching a task.

The noninteractive SSH PATH does not include `/home/zhoujunye/.local/bin`.
Use the absolute executable path (including the adapter's `--executable` option),
or explicitly add that directory to the launch PATH. No shell startup file was
modified. No provider credentials were added, and no model call, agent session,
paid experiment, container operation or production source deployment was run.
These installation checks do not establish live subagent or benchmark behavior.
