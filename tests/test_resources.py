import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pathlib import Path

from harness.runtime_support import runtime
from harness.runtime_support.resources import ContainerResources, cpu_sample, summarize
from scripts.studies import benchmark_matrix as matrix


def test_cgroup_cpu_units_and_quota_utilization(tmp_path):
    (tmp_path / 'cpu.stat').write_text('usage_usec 1000000\nuser_usec 800000\nsystem_usec 200000\n'
        'nr_periods 10\nnr_throttled 2\nthrottled_usec 100000\n')
    first = cpu_sample(tmp_path, 0)
    last = dict(first, elapsed_seconds=2, usage_usec=5_000_000, nr_periods=30,
                nr_throttled=6, throttled_usec=600_000)
    s = summarize([first, last], 8)
    assert s['cpu_seconds'] == 4
    assert s['average_cores'] == 2
    assert s['quota_utilization_percent'] == 25
    assert s['throttled_seconds'] == .5
    assert s['throttled_period_fraction'] == .2


def test_missing_metrics_are_unknown_not_zero():
    assert summarize([], 8)['available'] is False


@pytest.mark.parametrize('interval', [0, -1, float('inf'), float('nan'), True])
def test_sampling_interval_cannot_busy_loop(tmp_path, interval):
    with pytest.raises(ValueError, match='interval'):
        ContainerResources('fixture', tmp_path, 8, interval=interval)


def test_existing_capture_cannot_be_silently_mixed(tmp_path):
    (tmp_path/'cpu-samples.jsonl').write_text('old capture')
    with pytest.raises(FileExistsError, match='mix'):
        ContainerResources('fixture', tmp_path, 8).start()


def test_collector_close_preserves_final_sample_and_errors(tmp_path):
    cgroup = tmp_path / 'cgroup'
    cgroup.mkdir()
    (cgroup / 'cpu.stat').write_text('invalid')
    collector = ContainerResources('fixture', tmp_path, 8)
    collector.cgroup = cgroup
    collector.started = 0
    result = collector.close()
    assert result['available'] is False
    assert result['capture_complete'] is False
    assert result['sample_errors']
    assert json.loads((tmp_path / 'cpu-summary.json').read_text()) == result
    assert collector.close() is result


@pytest.mark.parametrize('cpus', [0, 129, True, 2.5])
def test_container_rejects_invalid_cpu_quota(tmp_path, cpus):
    with pytest.raises(ValueError, match='CPUs'):
        runtime.container(tmp_path, tmp_path, tmp_path, 'fixture', cpus=cpus)


