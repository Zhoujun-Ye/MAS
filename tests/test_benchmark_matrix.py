import json
from types import SimpleNamespace

import pytest

from scripts.studies import benchmark_matrix as matrix


def selected_tasks():
    return [(bench, SimpleNamespace(id=f"task-{index}", category=category, query="Fixture question"))
            for bench, categories in (
                ("dataclawbench", (None, None)),
                ("hybriddeepresearch", ("search_to_sql", "sql_to_search")),
                ("kramabench", (None, None)),
            ) for index, category in enumerate(categories)]


def cli_args(tmp_path, *extra):
    return ["--root", str(tmp_path / "data"), "--output", str(tmp_path / "output"),
            "--proofs", str(tmp_path / "proofs"), "--image", "fixture-image", *extra]


def test_matched_manifest_freezes_four_ids_without_relaxing_validation20(tmp_path,monkeypatch):
    tasks=[SimpleNamespace(id=f'FDA{i}',category='single_choice',query='Fixture') for i in range(6)]
    monkeypatch.setattr(matrix,'task_pools',lambda *a:{'fdabench':tasks})
    monkeypatch.setattr(matrix,'task_fingerprint',lambda b,t:'hash-'+t.id)
    manifest=dict(kind='matched-study-v1',benchmarks={'fdabench':[
        dict(task_id=t.id,task_sha256='hash-'+t.id) for t in tasks[:4]]})
    assert [t.id for _,t in matrix.manifest_selections(tmp_path,manifest,0,4)]==[t.id for t in tasks[:4]]
    manifest['kind']='validation20-v1'
    with pytest.raises(ValueError,match='20 unique'):
        matrix.manifest_selections(tmp_path,manifest,0,4)
    manifest['kind']='matched-study-v1'
    manifest['benchmarks']['fdabench'][0]['task_sha256']='changed'
    with pytest.raises(ValueError,match='changed or disappeared'):
        matrix.manifest_selections(tmp_path,manifest,0,4)


@pytest.mark.parametrize('mode',('full','observations','full-prompt-only'))
def test_retired_proofs_do_not_admit_baselines(mode):
    from harness.runtime_support.proof import validate
    with pytest.raises(ValueError,match='Retired'):
        validate(dict(mode=mode),'claude-code-subagents')


@pytest.mark.parametrize('condition',('full','observations','full-prompt-only'))
def test_retired_conditions_reject_before_credentials(tmp_path, monkeypatch, condition):
    monkeypatch.setattr(matrix.runtime, 'credential', lambda *a: pytest.fail('Retired condition read credentials'))
    with pytest.raises(SystemExit):
        matrix.main(cli_args(tmp_path, '--conditions', condition, '--execute'))
    with pytest.raises(ValueError,match='Only Single and Structured'):
        matrix.runtime_backend(condition)


def test_duplicate_benchmark_scope_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='unique benchmarks'):
        matrix.main(cli_args(tmp_path, '--benchmarks', 'kramabench', 'kramabench'))


def test_fdabench_choice_plan_has_no_paid_judges(tmp_path,monkeypatch,capsys):
    tasks=[('fdabench',SimpleNamespace(id=f'FDA{i}',category=c,web=True))
        for i,c in enumerate(('single_choice','multiple_choice'))]
    monkeypatch.setattr(matrix,'selections',lambda *a:tasks)
    monkeypatch.setattr(matrix.runtime,'credential',lambda *a:pytest.fail('Planning read credentials'))
    assert matrix.main(cli_args(tmp_path,'--benchmarks','fdabench'))==0
    plan=json.loads(capsys.readouterr().out)
    assert plan['attempts']==4
    assert plan['maximum_judge_calls']==0


def test_plan_is_exact_12_scope_and_never_executes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(matrix, "selections", lambda *args: selected_tasks())
    monkeypatch.setattr(matrix.subprocess, "Popen", lambda *a, **kw: pytest.fail("Plan must not launch processes"))
    monkeypatch.setattr(matrix.runtime, "credential", lambda *a: pytest.fail("Plan must not load credentials"))
    assert matrix.main(cli_args(tmp_path)) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["attempts"] == 12
    assert plan["maximum_judge_calls"] == 10
    assert plan["retries"] == 0
    assert plan["timeout_seconds_by_benchmark"] == {
        "dataclawbench": 1200, "hybriddeepresearch": 1800, "kramabench": 3600}
    assert plan["solver_concurrency"] == 8 and plan["judge_concurrency"] == 2
    assert len({(r["benchmark"], r["task_id"], r["backend"]) for r in plan["selections"]}) == 12
    for benchmark in ("dataclawbench", "hybriddeepresearch", "kramabench"):
        rows = [r for r in plan["selections"] if r["benchmark"] == benchmark]
        assert len(rows) == 4
        assert len({r["task_id"] for r in rows}) == 2
        assert {r["backend"] for r in rows} == set(matrix.BACKENDS)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("execute", [False, True])
