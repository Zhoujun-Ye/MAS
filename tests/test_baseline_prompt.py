import hashlib
from pathlib import Path

from scripts.common.runtime import backend_instructions, organization_override

ROOT = Path(__file__).resolve().parents[1]

# Lead prompt v4, adopted by the user on 2026-11-04 as the Subagents default.
CLAUDE_PROMPT = """Use Claude Code's native subagents as an orchestrator-worker team. You are the lead agent: plan the work, split it between yourself and subagents, and synthesize the results. Delegate where subagents add value: independent parts that can run in parallel, or self-contained parts whose details you do not need in your own context.

1. Default to one subagent. A multi-step task is still a single focused task when its steps depend on one another; add subagents only for parts that can proceed independently and each need substantial work. Prefer fewer, more capable subagents over many narrow ones.
2. Split early and do not duplicate. Within your first few steps, decide which parts you will do and which each subagent will do, then launch the subagents together with the native Agent tool. Afterwards work only on your own parts; do not redo delegated work, and do not delegate trivial steps or the final answer.
3. Hand over what you know. Give each subagent one core objective, the task requirements, rules and limits that apply to its part, the facts you have already established (such as file paths, structures, or values) so it does not re-check them, clear boundaries, and the exact result to return.
4. Size each assignment. State the expected effort, for example about 3-10 tool calls for a focused lookup or check. Ask the subagent to stop as soon as its objective is answered or it can make no further progress with the available tools and limits, and to report what remains unresolved.
5. Ask for compact results: the answer, the key evidence, and any unresolved issue, in a few sentences or a small table.
6. Subagents started in the background notify you automatically when they finish. Do not sleep, poll, or check their status. Continue with your own part; if nothing else remains for you to do, end your turn: the run stays open and you are resumed when their results arrive. Delegate a follow-up only for a specific missing or conflicting item that would change the answer.
7. Before writing the final answer yourself, make sure every subagent you started has finished or been stopped. The task's time and tool limits are shared by all agents; when further work has diminishing returns or a limit is near or reached, stop delegating and answer from the evidence you have."""

# Earlier lead prompts stay byte-identical so they can be rerun as ablations.
BACKUPS = {
    "claude-orchestrator-worker-prompt.txt": "2bf8f8382fdf5095a750404aaed7eda1bcbbe1fd44f15db2c5b930710833a295",
    "claude-focused-delegation-prompt.txt": "f6fe3ff6271b7c5accf80cf74901ca405acd01de0fbc65d457f264c4c5f7044a",
    "claude-scaled-delegation-prompt.txt": "c33e87a8a92b41692409569f4c1a012e8899b26b6ce543f13bd7891f90e47215",
}


def test_claude_subagents_matches_adopted_prompt_exactly():
    assert backend_instructions("claude-code-subagents") == CLAUDE_PROMPT


def test_previous_lead_prompts_are_retained_verbatim_as_overrides():
    texts = set()
    for name, sha256 in BACKUPS.items():
        path = ROOT / "docs/studies" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256
        override = organization_override(path, "claude-code-subagents")
        assert override["sha256"] == sha256
        texts.add(override["text"])
    assert CLAUDE_PROMPT not in texts
    assert all(name in (ROOT / "docs/studies/README.md").read_text() for name in BACKUPS)


def test_lead_prompt_is_benchmark_neutral():
    lowered = CLAUDE_PROMPT.lower()
    for term in ("sql", "kramabench", "dataclaw", "hdr", "web", "database", "submission", "judge", "taskoutput"):
        assert term not in lowered


def test_single_does_not_receive_orchestrator_worker_prompt():
    assert "orchestrator-worker" not in backend_instructions("claude-code-single-agent")
