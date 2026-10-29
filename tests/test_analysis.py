import json

import pytest

from mas_info.analysis import criteria, stats
from mas_info.analysis.loss_judge import build_case, parse_label, render
from mas_info.llm import ProviderError
from mas_info.runner import RunSpec, prepare_output, run_batch


def test_mcnemar_exact():
    base = {str(i): True for i in range(5)} | {"x": False}
    other = {str(i): False for i in range(5)} | {"x": False}
    result = stats.mcnemar(base, other)
    assert result == {"n": 6, "base_only": 5, "other_only": 0, "p_value": 0.0625}
    assert stats.mcnemar(base, base)["p_value"] == 1.0


def test_pass_hat_k_and_oracle():
    trials = {"a": [True, True, False], "b": [True, True, True]}
    assert stats.pass_hat_k(trials, 1) == pytest.approx((2 / 3 + 1) / 2)
    assert stats.pass_hat_k(trials, 3) == pytest.approx(0.5)
    success = {"C1": {"t1": True, "t2": False}, "C2": {"t1": False, "t2": True}}
    result = stats.oracle(success, ["C1", "C2"])
    assert result["oracle"] == 1.0 and result["gain"] == 0.5


def test_bootstrap_is_reproducible():
    values = [1.0, 0.0, 1.0, 1.0]
    assert stats.bootstrap_ci(values, seed=3) == stats.bootstrap_ci(values, seed=3)
    low, high = stats.bootstrap_ci(values)
    assert 0.0 <= low <= 0.75 <= high <= 1.0


def test_kappa():
    assert stats.cohen_kappa(["a", "b"], ["a", "b"]) == 1.0
    assert stats.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


def test_criteria_need_evidence_before_passing():
    summary = {"success_rate": {"C0": 0.6, "C1": 0.5, "C3": 0.58}, "paired": {}}
    verdict = criteria.evaluate({"bcp": summary})
    assert verdict["P1"]["status"] == "pass"
    assert verdict["P2"]["status"] == "pending"  # detector precision needs human labels
    assert verdict["P3"]["status"] == "pending"
    assert criteria.evaluate({})["P1"]["status"] == "pending"


def test_loss_judge_case_and_parse():
    events = [
        {"t": 0, "type": "message", "agent": "lead", "message": {"role": "system", "content": "sys"}},
        {"t": 1, "type": "message", "agent": "search_1", "message": {"role": "tool", "tool_call_id": "c", "content": "born 1950"}},
        {"t": 2, "type": "final", "agent": "lead"},
        {"t": 3, "type": "message", "agent": "lead", "message": {"role": "user", "content": "late"}},
    ]
    case = build_case(events, "Birth year 1950")
    assert "born 1950" in case["other_contexts"] and "late" not in case["decider_context"]
    assert render([{"role": "user", "content": "x" * 50}], 20).count("omitted") == 1
    label = parse_label('```json\n{"loss_type": "omission", "edge": "search_1->lead", "direction": "up"}\n```')
    assert label["loss_type"] == "omission"
    assert parse_label('{"loss_type": "unknown"}') is None


def test_runner_keeps_errors_apart_and_reruns_them(tmp_path):
    spec = RunSpec("bcp", "7", "C1", 0)
    prepare_output(tmp_path, {"setup": 1})
    with pytest.raises(RuntimeError):
        prepare_output(tmp_path, {"setup": 2})

    def failing(spec, trace):
        raise ProviderError("http_400", "missing reasoning_content", 400)

    assert run_batch([spec], failing, tmp_path, 1) == {"error": 1}
    result = json.loads((tmp_path / "results" / f"{spec.run_id}.json").read_text())
    assert result["error"]["http_status"] == 400

    def succeeding(spec, trace):
        trace.emit("final", agent="lead")
        return {"status": "completed"}

    assert run_batch([spec], succeeding, tmp_path, 1) == {"completed": 1}
    assert len(list((tmp_path / "traces" / "attempts").glob("*.jsonl"))) == 1
    assert run_batch([spec], succeeding, tmp_path, 1) == {}  # finished runs are kept


def test_run_ids_are_file_safe():
    assert RunSpec("bcp", "769", "C1", 0).run_id == "bcp_q769_C1_r0"
    run_id = RunSpec("telecom", "[mobile_data]airplane|on", "C0", 2).run_id
    assert run_id.startswith("telecom_qmobile-data-airplane-on-") and run_id.endswith("_C0_r2")
