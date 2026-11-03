import json

import pytest

from scripts.kramabench.cli_runtime import balance_deltas, credential, native_env, options, submission
from scripts.kramabench.native_evidence import read_evidence


def test_scope_and_no_secrets_in_native_plan():
    assert options("deepagents")["single_agent"] is True
    assert options("deepagents")["max_turns"] == 500
    assert not any("KEY" in key or "TOKEN" in key for key in native_env("both")
                   if key not in {"CLAUDE_CODE_MAX_OUTPUT_TOKENS"})
    assert options("deepagents")["model"] == "anthropic:deepseek-flash"
    assert options("claude-code-agent-team")["model"] == "deepseek-flash[1m]"
    assert native_env("claude-code-agent-team")["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"
    assert native_env("claude-code-subagents")["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "0"


def test_protected_credentials_are_not_shell_executed(tmp_path):
    path = tmp_path / "private.env"
    path.write_text("# example\nDEEPSEEK_API_KEY='literal;$(not-executed)'\n")
    path.chmod(0o600)
    assert credential(path) == "literal;$(not-executed)"
    path.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        credential(path)


def test_submission_path_and_shape(tmp_path):
    payload = dict(answer=1, pipeline_path="pipeline.py", evidence="checked", unfinished=[])
    (tmp_path / "pipeline.py").write_text("print(1)")
    (tmp_path / "submission.json").write_text(json.dumps(payload))
    assert submission(tmp_path) == payload
    (tmp_path / "pipeline.py").unlink()
    (tmp_path / "pipeline.py").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="Symlink"):
        submission(tmp_path)


def test_native_usage_deduplicates_claude_message_chunks_and_tools(tmp_path):
    path = tmp_path / "leader.jsonl"
    first = dict(role="assistant", id="m1", model="deepseek-flash",
                 usage=dict(input_tokens=100, cache_read_input_tokens=200, output_tokens=5),
                 content=[dict(type="tool_use", id="t1", name="TeamCreate", input={})])
    last = dict(first, usage=dict(input_tokens=100, cache_read_input_tokens=200, output_tokens=20),
                content=[dict(type="tool_use", id="t2", name="Agent", input={})])
    path.write_text("\n".join(json.dumps(dict(message=m)) for m in [first, last, last]))
    result = read_evidence(tmp_path, "claude-code")
    assert result["observed_totals"] == dict(input_tokens=300, output_tokens=20, cache_hit_tokens=200)
    assert result["tools"] == dict(TeamCreate=1, Agent=1)
    assert result["by_role"]["leader"]["token_weighted_cache_hit_rate"] == pytest.approx(2/3)
    assert result["estimated_usd_off_peak"] > 0


def test_missing_native_accounting_is_unknown(tmp_path):
    result = read_evidence(tmp_path, "claude-code")
    assert result["estimated_usd_off_peak"] is None
    assert result["observed_delegation_calls"] == 0


def test_non_usd_balances_are_not_silently_zero():
    def receipt(amount):
        return dict(response=dict(balance_infos=[dict(currency="CNY", total_balance=amount)]))
    assert balance_deltas(receipt("30.00"), receipt("23.90")) == {"CNY": "6.10"}
