import json

import pytest
from fakes import EVIDENCE, GOLD, TASK, FakeRetriever, ScriptedClient, last_user, role_of, turn

from mas_info.agent import BUDGET_EXHAUSTED
from mas_info.bcp import diagnostics, prompts
from mas_info.bcp.retriever import Truncator
from mas_info.bcp.system import solve
from mas_info.bcp.tools import get_document_tool, search_tool
from mas_info.trace import Trace, contexts, llm_inputs, read_trace

SETTINGS = {"k": 5, "snippet_max_tokens": 512, "tool_calls": 50, "max_turns": 10, "max_workers": 5}
ANSWER = "Explanation: Maria Lopez won in 2003 [102].\nExact Answer: Maria Lopez\nConfidence: 90%"
SUBTASKS = ["Find who won the Alpha Prize in 2003.", "Find when the Alpha Prize was founded."]
WORKER_JSON = {
    "conclusion": "Maria Lopez won in 2003.",
    "key_facts": [{"fact": "Maria Lopez won in 2003", "source": "102"}],
    "ruled_out": [],
    "open_questions": [],
    "confidence": "high",
}


def policy(messages, tools, tool_choice):
    role, n = role_of(messages), turn(messages)
    if tool_choice == "none":
        return {"content": "Exact Answer: forced"}
    if role in ("single", "sequential"):
        if last_user(messages).startswith("All sub-tasks are done") or n >= 2:
            return {"content": ANSWER}
        return {"calls": [("search", {"query": "Alpha Prize 2003"})] if n == 0 else [("get_document", {"docid": "102"})]}
    if role == "lead":
        if n == 0:
            calls = [("dispatch", {"task": task}) for task in SUBTASKS]
            return {"reasoning": "Plan the search. LEAD-NOTE", "calls": calls}
        if n == 1 and "read_artifact" in tools:
            return {"calls": [("read_artifact", {"artifact_id": "a1"})]}
        return {"content": ANSWER}
    if role == "worker":
        if n == 0:
            return {"calls": [("search", {"query": last_user(messages).split("Your assignment:\n")[-1]})]}
        if "only a JSON object" in messages[0]["content"]:
            return {"content": json.dumps(WORKER_JSON)}
        return {"content": "Report: I found who won."}  # cites no docid
    raise AssertionError(role)


def run(tmp_path, condition, settings=SETTINGS, subtasks=None, client_policy=policy):
    client = ScriptedClient(client_policy)
    retriever = FakeRetriever()
    tools = [search_tool(retriever, settings["k"], Truncator(512, None)), get_document_tool(retriever)]
    path = tmp_path / f"{condition}.jsonl"
    with Trace(path, f"bcp_q7_{condition}_r0") as trace:
        result = solve(TASK, condition, client=client, search_tools=tools, trace=trace, settings=settings, subtasks=subtasks)
    return result, read_trace(path), client


def boundary(events, direction):
    return [e for e in events if e["type"] == "boundary_msg" and e["direction"] == direction]


def test_single_agent(tmp_path):
    result, events, _ = run(tmp_path, "C0")
    assert result["status"] == "completed" and result["answer"] == "Maria Lopez"
    assert result["retrieved_docids"] == ["101", "102"] and result["tool_budget_used"] == 2
    assert not boundary(events, "down")
    final = next(e for e in events if e["type"] == "final")
    assert final["agent"] == "single" and final["context_tokens"] > 0


@pytest.mark.parametrize("condition", ["C1", "C2", "C3", "C4"])
def test_team_logs_every_boundary(tmp_path, condition):
    result, events, client = run(tmp_path, condition)
    down, up = boundary(events, "down"), boundary(events, "up")
    assert len(down) == len(up) == 2
    assert {e["edge"] for e in down} == {"lead->search_1", "lead->search_2"}
    assert sorted(e["task"] for e in down) == sorted(SUBTASKS)
    assert result["tool_budget_used"] == 2  # both workers drew from one budget
    assert all(e["agent"] != "lead" for e in events if e["type"] == "tool_call" and e["tool"] == "search")
    # The trace rebuilds exactly what the lead was sent in every call.
    sent = [request for request, _, _ in client.requests if role_of(request) == "lead"]
    assert llm_inputs(events, "lead") == sent


