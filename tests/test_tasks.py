import json

import pytest

from benchmarks.kramabench.tasks import DOMAINS, Task, UPSTREAM_COMMIT, load_tasks, public_tasks


def test_public_tasks_do_not_export_reference_fields():
    rows = [dict(id="task-1", query="Public question", answer="PRIVATE", answer_type="string_exact",
                 reference_code="PRIVATE", subtasks=["PRIVATE"])]
    assert vars(public_tasks(rows, DOMAINS[0])[0]) == dict(
        id="task-1", domain=DOMAINS[0], query="Public question")
    with pytest.raises(ValueError, match="Duplicate"):
        public_tasks(rows + rows, DOMAINS[0])


@pytest.mark.parametrize("task_id,domain,query", [
    ("../escape", "legal", "question"), ("valid", "unknown", "question"), ("valid", "legal", " "),
])
def test_invalid_public_tasks(task_id, domain, query):
    with pytest.raises(ValueError):
        Task(task_id, domain, query)


def test_pinned_workload_validation(tmp_path, monkeypatch):
    import benchmarks.kramabench.tasks as tasks
    source = {}
    for domain in DOMAINS:
        relative = f"workload/{domain}.json"
        data = json.dumps([dict(id=domain + "-1", query="question", answer="private")]).encode()
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        source[relative] = data
    def git(args):
        return (UPSTREAM_COMMIT + "\n").encode() if args[-2:] == ["rev-parse", "HEAD"] else source[
            args[-1].split(":", 1)[1]]
    monkeypatch.setattr(tasks.subprocess, "check_output", git)
    public, provenance = load_tasks(tmp_path)
    assert len(public) == len(DOMAINS) and provenance["commit"] == UPSTREAM_COMMIT
    (tmp_path / "workload/legal.json").write_text("[]")
    with pytest.raises(ValueError, match="Modified workload"):
        load_tasks(tmp_path)
