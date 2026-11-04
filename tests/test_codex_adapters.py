import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness import CodexSingleAgentCLI, CodexSubagentsCLI
from harness._codex_cli import parse_result
from analysis.codex_evidence import inspect


@pytest.mark.parametrize("kind,enabled", [(CodexSingleAgentCLI, False), (CodexSubagentsCLI, True)])
def test_codex_native_plan(tmp_path, kind, enabled):
    work = tmp_path / "work"
    work.mkdir()
    plan = kind().run("Solve", model="deepseek-flash", workspace=work, output=tmp_path / "out")
    assert plan["expected_version"] == "0.159.3"
    assert plan["status"] == "planned"
    assert not (tmp_path / "out").exists()
    argv = plan["argv"]
    assert f"features.multi_agent={str(enabled).lower()}" in argv
    assert f"features.multi_agent_v2={str(enabled).lower()}" in argv
    assert 'model_providers.deepseek.wire_api="responses"' in argv
    assert "model_providers.deepseek.request_max_retries=0" in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert argv[-1] == "-"


def test_codex_failed_turn_is_not_success(tmp_path):
    path = tmp_path / "events"
    path.write_text(json.dumps(dict(type="turn.failed")) + "\n")
    assert parse_result(path)["status"] == "incomplete"
    path.write_text(json.dumps(dict(type="turn.completed", usage=dict(input_tokens=3))) + "\n")
    result = parse_result(path)
    assert result["usage"]["input_tokens"] == 3
    assert result["delegation_verified"] is False


@pytest.mark.parametrize("kind,enabled", [(CodexSingleAgentCLI, False), (CodexSubagentsCLI, True)])
def test_pinned_native_tool_exposure(tmp_path, monkeypatch, kind, enabled):
    executable = os.environ.get("CODEX_TEST_EXECUTABLE")
    if not executable:
        pytest.skip("Pinned native binary required for offline integration probe")
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append(json.loads(body))
            payload = json.dumps({"error": {"message": "offline probe complete", "type": "invalid_request_error"}}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-dummy")
    work = tmp_path / "work"
    work.mkdir()
    try:
        result = kind(executable).run("Reply OK", model="deepseek-flash", workspace=work,
            output=tmp_path / "out", execute=True, timeout=30,
            base_url=f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert requests, (result, (tmp_path / "out/cli/stderr.log").read_text())
    assert len(requests) == 1
    names = {t.get("name") for t in requests[0].get("tools", [])}
    for tool in requests[0].get("tools", []):
        names.update(t.get("name") for t in tool.get("tools", []))
    assert ("spawn_agent" in names) == enabled, names
    assert result["status"] != "cli_exited"


def test_native_lifecycle_requires_completed_child(tmp_path):
    def session(name, source, terminal):
        rows = [dict(type="session_meta", payload=dict(id=name, source=source)),
                dict(type="event_msg", payload=dict(type=terminal))]
        (tmp_path / ("rollout-"+name+".jsonl")).write_text("\n".join(map(json.dumps, rows)))
    session("root", "exec", "task_complete")
    assert inspect(tmp_path, single=True)["passed"]
    assert not inspect(tmp_path, single=False)["passed"]
    session("child", dict(subagent={}), "turn_aborted")
    assert not inspect(tmp_path, single=True)["passed"]
    assert not inspect(tmp_path, single=False)["passed"]
    session("child", dict(subagent={}), "task_complete")
    assert inspect(tmp_path, single=False)["passed"]
