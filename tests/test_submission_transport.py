"""Submission validation and lossless provider transport regressions."""

import json

import httpx
import pytest

from benchmarks.kramabench.adapter import make_session, parse_submission, run_task
from benchmarks.kramabench.offline import FixtureWorkspace
from benchmarks.kramabench.roles import PROJECT_CONTEXT, SUBMISSION_INSTRUCTIONS
from benchmarks.kramabench.tasks import Task
from harness.llm import ChatClient, ModelConfig
from harness.trace import Trace, contexts, read_trace, validate
from tests.fakes import ScriptedClient


VALID = json.dumps({"answer": 4, "pipeline_path": "pipeline.py", "evidence": "fixture", "unfinished": []})
ROOT_RESPONSE_FORMAT = {"type": "json_object"}  # Generic opt-in transport, no longer the benchmark policy.


def test_json_mode_transport_preserves_tools_thinking_and_verbatim_history():
    bodies = []
    message = {"role": "assistant", "content": VALID, "reasoning_content": "verbatim reasoning"}

    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}],
                                       "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    client = ChatClient(ModelConfig(model="deepseek-flash", retries=0), transport=httpx.MockTransport(respond))
    history = [{"role": "system", "content": "Return JSON."}, message]
    tools = [{"type": "function", "function": {"name": "probe", "parameters": {"type": "object"}}}]
    try:
        result = client.complete(history, tools, "none", response_format=ROOT_RESPONSE_FORMAT)
        assert result.message == message
        assert bodies[0]["messages"] == history
        assert bodies[0]["tools"] == tools and bodies[0]["tool_choice"] == "none"
        assert bodies[0]["thinking"] == {"type": "enabled"}
        assert bodies[0]["response_format"] == {"type": "json_object"}
        assert "response_format" not in client.request_body(history)
        with pytest.raises(ValueError, match="response_format"):
            client.complete(history, response_format={"type": "unsupported"})
        for choice in ("required", {"type": "function", "function": {"name": "submit"}}):
            with pytest.raises(ValueError, match="thinking mode"):
                client.complete(history, tools, choice)
        assert len(bodies) == 1
    finally:
        client._http.close()


def test_single_submission_shared_budget_and_final_reminder(tmp_path):
    def policy(messages, tools, tool_choice):
        if tools == ["submit"]:
            assert SUBMISSION_INSTRUCTIONS in messages[-1]["content"]
            return {"calls": [("submit", json.loads(VALID))]}
        return {"calls": [("list_files", {"area": "data", "path": "."})]}

    client = ScriptedClient(policy)
    workspace = FixtureWorkspace(tmp_path / "fixture")
    workspace.calculate({"command": "fixture_average"}, None)
    with Trace(tmp_path / "trace.jsonl", "single") as trace:
        trace.emit("run_start")
        session, _ = make_session(client, trace, workspace, mode="single", session_model_calls=3)
        outcome = session.run("A public question")
        assert outcome.status == "done" and parse_submission(outcome.text)["answer"] == 4
        assert outcome.budget["model_calls"] == 3
        assert session.leader.response_format is None
        assert not session.members
        assert PROJECT_CONTEXT in session.leader.messages[0]["content"]
    attempts = [e for e in read_trace(tmp_path / "trace.jsonl") if e["type"] == "llm_attempt"]
    assert [e["response_format"] for e in attempts] == client.response_formats
    assert all(e["response_format"] is None for e in attempts)
    assert attempts[-1]["tool_choice"] is None
    assert attempts[-1]["available_tools"] == ["submit"]


@pytest.mark.parametrize("text", ["All checks complete.\n```json\n" + VALID + "\n```",
                                  "```json\n" + VALID + "\n```", "   ", VALID[:-1]])
def test_invalid_submission_retained_without_extraction_or_repair(tmp_path, text, monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("No real network request allowed")
    monkeypatch.setattr(httpx.Client, "send", forbid)
    client = ScriptedClient(lambda *args: {"content": text})
    workspace = FixtureWorkspace(tmp_path / "fixture")
    output = tmp_path / "attempt"
    with pytest.raises(ValueError):
        run_task(Task("fixture", "archeology", "Compute a value."), client=client, workspace=workspace,
                 dataset=workspace.data, output=output, mode="single", session_model_calls=1)
    report = json.loads((output / "report.json").read_text())
    assert report["failure_stage"] == "submission_validation"
    assert report["submission_status"] == "invalid" and not report["infra_affected"]
    assert report["usage"]["total"]["attempted_calls"] == 1
    assert report["usage"]["total"]["failed_calls"] == 0
    assert not (output / "submission.json").exists()
    assert not (output / "native_response.json").exists()
    events = read_trace(output / "trace.jsonl")
    assert validate(events) == []
    assert contexts(events)["leader"][-1]["content"] == text
    assert len(client.requests) == 1 and client.response_formats == [None]


@pytest.mark.parametrize('mode', ['single', 'team'])
def test_truncated_submit_is_incomplete_with_no_hidden_repair(tmp_path, mode):
    client = ScriptedClient(lambda *a: {'finish': 'length', 'reasoning': 'unfinished analysis',
                                      'calls': [('submit', json.loads(VALID))]})
    workspace = FixtureWorkspace(tmp_path / 'fixture')
    output = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='No valid submit'):
        run_task(Task('fixture', 'archeology', 'Compute a value.'), client=client, workspace=workspace,
                 dataset=workspace.data, output=output, mode=mode, session_model_calls=600)
    report = json.loads((output / 'report.json').read_text())
    assert report['termination_reason'] == 'length' and report['outcome_status'] == 'incomplete'
    assert report['budget']['model_calls_remaining'] == 599 and not report['infra_affected']
    assert report['submission_status'] == 'invalid' and len(client.requests) == 1
    assert not (output / 'submission.json').exists()
