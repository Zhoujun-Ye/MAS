import json
from pathlib import Path
import sys

from harness import ClaudeCodeAgentTeamCLI
from harness.claude_code_agent_team.terminal import NativeInputObserver, lifecycle_state, startup_response


def test_team_command_is_not_print_mode():
    command = ClaudeCodeAgentTeamCLI().command("deepseek-flash[1m]")
    assert "--print" not in command and "--output-format" not in command
    assert "--ax-screen-reader" in command


def test_root_stop_before_worker_stop_is_not_a_close_signal(tmp_path):
    events = [dict(hook_event_name="SessionStart", session_id="root"),
              dict(hook_event_name="SubagentStart", session_id="root", agent_id="w"),
              dict(hook_event_name="Stop", session_id="root"),
              dict(hook_event_name="SubagentStop", session_id="root", agent_id="w")]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))
    assert not lifecycle_state(path)["ready_to_exit"]
    with path.open("a") as stream:
        stream.write("\n" + json.dumps(dict(hook_event_name="Stop", session_id="root")) + "\n")
    assert lifecycle_state(path)["ready_to_exit"]


def test_startup_responses_do_not_approve_tools_or_logins():
    assert startup_response("Allow this Bash command?", set()) is None
    assert startup_response("Select login method", set()) is None
    assert startup_response("Do you trust the files in this folder?", set())[0] == "workspace_trust"
    assert startup_response("Do you trust the files in this folder?", {"workspace_trust"}) is None


def test_persistent_teammate_idle_is_not_mistaken_for_busy_lifetime(tmp_path):
    events = [dict(hook_event_name="SessionStart", session_id="root"),
              dict(hook_event_name="SubagentStart", session_id="root", agent_id="native-id", agent_type="analyst"),
              dict(hook_event_name="TeammateIdle", session_id="root", teammate_name="analyst"),
              dict(hook_event_name="Stop", session_id="root")]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))
    assert lifecycle_state(path)["ready_to_exit"]
    assert lifecycle_state(path)["active_subagent_ids"] == []


def test_automatic_native_message_invalidates_old_stop_without_userprompt_hook(tmp_path):
    path = tmp_path / "projects/work/root.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(type="user", timestamp="2026-11-02T18:05:14.307Z")) + "\n")
    observer = NativeInputObserver(tmp_path)
    state = dict(session_id="root", root_stop_received_at="2026-11-02T18:05:14.257430+00:00")
    assert observer.pending(state)
    assert observer.pending(state)
    assert not observer.pending(dict(state, root_stop_received_at="2026-11-02T18:05:20+00:00"))


def test_interactive_transport_has_real_tty_and_native_stop_receipts(tmp_path):
    workspace, output = tmp_path / "work", tmp_path / "out"
    workspace.mkdir()
    script = tmp_path / "fake-claude"
    script.write_text(f'''#!{sys.executable}
import json,os,shlex,subprocess,sys
if '--version' in sys.argv:
    print('2.1.225 (Claude Code)')
    sys.exit(0)
assert os.isatty(0) and os.isatty(1)
assert '--print' not in sys.argv
settings=json.loads(sys.argv[sys.argv.index('--settings')+1])
def hook(kind):
    command=settings['hooks'][kind][0]['hooks'][0]['command']
    subprocess.run(shlex.split(command),input=json.dumps(dict(hook_event_name=kind,
        session_id='fixture',transcript_path='/native/root.jsonl')),text=True,check=True)
hook('SessionStart')
hook('Stop')
for line in sys.stdin:
    if line.strip()=='/exit':
        hook('SessionEnd')
        sys.exit(0)
sys.exit(3)
''')
    script.chmod(0o755)
    report = ClaudeCodeAgentTeamCLI(str(script)).run("public task", model="model", workspace=workspace,
        output=output, execute=True, timeout=15, hook_python=sys.executable)
    assert report["status"] == "cli_exited"
    assert report["native_lifecycle"]["root_session_end_observed"]
    assert report["exit_requested_after_native_stop"] is True
    assert (output / "stdout.log").is_file()


def test_transport_waits_for_native_automatic_reply_inflight_after_stop(tmp_path):
    workspace, output, profile = tmp_path / "work", tmp_path / "out", tmp_path / "profile"
    workspace.mkdir()
    transcript = profile / "projects/work/fixture.jsonl"
    transcript.parent.mkdir(parents=True)
    script = tmp_path / "fake-claude"
    script.write_text(f'''#!{sys.executable}
import json,os,select,shlex,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
if '--version' in sys.argv:
    print('2.1.225 (Claude Code)'); sys.exit(0)
settings=json.loads(sys.argv[sys.argv.index('--settings')+1])
def hook(kind):
    command=settings['hooks'][kind][0]['hooks'][0]['command']
    subprocess.run(shlex.split(command),input=json.dumps(dict(hook_event_name=kind,
        session_id='fixture',transcript_path='/native/root.jsonl')),text=True,check=True)
hook('SessionStart')
Path('submission.json').write_text('{{"answer":1}}')
hook('Stop')
time.sleep(0.05)
Path({str(transcript)!r}).write_text(json.dumps(dict(type='user',
    timestamp=datetime.now(timezone.utc).isoformat(),message=dict(content='native teammate report')))+'\\n')
if select.select([sys.stdin],[],[],3.5)[0]:
    sys.exit(7)
hook('Stop')
for line in sys.stdin:
    if line.strip()=='/exit':
        hook('SessionEnd'); sys.exit(0)
sys.exit(3)
''')
    script.chmod(0o755)
    report = ClaudeCodeAgentTeamCLI(str(script)).run("public task", model="model", workspace=workspace,
        output=output, execute=True, timeout=15, hook_python=sys.executable,
        native_profile=profile, completion_file="submission.json")
    assert report["status"] == "cli_exited"
    assert report["completion_file_observed"]
    assert not report["native_before_exit"]["pending_native_input"]
    assert report["elapsed_seconds"] > 5