def test_relay_forms(tmp_path):
    _, c1, _ = run(tmp_path, "C1")
    assert [e["content"] for e in boundary(c1, "up")] == ["Report: I found who won."] * 2
    assert boundary(c1, "down")[0]["content"] in SUBTASKS

    _, c2, _ = run(tmp_path, "C2")
    assert all(e["schema_valid"] and json.loads(e["content"]) == WORKER_JSON for e in boundary(c2, "up"))

    _, c3, _ = run(tmp_path, "C3")
    down = boundary(c3, "down")[0]["content"]
    assert down.startswith("Original task:\nWho won the Alpha Prize") and "LEAD-NOTE" in down
    up = boundary(c3, "up")[0]["content"]
    assert "=== Complete tool log ===" in up and "Maria Lopez won the Alpha Prize in 2003" in up

    _, c4, _ = run(tmp_path, "C4")
    observations = [e["observation"] for e in c4 if e["type"] == "tool_call" and e["tool"] == "search"]
    assert all(text.startswith("[artifact a") for text in observations)
    assert all("=== Artifact index ===" in e["content"] for e in boundary(c4, "up"))
    reads = [e for e in c4 if e["type"] == "tool_call" and e["tool"] == "read_artifact"]
    assert reads[0]["agent"] == "lead" and "Alpha Prize" in reads[0]["observation"]


def test_sequential_replays_subtasks(tmp_path):
    result, events, _ = run(tmp_path, "C5", subtasks=SUBTASKS)
    users = [m["content"] for m in contexts(events)["single"] if m["role"] == "user"]
    assert users[0].startswith("Question: Who won") and "Sub-task 1 of 2" in users[0]
    assert users[1].startswith("Sub-task 2 of 2") and users[2] == prompts.SUBTASKS_DONE
    assert result["answer"] == "Maria Lopez"


def test_budget_is_shared_and_enforced(tmp_path):
    _, events, _ = run(tmp_path, "C0", settings={**SETTINGS, "tool_calls": 1})
    calls = [e for e in events if e["type"] == "tool_call"]
    assert calls[0]["tool"] == "search" and calls[1]["observation"] == BUDGET_EXHAUSTED


def test_turn_limit_forces_a_final_answer(tmp_path):
    result, events, client = run(tmp_path, "C0", settings={**SETTINGS, "max_turns": 1})
    assert result["final_status"] == "turn_limit" and result["answer"] == "forced"
    messages, _, tool_choice = client.requests[-1]
    assert tool_choice == "none" and messages[-1]["content"] == prompts.FINAL_ANSWER


def test_loss_diagnostics(tmp_path):
    _, c0, _ = run(tmp_path, "C0")
    single = diagnostics.analyze(c0, TASK, EVIDENCE, GOLD)
    assert single["evidence"]["r_sys"] == 1.0 and single["evidence"]["loss"] == 0.0
    assert single["answer_in_decider"]

    _, c1, _ = run(tmp_path, "C1")
    team = diagnostics.analyze(c1, TASK, EVIDENCE, GOLD)
    assert team["evidence"]["r_sys"] == 1.0 and team["evidence"]["r_arrive"] == 0.0
    assert team["evidence"]["loss"] == 1.0
    assert team["answer_in_other"] and not team["answer_in_decider"]
    assert diagnostics.failure_category(team, False) == "transmission"
    assert diagnostics.failure_category(team, True) is None

    _, c3, _ = run(tmp_path, "C3")
    full = diagnostics.analyze(c3, TASK, EVIDENCE, GOLD)
    assert full["evidence"]["loss"] == 0.0 and full["answer_in_decider"]
    assert diagnostics.failure_category(full, False) == "synthesis"
