"""Whole external-benchmark workflows with fake CLI/container boundaries only."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks._external import digest, jsonl
from scripts.common import run, score
from harness.runtime_support.proof import validate


@pytest.fixture(params=["dataclawbench", "hybriddeepresearch", "fdabench"])
def workflow(tmp_path, monkeypatch, request):
    from harness.runtime_support import preflight
    monkeypatch.setattr(preflight,'check',lambda *a,**kw:dict(paid_calls=0))
    monkeypatch.setattr('harness.runtime_support.web_fetch.check_ready',lambda *a, **kw:dict(tls_verified=True,model_calls=0))
    benchmark = request.param
    monkeypatch.setattr(run, "verify_sources", lambda *args: None)
    monkeypatch.setattr(score, "verify_sources", lambda *args: None)
    class FakeGateway:
        url = "http://127.0.0.1:1"
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(run, "CredentialGateway", FakeGateway)
    upstream = tmp_path / "upstream"
    qa = upstream / "assets/qa_raw/enterprise"
    qa.mkdir(parents=True)
    for index in range(2):
        (qa / f"easy{index}_result.json").write_text(json.dumps(dict(
            id=f"easy{index}", question="Compute x", guidelines="Return text", answer="PRIVATE_GOLD",
            metadata=dict(level="easy"))))
    data = upstream / "assets/database"
    data.mkdir()
    (data / "x.csv").write_text("x\n1\n")
    (upstream / "dataclaw").mkdir()
    (upstream / "dataclaw/build_tasks.py").write_text("# fixture evaluator")
    task_file = tmp_path / "tasks.jsonl"
    if benchmark == "hybriddeepresearch":
        import sqlite3
        data = tmp_path / "databases"
        folder = data / "retail"
        folder.mkdir(parents=True)
        with sqlite3.connect(folder / "retail_template.sqlite") as db:
            db.execute("CREATE TABLE x (n INTEGER)")
        task_file.write_text("\n".join(json.dumps(dict(id=f"task{index}", db="retail",
            hybrid_type=kind, final_question="Compute x", final_answer="PRIVATE_GOLD", sql="SELECT 1"))
            for index, kind in enumerate(("search_to_sql", "sql_to_search"))))
        (upstream / "evaluation").mkdir()
        (upstream / "evaluation/s2sql_eval.py").write_text("# fixture evaluator")
    if benchmark == "fdabench":
        import sqlite3
        data = tmp_path / "databases"
        folder = data / "bird/retail"
        folder.mkdir(parents=True)
        with sqlite3.connect(folder / "retail.sqlite") as db:
            db.execute("CREATE TABLE x (n INTEGER)")
        task_file.write_text("\n".join(json.dumps(dict(task_id=f"FDA{index:04d}", instance_id="bird1",
            db="retail", database_type="bird", question_type="single_choice", query="Compute x",
            options={"A":"1", "B":"2"}, correct_answer=["A"], tools_available=["execute_sql"],
            explanation="PRIVATE_GOLD")) for index in range(2)))
        (upstream / "FDABench/evaluation").mkdir(parents=True)
        (upstream / "FDABench/evaluation/rubric_evaluator.py").write_text("# fixture evaluator")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("DEEPSEEK_API_KEY=fake-never-sent")
    credentials.chmod(0o600)
    binary = tmp_path / "fake-claude"
    binary.write_text("fake executable, never launched")
    proof = tmp_path / "proof.json"
    from harness._claude_hooks import SUBAGENT_TOOLS
    from harness.runtime_support.proof import runtime_configuration
    proof.write_text(json.dumps(dict(passed=True, paid_calls=0, network="none",
        native_surface=dict(tools=list(SUBAGENT_TOOLS), skills=[], slash_commands=[]),
        runtime_configuration_sha256=runtime_configuration('claude-code-subagents'),
        requested_effort=run.runtime.DEFAULT_EFFORT, request_effort_verified=True,
        inference_policy=run.runtime.inference_configuration(), request_configuration_verified=True,
        backend="claude-code-subagents", native_subagents=dict(passed=True, subagent_starts=1,
        native_team_configs=0, teammate_idle_events=0),
        runtime_binding=dict(image_id="sha256:fake", binary_sha256=digest(binary)))))
    monkeypatch.setattr(run.runtime, "CLAUDE", binary)
    monkeypatch.setattr(run.runtime, "source_files", lambda: iter([(Path("fake.py"), binary)]))
    def check_output(command, **kwargs):
        if command[0] == "git":
            return (run.fda.REVISION if benchmark == "fdabench" else run.DC_REVISION if benchmark == "dataclawbench" else run.HDR_REVISION) + "\n"
        if command[:3] == ["docker", "network", "inspect"]:
            return b'[{"IPAM":{"Config":[{"Gateway":"127.0.0.1"}]}}]'
        assert command[:3] == ["docker", "image", "inspect"]
        return b'[{"Id":"sha256:fake"}]'
    monkeypatch.setattr(run.subprocess, "check_output", check_output)
    def subprocess_run(command, **kwargs):
        if command[:2] == ["docker", "rm"]:
            return SimpleNamespace(returncode=0)
        assert "native_evidence.py" in command[2]
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(observed_messages=1)))
    monkeypatch.setattr(run.subprocess, "run", subprocess_run)
    calls = []
    class FakeCLI:
        def __init__(self, executable):
            pass

        def run(self, prompt, *, workspace, output, **kwargs):
            calls.append(prompt)
            assert "PRIVATE_GOLD" not in prompt
            output.mkdir(parents=True)
            (workspace / "submission.json").write_text(json.dumps(dict(final_answer="1")))
            events = output.parent / "native-profile/observer/events.jsonl"
            events.parent.mkdir(parents=True)
            rows = [dict(hook_event_name="SessionStart", session_id="root"),
                    dict(hook_event_name="SubagentStart", agent_id="worker"),
                    dict(hook_event_name="SubagentStop", agent_id="worker"),
                    dict(hook_event_name="SessionEnd", session_id="root")]
            events.write_text("\n".join(map(json.dumps, rows)))
            return dict(status="cli_exited")
    monkeypatch.setitem(run.BACKENDS, "claude-code-subagents", FakeCLI)
    monkeypatch.setattr(run.runtime, "container", lambda *a, **kw: "fake-container")
    monkeypatch.setattr(run.runtime, "stop_container", lambda identity: dict(stopped=True))
    output = tmp_path / "run"
    argv = ["--upstream", str(upstream), "--data", str(data), "--backend", "claude-code-subagents",
            "--image", "existing", "--output", str(output), "--credentials", str(credentials),
            "--offline-proof", str(proof), "--authorized-attempts", "2"]
    if benchmark == "hybriddeepresearch":
        argv += ["--tasks", str(task_file), "--web-search", "deepseek"]
    if benchmark == "fdabench":
        argv += ["--tasks", str(task_file)]
    tasks = (run.fda.load_tasks(task_file) if benchmark == "fdabench" else
             run.dataclaw_tasks(upstream) if benchmark == "dataclawbench" else run.hybrid_tasks(task_file))
    for task in tasks:
        argv += ["--task-id", task.id]
    return SimpleNamespace(upstream=upstream, output=output, argv=argv, calls=calls,
                           benchmark=benchmark, task_file=task_file)


def test_real_preflight_freezes_resources_then_execution_reuses_plan(workflow,monkeypatch):
    from harness.runtime_support import preflight
    observed=[]
    monkeypatch.setattr(preflight,'check',lambda *a,**kw:observed.append((a,kw)) or dict(paid_calls=0))
    original=run.runtime.credential
    monkeypatch.setattr(run.runtime,'credential',lambda *a:pytest.fail('Offline preflight read credentials'))
    argv=workflow.argv+['--cpus','8','--compute-threads','4']
    assert run.main(argv+['--preflight'],benchmark=workflow.benchmark)==0
    assert len(observed)==2 and all(a[6:8]==(8,4) for a,k in observed)
    assert not workflow.calls
    monkeypatch.setattr(run.runtime,'credential',original)
    assert run.main(argv+['--from-plan','--execute'],benchmark=workflow.benchmark)==0
    assert len(workflow.calls)==2


def test_changed_frozen_resources_reject_before_credentials(workflow,monkeypatch):
    from harness.runtime_support import preflight
    monkeypatch.setattr(preflight,'check',lambda *a,**kw:dict(paid_calls=0))
    assert run.main(workflow.argv+['--preflight'],benchmark=workflow.benchmark)==0
    monkeypatch.setattr(run.runtime,'credential',lambda *a:pytest.fail('Changed plan read credentials'))
    with pytest.raises(ValueError,match='Frozen plan'):
        run.main(workflow.argv+['--from-plan','--execute','--cpus','4'],benchmark=workflow.benchmark)


def test_changed_cached_inputs_reject_before_credentials(workflow,monkeypatch):
    import sqlite3
    cache=workflow.output.parent/'asset-digests.sqlite'
    argv=workflow.argv+['--asset-cache',str(cache)]
    assert run.main(argv+['--preflight'],benchmark=workflow.benchmark)==0
    data=Path(argv[argv.index('--data')+1])
    if workflow.benchmark=='dataclawbench':(data/'x.csv').write_text('x\n2\n')
    elif workflow.benchmark == 'fdabench':
        with sqlite3.connect(data/'bird/retail/retail.sqlite') as db:db.execute('CREATE TABLE changed (n INTEGER)')
    else:
        with sqlite3.connect(data/'retail/retail_template.sqlite') as db:db.execute('CREATE TABLE changed (n INTEGER)')
    monkeypatch.setattr(run.runtime,'credential',lambda *a:pytest.fail('Changed input read credentials'))
    with pytest.raises(ValueError,match='Frozen plan'):
        run.main(argv+['--from-plan','--execute'],benchmark=workflow.benchmark)


def test_saved_attempt_cannot_be_dispatched_twice(workflow,monkeypatch):
    assert run.main(workflow.argv+['--preflight'],benchmark=workflow.benchmark)==0
    assert run.main(workflow.argv+['--from-plan','--execute'],benchmark=workflow.benchmark)==0
    monkeypatch.setattr(run.runtime,'credential',lambda *a:pytest.fail('Repeated attempt read credentials'))
    with pytest.raises(ValueError,match='already started'):
        run.main(workflow.argv+['--from-plan','--execute'],benchmark=workflow.benchmark)


@pytest.mark.parametrize('mode',('observations','full','full-prompt-only'))
def test_retired_modes_reject_before_credentials(workflow,monkeypatch,mode):
    monkeypatch.setattr(run.runtime,'credential',lambda *a:pytest.fail('Retired mode read credentials'))
    with pytest.raises(SystemExit):
        run.main(workflow.argv+['--evidence-mode',mode,'--execute'],benchmark=workflow.benchmark)
    assert not workflow.calls


def test_plan_execute_and_export_keeps_gold_out_of_solver(workflow, tmp_path):
    assert run.main(workflow.argv, benchmark=workflow.benchmark) == 0
    assert not workflow.output.exists() and not workflow.calls
    assert run.main(workflow.argv + ["--execute"], benchmark=workflow.benchmark) == 0
    assert len(workflow.calls) == 2
    rows = jsonl(workflow.output / "predictions.jsonl")
    assert len(rows) == 2 and all(row["status"] == "cli_exited" for row in rows)
    for row in rows:
        folder = workflow.output / row["instance_id"] / "claude-code-subagents"
        assert digest(folder / "submission.json") == row["submission_sha256"]
        assert "PRIVATE_GOLD" not in (folder / "report.json").read_text()
    evaluation = tmp_path / "evaluation"
    assert score.main(["--run", str(workflow.output), "--upstream", str(workflow.upstream),
                       "--tasks", str(workflow.task_file), "--output", str(evaluation)], benchmark=workflow.benchmark) == 0
    inputs = list(evaluation.glob("*-inputs.jsonl"))
    assert sum(len(jsonl(path)) for path in inputs) == 2
    if workflow.benchmark == "hybriddeepresearch":
        assert len(jsonl(evaluation / "s2sql-inputs.jsonl")) == 1
        assert len(jsonl(evaluation / "text-inputs.jsonl")) == 1
    assert json.loads((evaluation / "receipt.json").read_text())["judge_calls"] == 0


def test_cleanup_failure_retained_and_stops_later_tasks(workflow, monkeypatch):
    removed=[]
    original=run.subprocess.run
    def commands(command, **kwargs):
        if command[:2]==['docker','rm']:
            removed.append(command)
            assert command==['docker','rm','-f','fake-container']
            assert kwargs['timeout']==15
        return original(command, **kwargs)
    monkeypatch.setattr(run.subprocess, 'run', commands)
    def fail(identity):
        raise RuntimeError("fake stop failure")
    monkeypatch.setattr(run.runtime, "stop_container", fail)
    assert run.main(workflow.argv + ["--execute"], benchmark=workflow.benchmark) == 1
    rows = jsonl(workflow.output / "predictions.jsonl")
    assert [row["status"] for row in rows] == ["cleanup_failed", "not_started"]
    assert all(row["final_answer"] == "" for row in rows) and len(workflow.calls) == 1
    assert len(removed)==1


def test_gateway_cleanup_failure_preserves_terminal_report(workflow, monkeypatch):
    def fail(*args):raise RuntimeError('untrusted gateway shutdown details')
    monkeypatch.setattr(run.CredentialGateway, '__exit__', fail)
    assert run.main(workflow.argv + ['--execute'], benchmark=workflow.benchmark)==1
    rows=jsonl(workflow.output/'predictions.jsonl')
    assert [row['status'] for row in rows]==['cleanup_failed','not_started']
    report=workflow.output/rows[0]['instance_id']/'claude-code-subagents/report.json'
    value=json.loads(report.read_text())
    assert value['gateway_cleanup_error']=='RuntimeError'
    assert 'finished_at' in value and value['cleanup']['stopped']
    assert 'untrusted gateway shutdown details' not in report.read_text()


def test_web_loss_between_standalone_tasks_blocks_next_dispatch(workflow, monkeypatch):
    if workflow.benchmark!='hybriddeepresearch':return
    def ready(*args, **kwargs):
        if workflow.calls:raise TimeoutError('untrusted network details')
        return dict(tls_verified=True,model_calls=0)
    monkeypatch.setattr('harness.runtime_support.web_fetch.check_ready', ready)
    assert run.main(workflow.argv+['--execute'], benchmark=workflow.benchmark)==1
    assert len(workflow.calls)==1
    rows=jsonl(workflow.output/'predictions.jsonl')
    assert [r['status'] for r in rows]==['cli_exited','not_started']
    assert rows[1]['dispatch_blocked']=='web_readiness_failed'
    assert 'untrusted network details' not in json.dumps(rows)


def test_empty_text_answers_get_zero_without_loading_judge_key(workflow,tmp_path,monkeypatch):
    original=run.BACKENDS['claude-code-subagents'].run
    def empty(self,*a,**kw):
        result=original(self,*a,**kw)
        (kw['workspace']/'submission.json').write_text('{"final_answer":""}')
        return result
    monkeypatch.setattr(run.BACKENDS['claude-code-subagents'],'run',empty)
    assert run.main(workflow.argv+['--execute'],benchmark=workflow.benchmark)==1
    assert jsonl(workflow.output/'predictions.jsonl')[0]['status']=='incomplete'
    monkeypatch.setattr(run.runtime,'credential',lambda *a:pytest.fail('Empty answer loaded judge key'))
    output=tmp_path/'empty-score'
    assert score.main(['--run',str(workflow.output),'--upstream',str(workflow.upstream),
        '--tasks',str(workflow.task_file),'--output',str(output)],benchmark=workflow.benchmark)==0
    judged=jsonl(output/'judge-results.jsonl')
    assert judged and all(r['score']==0 and r['attempted_calls']==0 and r['status']=='empty_prediction' for r in judged)
    assert json.loads((output/'receipt.json').read_text())['judge_calls']==0


def test_unverified_organization_keeps_hash_bound_answer_separate(workflow, tmp_path, monkeypatch):
    original = run.BACKENDS['claude-code-subagents'].run
    def completed(self, *args, **kwargs):
        return dict(original(self, *args, **kwargs), returncode=0)
    monkeypatch.setattr(run.BACKENDS['claude-code-subagents'], 'run', completed)
    monkeypatch.setattr(run, 'native_subagents', lambda *a: dict(passed=False))
    assert run.main(workflow.argv + ['--execute'], benchmark=workflow.benchmark) == 1
    rows = jsonl(workflow.output / 'predictions.jsonl')
    assert rows[0]['status'] == 'native_condition_unverified' and rows[0]['final_answer'] == '1'
    assert rows[1]['status'] == 'not_started' and rows[1]['final_answer'] == ''
    args = ['--run', str(workflow.output), '--upstream', str(workflow.upstream),
            '--tasks', str(workflow.task_file), '--output', str(tmp_path/'evaluation')]
    assert score.main(args, benchmark=workflow.benchmark) == 0
    rows[0]['final_answer'] = 'tampered'
    (workflow.output/'predictions.jsonl').write_text('\n'.join(map(json.dumps, rows)))
    with pytest.raises(ValueError, match='differs'):
        score.main(args, benchmark=workflow.benchmark)


@pytest.mark.parametrize('status', ['timed_out', 'cleanup_failed', 'single_agent_condition_violated'])
def test_failed_attempt_is_not_outcome_eligible(status):
    assert not run.evaluable_prediction(dict(status=status, cli=dict(status='cli_exited', returncode=0)))


def test_success_cannot_bypass_submission_hash(workflow, tmp_path):
    run.main(workflow.argv + ["--execute"], benchmark=workflow.benchmark)
    path = workflow.output / "predictions.jsonl"
    rows = jsonl(path)
    del rows[0]["submission_sha256"]
    path.write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError, match="hash"):
        score.main(["--run", str(workflow.output), "--upstream", str(workflow.upstream),
                    "--tasks", str(workflow.task_file), "--output", str(tmp_path / "evaluation")], benchmark=workflow.benchmark)


def test_proof_requires_backend_observations():
    with pytest.raises(ValueError, match="observations"):
        validate(dict(passed=True, network="none", paid_calls=0), "claude-code-subagents")


def test_checkout_content_is_verified_not_only_revision(tmp_path):
    import subprocess
    from benchmarks._external import verify_sources
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    evaluator = tmp_path / "evaluation"
    evaluator.mkdir()
    source = evaluator / "s2sql_eval.py"
    source.write_text("# pinned fixture")
    subprocess.run(["git", "-C", str(tmp_path), "add", "evaluation"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Offline", "-c", "user.email=offline@example.invalid",
                    "commit", "-qm", "fixture"], check=True)
    verify_sources(tmp_path, "hybriddeepresearch")
    source.write_text("# modified evaluator")
    with pytest.raises(ValueError, match="differs"):
        verify_sources(tmp_path, "hybriddeepresearch")
