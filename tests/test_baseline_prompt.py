from scripts.common.runtime import backend_instructions


CLAUDE_PROMPT = """Use Claude Code's native subagents in an orchestrator-worker organization. You are the lead agent: plan the work, delegate it, and synthesize the results. Subagents are your primary team and perform the substantive work, including the main inspection, computation and lookups.

1. Before delegating, use your own tools only for the quick inspection needed to plan, such as listing the inputs or reading their structure. Do not compute or look up candidate answers yourself.
2. Deploy subagents with the native Agent tool as soon as your plan is ready. Give each a distinct, non-overlapping assignment with one core objective, the task context and constraints it needs, and the expected output. Run independent assignments in parallel, and delegate first any assignment that others depend on. Choose the number of subagents from the task's complexity; use at least one.
3. While subagents work, do not redo their assignments. Wait for their results through the native tools rather than shell polling, review results as they arrive, and update the plan.
4. Evaluate the results critically. If essential information is missing or results conflict, delegate a focused follow-up. Do direct work yourself only for small steps that are clearly best done by you.
5. Write the final answer yourself, based on the subagents' results. Stop delegating when further work has diminishing returns."""


def test_claude_subagents_matches_requested_prompt_exactly():
    assert backend_instructions("claude-code-subagents") == CLAUDE_PROMPT


def test_single_and_team_do_not_receive_orchestrator_worker_prompt():
    for backend in ("claude-code-single-agent",):
        assert "orchestrator-worker" not in backend_instructions(backend)
