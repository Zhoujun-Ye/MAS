import json
from pathlib import Path

import pytest

from benchmarks.cooperbench.adapter import Pair, discover, make_team, grade, load_submitted_patches
from harness.config import digest
from fakes import ScriptedClient
from harness.agent import Tool, Observation
from harness.trace import Trace, read_trace, validate


@pytest.mark.parametrize('mutation', ['none', 'patch', 'snapshot', 'version', 'incomplete', 'report_only', 'missing'])
def test_grade_is_bound_to_current_frozen_patches(tmp_path, mutation):
    manifest = dict(bases={'worker_a': 'base', 'worker_b': 'base'}, submission_contract='immutable-snapshot-v1')
    result = dict(status='completed', submission_status='submitted', unfinished_roles=[], evaluation_snapshots={})
    for role in ('worker_a', 'worker_b'):
        artifact = dict(patch='patch-' + role, base='base')
        record = dict(submission_id=role + ':v2', revision=2, kind="explicit", artifact=artifact, digest=digest(artifact))
        (tmp_path / (role + '.submission.json')).write_text(json.dumps(record))
        (tmp_path / (role + '.patch')).write_text(artifact['patch'])
        result['evaluation_snapshots'][role] = dict(submission_id=record['submission_id'], digest=record['digest'], kind='explicit')
    if mutation == 'patch':
        (tmp_path / 'worker_a.patch').write_text('unsubmitted later edit')
    elif mutation == 'snapshot':
        path = tmp_path / 'worker_a.submission.json'
        record = json.loads(path.read_text())
        record['artifact']['patch'] = 'tampered'
        path.write_text(json.dumps(record))
    elif mutation == 'version':
        result['evaluation_snapshots']['worker_a']['submission_id'] = 'worker_a:v1'
    elif mutation == 'incomplete':
        result['submission_status'] = 'incomplete'
    elif mutation == 'report_only':
        manifest['submission_contract'] = 'report-only-v1'
    elif mutation == 'missing':
        del result['evaluation_snapshots']['worker_a']
    if mutation in ('none', 'incomplete'):
        assert load_submitted_patches(tmp_path, manifest, result) == {'worker_a': 'patch-worker_a', 'worker_b': 'patch-worker_b'}
    else:
        with pytest.raises(ValueError):
            load_submitted_patches(tmp_path, manifest, result)


