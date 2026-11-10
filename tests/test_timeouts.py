from types import SimpleNamespace

import pytest

from benchmarks.policy import TIMEOUT_SECONDS_BY_BENCHMARK, default_timeout, timeout_policy


@pytest.mark.parametrize("benchmark,seconds,provisional", [
    ("dataclawbench", 1200, False),
    ("hybriddeepresearch", 1800, True),
    ("kramabench", 3600, True),
    ("fdabench", 1800, True),
])
def test_timeout_defaults_and_provenance(benchmark, seconds, provisional):
    assert default_timeout(benchmark) == seconds
    policy = timeout_policy(benchmark)
    assert policy["default_seconds"] == policy["effective_seconds"] == seconds
    assert policy["overridden"] is False
    assert (policy["default_basis"] == "engineering_provisional") is provisional
    if not provisional:
        assert "dataclaw/eval/run_batch.py" in policy["source"]
        assert policy["source_revision"] == "32e138750ceba41b47290211403ad1781d5e1971"
    else:
        assert policy["source_revision"] is None


@pytest.mark.parametrize("benchmark", tuple(TIMEOUT_SECONDS_BY_BENCHMARK))
def test_explicit_historical_timeout_is_preserved(benchmark):
    policy = timeout_policy(benchmark, 900)
    assert policy["effective_seconds"] == 900
    assert policy["overridden"] is True
    assert policy["default_seconds"] == default_timeout(benchmark)


@pytest.mark.parametrize("seconds", [0, -1, True, 1.5, "900"])
def test_invalid_timeout_values_rejected(seconds):
    with pytest.raises(ValueError, match="positive integer"):
        timeout_policy("dataclawbench", seconds)


def test_unknown_benchmark_rejected():
    with pytest.raises(ValueError, match="Unknown benchmark"):
        default_timeout("unknown")


@pytest.mark.parametrize("benchmark,expected", [("dataclawbench", 1200), ("hybriddeepresearch", 1800), ("fdabench", 1800)])
@pytest.mark.parametrize("override", [None, 900])
def test_common_cli_resolves_default_without_changing_override(tmp_path, monkeypatch, benchmark, expected, override):
    from scripts.common import run
    captured = {}
    monkeypatch.setattr(run, "load", lambda args: [])

    def plan(args, tasks):
        captured["timeout"] = args.timeout
        return dict(timeout=args.timeout)

    monkeypatch.setattr(run, "plan", plan)
    argv = ["--benchmark", benchmark, "--upstream", str(tmp_path / "upstream"),
            "--data", str(tmp_path / "data"), "--output", str(tmp_path / "output"),
            "--backend", "claude-code-single-agent", "--image", "fixture", "--task-id", "fixture"]
    if benchmark in {"hybriddeepresearch", "fdabench"}:
        argv += ["--tasks", str(tmp_path / "release.jsonl")]
    if override is not None:
        argv += ["--timeout", str(override)]
    assert run.main(argv) == 0
    assert captured["timeout"] == (expected if override is None else override)


@pytest.mark.parametrize("override,expected", [(None, 3600), (900, 900)])
def test_krama_cli_timeout_default_and_override(tmp_path, monkeypatch, override, expected):
    from scripts.kramabench import run
    captured = {}
    task = SimpleNamespace(id="fixture")
    monkeypatch.setattr(run, "load_tasks", lambda upstream: ([task], {}))

    def freeze(args):
        captured["timeout"] = args.timeout
        return [task], {}

    monkeypatch.setattr(run, "freeze", freeze)
    argv = ["--backend", "claude-code-single-agent", "--upstream", str(tmp_path / "upstream"),
            "--output", str(tmp_path / "output"), "--offline-proof", str(tmp_path / "proof.json")]
    if override is not None:
        argv += ["--timeout", str(override)]
    run.main(argv)
    assert captured["timeout"] == expected