def test_all_solver_commands_share_scope_and_benchmark_timeout(tmp_path, execute):
    args = SimpleNamespace(root=tmp_path / "data", proofs=tmp_path / "proofs", image="immutable-image",
                           credentials=tmp_path / "private.env")
    for benchmark, task in selected_tasks():
        for backend in matrix.BACKENDS:
            output = tmp_path / "results" / benchmark / task.id / backend
            command = matrix.solver_command(args, benchmark, task, backend, output, execute=execute)
            expected = {"dataclawbench": "1200", "hybriddeepresearch": "1800", "kramabench": "3600"}
            assert command[command.index("--timeout") + 1] == expected[benchmark]
            assert command.count("--task-id") == 1
            assert command[command.index("--task-id") + 1] == task.id
            assert command[command.index("--credentials") + 1] == str(args.credentials)
            assert command[command.index("--offline-proof") + 1] == str(args.proofs / backend / "proof.json")
            assert ("--execute" in command) is execute
            assert all("API_KEY" not in part and "AUTH_TOKEN" not in part for part in command)
            if benchmark == "kramabench":
                assert ("--from-plan" in command) is execute
                assert command[command.index("--judge-limit") + 1] == "0"
                assert command[command.index("--concurrency") + 1] == "1"
            else:
                assert command[command.index("--authorized-attempts") + 1] == "1"
            if benchmark == "hybriddeepresearch":
                assert command[command.index("--web-search") + 1] == "deepseek"
                assert command[command.index("--max-web-requests") + 1] == "20"


@pytest.mark.parametrize("attempts,judges", [(11, 10), (13, 10), (12, 11), (12, -1)])
def test_execution_rejects_other_authorization_scope(tmp_path, monkeypatch, attempts, judges):
    monkeypatch.setattr(matrix, "selections", lambda *args: selected_tasks())
    monkeypatch.setattr(matrix.subprocess, "Popen", lambda *a, **kw: pytest.fail("Invalid scope must not launch"))
    monkeypatch.setattr(matrix.runtime, "credential", lambda *a: pytest.fail("Invalid scope must not load credentials"))
    with pytest.raises(ValueError, match="12 authorized solvers"):
        matrix.main(cli_args(tmp_path, "--execute", "--authorized-attempts", str(attempts),
                             "--authorized-judges", str(judges)))
    assert not (tmp_path / "output").exists()


def test_selection_uses_public_categories_without_reference_access(tmp_path, monkeypatch):
    dc = [SimpleNamespace(id="web", web=True,category='a'), SimpleNamespace(id="dc1", web=False,category='b'),
          SimpleNamespace(id="dc2", web=False,category='a'), SimpleNamespace(id="dc3", web=False,category='b')]
    hdr = [SimpleNamespace(id="text", category="sql_to_search"),
           SimpleNamespace(id="sql", category="search_to_sql")]
    krama = [SimpleNamespace(id="k1",domain='a'), SimpleNamespace(id="k2",domain='b'), SimpleNamespace(id="k3",domain='a')]
    monkeypatch.setattr(matrix, "dc_tasks", lambda path: dc)
    monkeypatch.setattr(matrix, "hdr_tasks", lambda path: hdr)
    monkeypatch.setattr(matrix, "krama_tasks", lambda path: (krama, {}))
    selected=matrix.selections(tmp_path)
    assert len(selected)==6
    assert {t.category for b,t in selected if b=='dataclawbench'}=={'a','b'}
    assert {t.category for b,t in selected if b=='hybriddeepresearch'}=={'search_to_sql','sql_to_search'}
    assert {t.domain for b,t in selected if b=='kramabench'}=={'a','b'}
    dc.reverse();krama.reverse()
    assert selected==matrix.selections(tmp_path)


def test_seeded_sample_is_balanced_reproducible_and_input_order_independent():
    tasks = [SimpleNamespace(id=f"{category}-{i}", category=category)
             for category in ("a", "b", "c") for i in range(20)]
    sample = lambda values, seed=42: matrix.balanced_sample(values, 10, lambda t: t.category, seed)
    first = sample(tasks)
    assert [t.id for t in first] == [t.id for t in sample(list(reversed(tasks)))]
    assert len({t.id for t in first}) == 10
    assert sorted(sum(t.category == c for t in first) for c in ("a", "b", "c")) == [3, 3, 4]
    assert [t.id for t in first] != [t.id for t in sample(tasks, 43)]
    with pytest.raises(ValueError, match="Not enough tasks"):
        sample(tasks[:2])


def test_ten_task_plan_is_matched_and_has_bounded_judges(tmp_path, monkeypatch, capsys):
    tasks = [(bench, SimpleNamespace(id=f"task-{i}", category="search_to_sql" if i < 4 else "sql_to_search"))
             for bench in ("dataclawbench", "hybriddeepresearch", "kramabench") for i in range(10)]
    monkeypatch.setattr(matrix, "selections", lambda root, count, seed, benchmarks=matrix.BENCHMARKS: tasks)
    monkeypatch.setattr(matrix.subprocess, "Popen", lambda *a, **kw: pytest.fail("Plan must not launch"))
    assert matrix.main(cli_args(tmp_path, "--tasks-per-benchmark", "10", "--sample-seed", "42")) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["attempts"] == 60 and plan["maximum_judge_calls"] == 52
    for bench in ("dataclawbench", "hybriddeepresearch", "kramabench"):
        paired = [{r["task_id"] for r in plan["selections"] if r["benchmark"] == bench and r["backend"] == backend}
                  for backend in matrix.BACKENDS]
        assert paired[0] == paired[1] and len(paired[0]) == 10


def test_dataclaw_web_selection_gets_explicit_web_budget(tmp_path):
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path, image="fixture", credentials=tmp_path / "private.env")
    command = matrix.solver_command(args, "dataclawbench", SimpleNamespace(id="web", web=True),
                                    matrix.BACKENDS[0], tmp_path / "output")
    assert command[command.index("--web-search") + 1] == "deepseek"
    assert command[command.index("--max-web-requests") + 1] == "20"