def fixture_dataset(tmp_path):
    task = tmp_path / 'sample_task/task0'
    for feature, text in ((1, 'PRIVATE_FEATURE_A'), (2, 'PRIVATE_FEATURE_B')):
        folder = task / f'feature{feature}'
        folder.mkdir(parents=True)
        (folder / 'feature.md').write_text(text)
        (folder / 'tests.patch').write_text('HIDDEN_TESTS')
        (folder / 'feature.patch').write_text('GOLD_SOLUTION')
    return tmp_path


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_private_features_and_workspace_routing(tmp_path, scheduler):
    data = fixture_dataset(tmp_path / 'data')
    pair, = discover(data)
    assert pair.task_id == 0 and pair.features == (1, 2)
    called = []
    class Workspace:
        def __init__(self, role):
            self.role = role
        def tools(self):
            def run(args, agent):
                called.append((agent.name, self.role))
                return Observation('local file')
            return [Tool('read_file', 'Read', dict(type='object', properties={}), run)]
    def policy(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        serialized = json.dumps(messages)
        assert 'HIDDEN_TESTS' not in serialized and 'GOLD_SOLUTION' not in serialized
        if role == 'leader':
            assert 'PRIVATE_FEATURE_' not in serialized
            return dict(content='Submitted')
        own, other = ('A', 'B') if role == 'worker_a' else ('B', 'A')
        assert 'PRIVATE_FEATURE_' + own in serialized
        assert 'PRIVATE_FEATURE_' + other not in serialized
        if not any(m['role'] == 'assistant' for m in messages):
            return dict(calls=[('read_file', {})])
        return dict(calls=[('submit_assignment', dict(report='Work ready'))])
    with Trace(tmp_path / 'trace.jsonl', 'fixture') as trace:
        trace.emit('run_start')
        team = make_team(pair, data, {r: Workspace(r) for r in ('worker_a', 'worker_b')},
                         ScriptedClient(policy), trace, scheduler=scheduler)
        result = team.run_task(pair.request)
        trace.emit('run_end', status=result['status'])
    assert result['status'] == 'completed'
    assert result['submission_status'] == 'submitted'
    assert team.templates == {'worker_a': 'coder', 'worker_b': 'coder', 'leader': 'leader'}
    assert team.permissions['worker_a'] == team.permissions['worker_b'] == ('import_files', 'read_file', 'share_files')
    assert team.member_limits['worker_a'] == team.member_limits['worker_b']
    assert sorted(called) == [('worker_a', 'worker_a'), ('worker_b', 'worker_b')]
    assert validate(read_trace(trace.path)) == []


@pytest.mark.parametrize('merge, passed, error, correct', [
    ('clean', True, None, True), ('identical', True, None, True),
    ('conflicts', True, None, False), ('clean', False, None, False),
    ('error', False, 'environment failed', None)])
def test_official_evaluation_boundary(merge, passed, error, correct):
    def evaluator(**kwargs):
        assert kwargs['backend'] == 'docker'
        assert kwargs['patch1'] == 'A' and kwargs['patch2'] == 'B'
        assert kwargs['task_id'] == 0
        return dict(merge=dict(status=merge), both_passed=passed, error=error)
    result = grade(Pair('sample_task', 0, (1, 2)), dict(worker_a='A', worker_b='B'), Path('/data'), evaluator)
    assert result['correct'] is correct
    assert (result['status'] == 'error') == bool(error)


@pytest.mark.parametrize('repo, task, features', [('../bad', 1, (1, 2)), ('sample_task', -1, (1, 2)),
    ('sample_task', 1, (2, 1)), ('sample_task', 1, (1, 1))])
def test_invalid_task_identity(repo, task, features):
    with pytest.raises(ValueError):
        Pair(repo, task, features)


def test_terminal_patches_can_be_evaluated_without_rescuing_primary_failure(tmp_path):
    from benchmarks.cooperbench.adapter import REVISION, WORKERS
    from scripts.cooperbench.grade import evaluate_output
    manifest = dict(upstream_revision=REVISION, pair=dict(repo='sample_task', task_id=0, features=[1, 2]),
                    image_id='image', environment=dict(image_id='image', source_image_id='official', runtime_env={}),
                    submission_contract='immutable-snapshot-v1', bases=dict.fromkeys(WORKERS, 'base'))
    result = dict(status='incomplete', failure_class='agent_failure', evaluation_snapshots={})
    for role in WORKERS:
        artifact = dict(patch='partial', base='base')
        record = dict(submission_id=role + ':v1:terminal', revision=1, kind='terminal', artifact=artifact, digest=digest(artifact))
        result['evaluation_snapshots'][role] = {k: record[k] for k in ('submission_id', 'digest', 'kind')}
        (tmp_path / (role + '.submission.json')).write_text(json.dumps(record))
        (tmp_path / (role + '.patch')).write_text('partial')
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'result.json').write_text(json.dumps(result))
    evaluator = lambda **kwargs: dict(merge=dict(status='clean'), both_passed=True)
    graded = evaluate_output(tmp_path, tmp_path, lambda _: manifest['environment'], evaluator)
    assert graded['correct'] is False and graded['code_correct'] is True
    assert graded['verification'] == 'passed'
    corrupted = evaluate_output(tmp_path, tmp_path, lambda _: dict(manifest['environment'], image_id='different-image'), evaluator)
    assert corrupted['status'] == 'error' and corrupted['correct'] is False
    changed_profile = evaluate_output(tmp_path, tmp_path,
        lambda _: dict(manifest['environment'], runtime_env={'changed': 'yes'}), evaluator)
    assert changed_profile['status'] == 'error'
