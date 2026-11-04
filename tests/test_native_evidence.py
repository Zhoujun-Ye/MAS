import json

from analysis import native_evidence

def test_payload_rejection_is_not_hidden_by_native_is_error_false(tmp_path):
    events = [dict(message=dict(content=[dict(type="tool_use", id="a", name="TeamDelete", input={})])),
              dict(message=dict(content=[dict(type="tool_result", tool_use_id="a", is_error=False,
                  content=[dict(type="text", text=json.dumps(dict(success=False, message="members active")))])]))]
    (tmp_path / "history.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    result = native_evidence.tool_errors(tmp_path, "claude-code", tmp_path / "no-stdout")
    assert result["reported_tool_errors"] == 0
    assert result["payload_rejections_by_tool"] == dict(TeamDelete=1)
    assert result["team_delete_success_count"] == 0


def test_manual_native_team_state_edits_are_flagged(tmp_path):
    event = dict(message=dict(content=[dict(type="tool_use", id="edit", name="Bash", input=dict(
        command="rm -rf /native/claude/teams/example /native/claude/tasks/example"))]))
    (tmp_path / "history.jsonl").write_text(json.dumps(event))
    result = native_evidence.tool_errors(tmp_path, "claude-code", tmp_path / "no-stdout")
    assert len(result["native_state_write_commands"]) == 1


def test_terminal_json_values_are_not_stream_events(tmp_path):
    stdout = tmp_path / "stdout.log"
    stdout.write_text('15\n[1,2]\nnull\n{"type":"system","subtype":"api_retry"}\n')
    result = native_evidence.tool_errors(tmp_path, "claude-code", stdout)
    assert result["native_retry_events_observed"] == 1


def test_workspace_team_deliverables_are_not_native_runtime_state(tmp_path):
    event = dict(message=dict(content=[dict(type="tool_use", id="work", name="Bash", input=dict(
        command="cd /workspace/teams/checker && python -c \"import json; json.dump({},open('summary.json','w'))\""))]))
    (tmp_path / "history.jsonl").write_text(json.dumps(event))
    result = native_evidence.tool_errors(tmp_path, "claude-code", tmp_path / "no-stdout")
    assert result["native_state_write_commands"] == []

def test_implicit_team_does_not_require_retired_teamdelete(tmp_path):
    folder = tmp_path / "case/claude-code"
    (folder / "cli").mkdir(parents=True)
    snapshot = dict(configs=[dict(data=dict(members=[dict(name="checker", agentType="general-purpose")]))])
    (folder / "cli/native-team-history.jsonl").write_text(json.dumps(snapshot) + "\n")
    team = native_evidence.native_team(folder, dict(cli=dict(native_before_exit=dict(ready_to_exit=True),
        native_lifecycle=dict(root_session_end_observed=True))))
    assert team == dict(named_member_names=["checker"], native_stop_before_exit=True, session_end=True)
