import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.common import tools
from scripts.server.prepare_data import download


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


def test_search_is_bounded_basic_and_key_not_in_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "private-fixture")
    monkeypatch.setenv("MAS_WEB_LEDGER", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "1")
    calls = []
    def invoke(command, **kwargs):
        calls.append(command)
        assert "private-fixture" not in " ".join(command)
        assert 'search_depth' in kwargs["input"] and 'basic' in kwargs["input"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(results=[], usage=dict(credits=1))) + "\n200")
    monkeypatch.setattr(tools.subprocess, "run", invoke)
    assert tools.tavily_search("fixture")["usage"]["credits"] == 1
    with pytest.raises(ValueError, match="budget exhausted"):
        tools.tavily_search("second")
    assert len(calls) == 1
    assert "fixture" not in (tmp_path / "usage.jsonl").read_text()


def test_failed_search_is_reserved_and_not_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "private-fixture")
    monkeypatch.setenv("MAS_WEB_LEDGER", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "1")
    monkeypatch.setattr(tools.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=28))
    with pytest.raises(RuntimeError, match="not retried"):
        tools.tavily_search("fixture")
    with pytest.raises(ValueError, match="budget exhausted"):
        tools.tavily_search("fixture")


def test_deepseek_search_and_fetch_share_request_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "private-fixture")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("MAS_WEB_LEDGER", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("MAS_WEB_MAX_REQUESTS", "2")
    calls = []
    def post(url, payload, key):
        assert key == "private-fixture"
        calls.append((url, payload))
        return dict(results=[])
    monkeypatch.setattr(tools, "json_post", post)
    tools.deepseek_web("search", "sqlite")
    tools.deepseek_web("fetch", "https://www.sqlite.org/lang_select.html")
    assert calls[0][0].endswith("/v1/tools/search") and calls[0][1]["count"] == 5
    assert calls[1][0].endswith("/v1/tools/fetch")
    with pytest.raises(ValueError, match="budget exhausted"):
        tools.deepseek_web("search", "next")
    assert len(calls) == 2
    with pytest.raises(ValueError, match="1-128"):
        tools.deepseek_web("search", "x" * 129)
    with pytest.raises(ValueError, match="without credentials"):
        tools.deepseek_web("fetch", "https://user:password@example.invalid/")
