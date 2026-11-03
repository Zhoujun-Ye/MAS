from scripts.kramabench.scoped_subagents_pilot import metrics, select_tasks


def test_selection_is_balanced_order_invariant_and_ignores_answers():
    tasks = [dict(id=f"{domain}-{level}-{i}", answer=i) for domain in
             ("archeology", "astronomy", "biomedical", "environment", "legal", "wildfire")
             for level in ("easy", "hard") for i in range(1, 5)]
    chosen = select_tasks(tasks)
    assert len(chosen) == len(set(chosen)) == 24
    assert chosen == select_tasks(list(reversed(tasks)))
    assert chosen == select_tasks([dict(t, answer="changed") for t in tasks])
    for domain in {t["id"].split("-")[0] for t in tasks}:
        for level in ("easy", "hard"):
            assert sum(i.startswith(domain + "-" + level + "-") for i in chosen) == 2


def test_missing_usage_and_grade_are_not_zero_cost_or_correctness():
    row = dict(status="cli_error", grade=dict(score_kind="binary", score=None))
    result = metrics([row])
    assert result["binary_n"] == 1
    assert result["binary_graded"] == result["binary_correct"] == 0
    assert result["estimate_usd_offpeak"] is None
    assert result["mean_cli_seconds"] is None
