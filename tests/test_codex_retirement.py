import json

from scripts.server.retire_codex_results import clean


def test_retirement_is_scoped_and_preserves_claude(tmp_path):
    for name in ["claude-code-subagents", "codex-subagents"]:
        folder = tmp_path / "solvers" / name
        folder.mkdir(parents=True)
        (folder / "raw.txt").write_text(name)
    index = tmp_path / "summary.json"
    index.write_text(json.dumps(dict(rows=[dict(backend=b, score=1) for b in ["claude-code-subagents", "codex-subagents"]])))
    clean(tmp_path)
    assert (tmp_path / "solvers/codex-subagents/raw.txt").exists()
    result = clean(tmp_path, execute=True)
    assert (tmp_path / "solvers/claude-code-subagents/raw.txt").read_text() == "claude-code-subagents"
    assert not (tmp_path / "solvers/codex-subagents").exists()
    assert json.loads(index.read_text())["rows"] == [dict(backend="claude-code-subagents", score=1)]
    assert len(result["deleted"]) == 1
    assert clean(tmp_path)["deleted"] == []
