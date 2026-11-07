import json

from analysis.run_integrity import inspect_run


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows))


def test_unmatched_calls_and_late_delegation(tmp_path):
    def msg(identity, content, role="assistant"):
        return dict(message=dict(id=identity, role=role, content=content))
    write(tmp_path / "native-profile/claude/root.jsonl", [
        msg("m1", [dict(type="tool_use", id="shell", name="Bash", input={})]),
        msg("m2", [dict(type="text", text="answer42")]),
        msg("m3", [dict(type="tool_use", id="delegate", name="Agent", input={})]),
        msg("u1", [dict(type="tool_result", tool_use_id="delegate", content="done")], "user")])
    write(tmp_path / "gateway-requests.jsonl", [dict(request_id=i, route="/anthropic/v1/messages",
        upstream_attempted=True, provider_response_id=i) for i in ["m1", "m2", "m3", "shell-direct"]])
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace/submission.json").write_text(json.dumps(dict(final_answer="answer42")))
    audit = inspect_run(tmp_path, "claude-code-subagents")
    assert audit["gateway_reconciliation"]["status"] == "review_required"
    assert audit["gateway_reconciliation"]["matched_requests"] == 3
    timeline = audit["lead_delegation_timeline"]
    assert timeline["before_first_delegation"]["tool_calls"] == 1
    assert timeline["before_first_delegation_result"]["answer_matches"][0]["line"] == 2
    assert timeline["first_delegation_result"] == 3


def test_missing_evidence_is_unknown(tmp_path):
    audit = inspect_run(tmp_path, "claude-code-subagents")
    assert audit["gateway_reconciliation"]["status"] == "incomplete"
    assert audit["lead_delegation_timeline"]["status"] == "unavailable"


def test_claude_background_ack_is_not_worker_result(tmp_path):
    write(tmp_path / "native-profile/claude/root.jsonl", [
        dict(message=dict(role="assistant", content=[dict(type="tool_use", id="d", name="Agent",
             input=dict(run_in_background=True))])),
        dict(message=dict(role="user", content=[dict(type="tool_result", tool_use_id="d", content="started")]))])
    assert inspect_run(tmp_path, "claude-code-subagents")["lead_delegation_timeline"]["first_delegation_result"] is None
