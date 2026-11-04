import hashlib
import json

import pytest

from scripts.studies.compare_claude_single import compare
from scripts.kramabench.results import summarize


def fixture(tmp_path):
    root = tmp_path/"native"
    folder = root/"a-easy-1/claude-code-single-agent"
    folder.mkdir(parents=True)
    payload = b'{"answer":1}'
    (folder/"submission.json").write_bytes(payload)
    scoring = dict(version="scale_aware_answer_metrics_v3")
    row = dict(task_id="a-easy-1", backend="claude-code-single-agent", status="cli_exited",
        single_agent_audit=dict(passed=True, subagent_starts=0, executed_delegation_tools=0),
        single_agent_transcript_audit=dict(member_messages=0),
        grade=dict(score=1, score_kind="binary", answer_type="numeric_exact", metric="success",
                   scoring_contract=scoring, submission_file_sha256=hashlib.sha256(payload).hexdigest()))
    (root/"summary.json").write_text(json.dumps(dict(plan=dict(scoring=scoring), rows=[row])))
    (root/"progress.json").write_text('{"stage":"finished"}')
    base_rows = [dict(row, backend=b) for b in ("deepagents", "claude-code-agent-team", "claude-code-subagents")]
    baseline = tmp_path/"baseline.json"
    baseline.write_text(json.dumps(dict(rows=base_rows, scoring=scoring,
        cohorts={n:summarize([r]) for n,r in zip(("single", "team", "subagents"),base_rows)})))
    return baseline, root


def test_four_conditions_are_matched_and_native_evidence_is_not_changed(tmp_path):
    baseline, root = fixture(tmp_path)
    original = (root/"summary.json").read_bytes()
    result = compare(baseline, root, tmp_path/"comparison", expected_tasks=1)
    assert len(result["rows"]) == 4
    assert result["cohorts"]["claude_single"]["native_subagent_starts"] == 0
    assert result["new_judge_calls"] == result["new_solver_calls"] == 0
    assert original == (root/"summary.json").read_bytes()


@pytest.mark.parametrize("violation", ["artifact", "delegation", "missing_transcript", "scoring", "incomplete"])
def test_invalid_four_condition_comparison_is_rejected(tmp_path, violation):
    baseline, root = fixture(tmp_path)
    path = root/"summary.json"
    value = json.loads(path.read_text())
    if violation == "artifact":
        (root/"a-easy-1/claude-code-single-agent/submission.json").write_text('{}')
    elif violation == "delegation":
        value["rows"][0]["single_agent_audit"]["subagent_starts"] = 1
    elif violation == "missing_transcript":
        value["rows"][0].pop("single_agent_transcript_audit")
    elif violation == "scoring":
        value["plan"]["scoring"] = {}
    else:
        value["rows"] = []
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        compare(baseline, root, tmp_path/"comparison", expected_tasks=1)
    assert not (tmp_path/"comparison").exists()
