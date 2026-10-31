import copy
import json
import subprocess
from dataclasses import asdict

import pytest

from benchmarks.cooperbench.adapter import Pair, grade
from benchmarks.cooperbench.diagnostics import diagnose
from benchmarks.cooperbench.native import diagnostic_runner_args
from benchmarks.cooperbench.errata import clarify, input_receipt


@pytest.mark.parametrize('output,kind', [
    ('___ ERROR at setup of test_stream ___\nTimeoutError', 'fixture_error'),
    ('ERROR collecting tests/test_card.py\nTypeError', 'collection_error'),
    ('\x1b[31mFAILED tests/test_x.py::test_x\x1b[0m', 'test_failure'),
    ('--- FAIL: TestHeader (0.01s)', 'test_failure'),
    ('Running tests...\nCleaning up repository...', 'unresolved'),
])
@pytest.mark.parametrize('key', ['output', 'test_output'])
def test_diagnostics_preserve_raw_and_do_not_infer_cause(output, kind, key):
    raw = {'feature1': {key: output, 'passed': False}, 'feature2': {'passed': True}}
    before = copy.deepcopy(raw)
    result = diagnose(Pair('sample_task', 0, (1, 2)), raw)
    assert result['features'][0]['kind'] == kind
    assert result['features'][0]['cause'] == 'not_determined'
    assert result['features'][1]['kind'] == 'passed'
    assert raw == before


def test_known_issue_does_not_rescue_official_failure():
    pair = Pair('openai_tiktoken_task', 0, (2, 9))
    raw = dict(merge={'status': 'identical'}, both_passed=False)
    result = grade(pair, {'worker_a': '', 'worker_b': ''}, '.', lambda **kwargs: raw)
    assert result['correct'] is False
    assert result['diagnostics']['benchmark_issues'][0]['feature'] == 9
    assert diagnose(Pair('sample_task', 0, (2, 9)), raw)['benchmark_issues'] == []


def test_trace_only_known_runner_invocation():
    direct = ('bash', '/usr/local/bin/runner.sh', 'tests.patch', 'merged.patch')
    assert diagnostic_runner_args(direct) == ('bash', '-x', *direct[1:])
    script = 'git reset --hard BASE\nbash /usr/local/bin/runner.sh tests.patch merged.patch\n'
    transformed = diagnostic_runner_args(('bash', '-c', script))
    assert transformed[2] == script.replace('bash /', 'bash -x /')
    unrelated = ('bash', '-c', 'echo hello')
    assert diagnostic_runner_args(unrelated) == unrelated


def test_shell_trace_retains_failed_capture_without_changing_exit(tmp_path):
    script = tmp_path / 'runner.sh'
    script.write_text("set -e\nTEST_OUTPUT=$(printf '%s\\n' '--- FAIL: TestHeader'; exit 7)\necho unreachable\n")
    normal = subprocess.run(['bash', str(script)], capture_output=True, text=True)
    traced = subprocess.run(['bash', '-x', str(script)], capture_output=True, text=True)
    assert normal.returncode == traced.returncode == 7
    assert '--- FAIL: TestHeader' not in normal.stdout + normal.stderr
    assert '--- FAIL: TestHeader' in traced.stderr


@pytest.mark.parametrize('repo,task,feature,expected', [
    ('openai_tiktoken_task', 0, 9, 'compression=True/False'),
    ('dspy_task', 8394, 5, 'original Python object'),
])
def test_clarifications_are_explicit_and_inputs_are_pinned(tmp_path, repo, task, feature, expected):
    pair = Pair(repo, task, (1, feature))
    for f in pair.features:
        directory = tmp_path / repo / f'task{task}' / f'feature{f}'
        directory.mkdir(parents=True)
        (directory / 'feature.md').write_text('Original specification')
    official = pair.private_inputs(tmp_path)
    clarified = pair.private_inputs(tmp_path, 'clarified-v1')
    assert official['worker_b'] == 'Original specification'
    assert clarified['worker_a'] == official['worker_a']
    assert expected in clarified['worker_b']
    assert pair.private_inputs(tmp_path) == official
    receipt = input_receipt(clarified, 'clarified-v1')
    assert receipt['official_assignments'] is False
    assert receipt['input_sha256'] != input_receipt(official, 'official')['input_sha256']
    with pytest.raises(ValueError):
        clarify('text', repo, task, feature, 'unknown')


def test_repair_sources_are_failed_same_pairs_with_registered_errata(tmp_path, monkeypatch):
    from scripts.cooperbench import pilot
    pair = Pair('openai_tiktoken_task', 0, (2, 9))
    for name, value in [('manifest.json', {'pair': asdict(pair)}), ('result.json', {}),
                        ('grade.json', {'correct': False})]:
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / 'trace.jsonl').write_text('')
    calls = []
    monkeypatch.setattr(pilot, 'load_submitted_patches', lambda *args: calls.append(args))
    receipt = pilot.repair_sources([tmp_path], [pair])
    assert receipt[pair.key]['issues'] and len(calls) == 1
    assert 'grade.json' in receipt[pair.key]['evidence_sha256']
    with pytest.raises(ValueError):
        pilot.repair_sources([], [pair])
    (tmp_path / 'grade.json').write_text(json.dumps({'correct': True}))
    with pytest.raises(ValueError):
        pilot.repair_sources([tmp_path], [pair])
