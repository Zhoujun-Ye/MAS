import json
from pathlib import Path
import subprocess
import sys

from analysis import native_evidence
from analysis.native_evidence import background_shell_evidence

def test_payload_rejection_is_not_hidden_by_native_is_error_false(tmp_path):
    events = [dict(message=dict(content=[dict(type="tool_use", id="a", name="Bash", input={})])),
              dict(message=dict(content=[dict(type="tool_result", tool_use_id="a", is_error=False,
                  content=[dict(type="text", text=json.dumps(dict(success=False, message="members active")))])]))]
    (tmp_path / "history.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    result = native_evidence.tool_errors(tmp_path, "claude-code", tmp_path / "no-stdout")
    assert result["reported_tool_errors"] == 0
    assert result["payload_rejections_by_tool"] == dict(Bash=1)


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



def test_evidence_decoder_remains_standalone_under_isolated_python(tmp_path):
    profile = tmp_path / 'empty-profile'
    result = subprocess.run([sys.executable, '-I', str(Path(native_evidence.__file__).resolve()),
        '--backend', 'claude-code-subagents', '--profile', str(profile)],
        cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['team_correctness_verified'] is False
    assert not profile.exists()


def test_background_handoff_does_not_establish_completion():
    rows = [dict(tool_name='Bash', tool_response=dict(backgroundTaskId='one'))] * 2
    assert background_shell_evidence(rows)['bash_background_handoffs'] == 1
    assert background_shell_evidence(rows)['running_shells_at_last_stop'] is None
    rows.append(dict(hook_event_name='Stop', background_tasks=[dict(type='shell', status='running')]))
    assert background_shell_evidence(rows)['running_shells_at_last_stop'] == 1
    rows.append(dict(hook_event_name='Stop', agent_id='worker', background_tasks=[]))
    assert background_shell_evidence(rows)['running_shells_at_last_stop'] == 1
    rows.append(dict(hook_event_name='Stop', background_tasks=[]))
    assert background_shell_evidence(rows)['running_shells_at_last_stop'] == 0
