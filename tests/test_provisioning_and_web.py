import hashlib
import json
from types import SimpleNamespace

import pytest

from harness.runtime_support import tools
from scripts.server.prepare_data import download


@pytest.fixture(autouse=True)
def gateway_environment(monkeypatch,tmp_path):
    monkeypatch.setenv('MAS_WEB_BASE_URL','http://127.0.0.1:8765')
    monkeypatch.chdir(tmp_path)


def test_hydration_checks_content_and_reuses_verified_assets(tmp_path, monkeypatch):
    content = b"verified asset"
    expected = hashlib.sha256(content).hexdigest()
    path = tmp_path / "asset"
    calls = []
    def fetch(command, **kwargs):
        calls.append(command)
        from pathlib import Path
        Path(command[command.index("--output") + 1]).write_bytes(content)
    monkeypatch.setattr("scripts.server.prepare_data.subprocess.run", fetch)
    download("https://example.invalid/data", path, sha256=expected, size=len(content))
    download("https://example.invalid/data", path, sha256=expected, size=len(content))
    assert len(calls) == 1
    with pytest.raises(ValueError, match="integrity"):
        download("https://example.invalid/data", path, sha256="0" * 64, size=len(content))
    assert path.read_bytes() == content


def test_deepseek_search_and_fetch_share_request_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "private-fixture")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "2")
    calls = []
    def post(url, payload, key):
        assert key == "private-fixture"
        if len(calls)>=2:raise tools.budget_exhausted(2)
        calls.append((url, payload))
        return dict(results=[],web_budget=dict(used=len(calls),limit=2,remaining=2-len(calls)))
    monkeypatch.setattr(tools, "json_post", post)
    tools.deepseek_web("search", "sqlite")
    tools.deepseek_web("fetch", "https://www.sqlite.org/lang_select.html")
    assert calls[0][0].endswith("/v1/tools/search") and calls[0][1]["count"] == 10
    assert calls[1][0].endswith("/v1/tools/fetch")
    with pytest.raises(tools.WebBudgetExhausted, match="budget exhausted"):
        tools.deepseek_web("search", "next")
    assert len(calls) == 2
    with pytest.raises(ValueError, match="1-128"):
        tools.deepseek_web("search", "x" * 129)
    with pytest.raises(ValueError, match="without credentials"):
        tools.deepseek_web("fetch", "https://user:password@example.invalid/")


def test_web_responses_lead_with_run_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "private-fixture")
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "3")
    calls=[]
    def response(*a):
        calls.append(1)
        return dict(results=[1],web_budget=dict(used=len(calls),limit=3,remaining=3-len(calls),scope=tools.BUDGET_SCOPE))
    monkeypatch.setattr(tools,'json_post',response)
    first = tools.deepseek_web("search", "sqlite")
    second = tools.deepseek_web("fetch", "https://www.sqlite.org/")
    assert list(first)[0] == "web_budget" and first["results"] == [1]
    assert first["web_budget"] == dict(used=1, limit=3, remaining=2, scope=tools.BUDGET_SCOPE)
    assert second["web_budget"]["remaining"] == 1
    assert tools.with_budget([1], first["web_budget"]) == dict(web_budget=first["web_budget"], response=[1])


def test_exhausted_budget_is_final_shared_and_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "private-fixture")
    monkeypatch.setenv("MAS_BENCHMARK_WEB", "1")
    monkeypatch.setenv("MAS_WEB_PROVIDER", "deepseek")
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "1")
    calls = []
    def response(*a):
        if calls:raise tools.budget_exhausted(1)
        calls.append(a)
        return dict(results=[],web_budget=dict(used=1,limit=1,remaining=0))
    monkeypatch.setattr(tools,'json_post',response)
    assert tools.main(["search", "--query", "sqlite"]) == 0
    assert '"web_budget"' in capsys.readouterr().out
    assert tools.main(["fetch", "--url", "https://www.sqlite.org/"]) == 3
    captured = capsys.readouterr()
    assert captured.out == "" and "Traceback" not in captured.err
    message = captured.err.strip()
    assert "\n" not in message and "all 1 web requests for this run" in message
    for phrase in ("shared by every agent and process", "No request was sent", "do not retry"):
        assert phrase in message
    assert len(calls) == 1


def test_gateway_exhaustion_maps_to_same_final_message(monkeypatch):
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "4")
    reply = json.dumps(dict(error=dict(type="run_web_limit_exhausted"))) + "\n429"
    monkeypatch.setattr(tools.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=reply))
    with pytest.raises(tools.WebBudgetExhausted, match="all 4 web requests for this run"):
        tools.json_post("http://127.0.0.1/example", {}, "synthetic-token")
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "not-a-number")
    with pytest.raises(tools.WebBudgetExhausted, match="all web requests for this run"):
        tools.json_post("http://127.0.0.1/example", {}, "synthetic-token")