def test_explicit_cpu_quota_reaches_docker(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(runtime.subprocess, 'check_output',
                        lambda command, **kwargs: commands.append(command) or 'fixture\n')
    runtime.container(tmp_path, tmp_path, tmp_path, 'fixture', cpus=8)
    assert commands[0][commands[0].index('--cpus') + 1] == '8'


def test_compute_threads_are_explicit_and_bounded(tmp_path, monkeypatch):
    assert runtime.native_env('claude-code-subagents')['OPENBLAS_NUM_THREADS'] == '1'
    assert runtime.native_env('claude-code-subagents',compute_threads=4)['OPENBLAS_NUM_THREADS'] == '4'
    with pytest.raises(ValueError,match='quota'):
        runtime.container(tmp_path,tmp_path,tmp_path,'fixture',cpus=2,compute_threads=4)
    commands=[]
    monkeypatch.setattr(runtime.subprocess,'check_output',lambda c,**kw:commands.append(c) or 'fixture\n')
    runtime.container(tmp_path,tmp_path,tmp_path,'fixture',cpus=8,compute_threads=4)
    assert 'OPENBLAS_NUM_THREADS=4' in commands[0]
    assert 'OMP_NUM_THREADS=4' in commands[0]


def test_module_requirements_are_generic_and_never_install():
    assert runtime.capability_modules(['numpy','numpy','scipy'])==['numpy','scipy']
    command=runtime.capability_command(['missing_synthetic_module'])
    assert command[:2]==['python3','-c']
    assert 'find_spec' in command[-1] and 'SystemExit' in command[-1]
    assert 'pip' not in command[-1] and 'pymsis' not in command[-1]


@pytest.mark.parametrize('modules',[['os.path'],['a;import os'],['../outside'],[1],'numpy'])
def test_module_requirements_reject_code_and_implicit_parent_imports(modules):
    with pytest.raises(ValueError):runtime.capability_modules(modules)


def test_mixed_cpu_study_keeps_exact_authorized_scope(tmp_path, monkeypatch, capsys):
    tasks = [('kramabench', SimpleNamespace(id=f'task-{i}')) for i in range(20)]
    monkeypatch.setattr(matrix, 'selections', lambda *a: tasks)
    monkeypatch.setattr(matrix.runtime, 'credential', lambda *a: pytest.fail('Planning must not load credentials'))
    assert matrix.main(['--root', str(tmp_path), '--output', str(tmp_path/'out'), '--image', 'fixture',
        '--proofs', str(tmp_path), '--benchmarks', 'kramabench', '--conditions', 'claude-code-subagents',
        'full', '--tasks-per-benchmark', '20', '--concurrency', '8', '--cpus', '8', '--record-resources',
        '--compute-threads', '4', '--require-module', 'numpy']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['attempts'] == plan['maximum_judge_calls'] == 40
    assert plan['protocol_settings']['cpu_per_attempt'] == 8
    assert plan['protocol_settings']['record_resources'] is True
    assert plan['protocol_settings']['compute_threads'] == 4
    assert plan['protocol_settings']['required_modules'] == ['numpy']
    assert plan['solver_concurrency'] == 8
    assert len({r['task_id'] for r in plan['selections']}) == 20
    assert {r['backend'] for r in plan['selections']} == {'full', 'claude-code-subagents'}


def test_solver_command_records_resource_options(tmp_path):
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path, image='fixture', credentials=tmp_path/'private',
                           cpus=8, record_resources=True, compute_threads=4, require_module=['numpy'])
    cmd = matrix.solver_command(args, 'kramabench', SimpleNamespace(id='fixture'), 'full', tmp_path/'out')
    assert cmd[cmd.index('--cpus') + 1] == '8'
    assert '--record-resources' in cmd
    assert cmd[cmd.index('--compute-threads') + 1] == '4'
    assert cmd[cmd.index('--require-module') + 1] == 'numpy'


def test_canonical_infra_profile_matches_live_protocol_without_task_ids():
    settings=matrix.protocol_settings(SimpleNamespace(effort='high',backends=['claude-code-subagents','full'],
        concurrency=8,judge_concurrency=2,cpus=8,compute_threads=4,record_resources=True))
    profile=Path(__file__).resolve().parents[1]/'docs/studies/cpu8-infra-protocol.json'
    assert json.loads(profile.read_text())==settings


def test_capability_checks_import_not_merely_presence(tmp_path):
    (tmp_path/'broken_fixture.py').write_text('raise RuntimeError("broken ABI")')
    command = runtime.capability_command(['broken_fixture'])
    result = subprocess.run([sys.executable, *command[1:]], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 2
    receipt = json.loads(result.stdout)
    assert receipt['required_modules']['broken_fixture'] is False
    assert receipt['import_errors']['broken_fixture'] == 'RuntimeError'
    assert 'broken ABI' not in result.stdout


def test_functional_probes_are_frozen_and_not_run_on_host(tmp_path):
    path = tmp_path/'capability.py'
    marker = tmp_path/'must-not-exist'
    path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    first = runtime.capability_probes([path])
    assert not marker.exists()
    path.write_text('raise RuntimeError("missing model data")\n')
    assert first[0]['sha256'] != runtime.capability_probes([path])[0]['sha256']
    assert not marker.exists()
    path.write_text('invalid python !')
    with pytest.raises(SyntaxError):
        runtime.capability_probes([path])


def test_matrix_forwards_and_freezes_functional_probe(tmp_path):
    probe = tmp_path/'functional.py'
    probe.write_text('assert 2 + 2 == 4\n')
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path, image='fixture',
        credentials=tmp_path/'private', cpus=8, record_resources=True, compute_threads=4,
        require_module=[], capability_probe=[str(probe)], effort='high',
        backends=['claude-code-subagents', 'full'], concurrency=8, judge_concurrency=2)
    command = matrix.solver_command(args, 'kramabench', SimpleNamespace(id='fixture'), 'full', tmp_path/'out')
    assert command[command.index('--capability-probe') + 1] == str(probe)
    assert matrix.protocol_settings(args)['capability_probes'] == runtime.capability_probes([probe])
