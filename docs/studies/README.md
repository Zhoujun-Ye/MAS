# Subagents Lead Prompts

The Subagents condition appends one lead-only organization prompt after the shared
task rules. Single never receives it. Only the lead sees it; workers see what the
lead hands over plus the output of the tools they call.

## Current Default: Lead Prompt v4 (2026-11-04)

Defined in `scripts/common/runtime.py` (`backend_instructions`) and used when no
`--organization-prompt` is given. The user adopted it on 2026-11-04 after the
`claude-all-high-01-21a0cdb` timing diagnosis. It keeps the focused-delegation
prompt and changes three rules. Each change corrects mechanics or follows a
published source; none adds a roster, judge or benchmark-specific policy:

| Rule | Change | Basis |
| --- | --- | --- |
| 3 | Hand over the task requirements, rules **and limits** that apply to the worker's part | Workers do not see the lead's task text; 0/7 retained briefs relayed the shared integrity rule, and the web budget appeared only after it was exhausted |
| 4 | Stop when the objective is answered **or no further progress is possible with the available tools and limits**, then report what remains | Anthropic [research_subagent](https://github.com/anthropics/claude-cookbooks/blob/b6034e05ee90dbafe8c854e44cb6f0381bf57a5e/patterns/agents/prompts/research_subagent.md) (`maximum_tool_call_limit`: stop using tools on diminishing returns and report) |
| 6 | State the native waiting mechanism: background subagents notify the lead; never sleep or poll; if nothing else remains, end the turn and the run resumes on completion | Claude Code 2.1.286 has no TaskOutput tool, and its own Agent tool text says not to sleep or poll; 2/4 background leads still slept. Resumption after `end_turn` was observed in the retained Krama run |
| 7 | Stop delegating when a limit is near **or reached** | The previous wording missed the already-exhausted case |

Run limits themselves (wall-clock seconds and, where enabled, the shared web
budget) are task rules, not organization. `limit_instructions()` states them
identically to Single and Subagents. The web helper also reports the remaining
budget in every response and gives one final message when the budget is gone.

Kept out on purpose, because they are the research object: restrictions on
lead-first exploration, verification limits, evidence-gated follow-ups, budget
allocation, roles and judges. Improvements there are separate study conditions,
with this prompt as the control.

## Retained Prompts

All files load unchanged with `--organization-prompt docs/studies/<file>`.
The SHA-256 covers the raw file bytes, as recorded by `organization_override`.

| File | Status | SHA-256 |
| --- | --- | --- |
| `claude-focused-delegation-prompt.txt` | Lead prompt v3. Used by the retained `claude-all-high-01-21a0cdb` batch | `f6fe3ff6271b7c5accf80cf74901ca405acd01de0fbc65d457f264c4c5f7044a` |
| `claude-orchestrator-worker-prompt.txt` | Strict orchestrator-worker prompt, the code default until v4 | `2bf8f8382fdf5095a750404aaed7eda1bcbbe1fd44f15db2c5b930710833a295` |
| `claude-scaled-delegation-prompt.txt` | Earlier scaled-delegation study prompt | `c33e87a8a92b41692409569f4c1a012e8899b26b6ce543f13bd7891f90e47215` |

`tests/test_baseline_prompt.py` pins the v4 text and these hashes.

v4 has no paid result yet. Validate it on tasks other than the six used in its
diagnosis, and freeze it before any comparison.

## Verification Receipt (2026-11-04)

Fresh server source stage: `/home/zhoujunye/MAS-information-stages/20261104-lead-v4`.
`pytest-results.xml` records **341 passing offline tests, none skipped**, with
`KRAMABENCH_UPSTREAM` set for the pinned-source checks.

The real HDR and DataClaw planners ran in plan-only mode against the server data
and created no output directory. HDR Single prompts are 2,270 and 1,780
characters; Subagents prompts are 4,298 and 3,808. The web helper was also run as a
subprocess against a closed loopback port with a budget of 1:
- the transport failure consumed the reservation and was not retried;
- the next call exited with status 3 and printed only the final budget message.

No paid model, search or judge calls were made. No container ran, and nothing was
deployed to production. Existing offline native proofs bind only the image and CLI
binary, so they still validate. They were recorded before TaskOutput (which does
not exist in 2.1.286) was removed from the requested tool lists.
