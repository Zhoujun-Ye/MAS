import hashlib

from scripts.common.prompts.conditions import backend_instructions
from scripts.common.prompts.single_agent import PROMPT as SINGLE_AGENT_PROMPT
from scripts.common.prompts.structured_subagents import PROMPT as STRUCTURED_SUBAGENTS_PROMPT

# Current lead prompt, frozen by the user on 2026-11-04.
CLAUDE_PROMPT = backend_instructions("claude-code-subagents")
FINAL_PROMPT_SHA256 = "31ff6e4176a25d961866f644adb4d7b97cb4b00228e696c0e4e38a52b9485a95"

def test_claude_subagents_matches_adopted_prompt_exactly():
    assert hashlib.sha256(CLAUDE_PROMPT.encode()).hexdigest() == FINAL_PROMPT_SHA256


def test_lead_prompt_is_benchmark_neutral():
    lowered = CLAUDE_PROMPT.lower()
    for term in ("sql", "kramabench", "dataclaw", "hdr", "web", "database", "submission", "judge", "taskoutput"):
        assert term not in lowered


def test_single_does_not_receive_orchestrator_worker_prompt():
    assert "orchestrator-worker" not in backend_instructions("claude-code-single-agent")


def test_condition_selection_preserves_exact_prompt_text():
    assert CLAUDE_PROMPT == STRUCTURED_SUBAGENTS_PROMPT
    assert backend_instructions("claude-code-single-agent") == SINGLE_AGENT_PROMPT
