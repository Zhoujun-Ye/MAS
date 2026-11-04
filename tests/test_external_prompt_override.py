from types import SimpleNamespace

import pytest

from scripts.common.run import instructions
from scripts.common.runtime import limit_instructions, organization_override


@pytest.mark.parametrize("benchmark", ["dataclawbench", "hybriddeepresearch"])
def test_lead_override_preserves_benchmark_rules(tmp_path, benchmark):
    path = tmp_path / "prompt.txt"
    path.write_text("CUSTOM_LEAD_PROMPT")
    override = organization_override(path, "claude-code-subagents")
    web = benchmark == "hybriddeepresearch"
    task = SimpleNamespace(benchmark=benchmark, db="fixture", web=web)
    limits = dict(timeout=1800, web_limit=4 if web else 0)
    default = instructions(task, "claude-code-subagents", **limits)
    changed = instructions(task, "claude-code-subagents", override, **limits)
    assert changed.endswith("CUSTOM_LEAD_PROMPT")
    assert changed.split("CUSTOM_LEAD_PROMPT")[0] == default.split("Use Claude Code")[0]
    assert "Do not install packages" in changed
    assert "/data" in changed
    # Run limits belong to the shared task rules, so an override cannot drop them.
    assert limit_instructions(**limits) in changed
    with pytest.raises(ValueError):
        organization_override(path, "claude-code-single-agent")
