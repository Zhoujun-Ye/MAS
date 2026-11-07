import json

import pytest

from harness.evidence_mas.hook import response
from harness.evidence_mas.store import Store, StoreError
from harness.evidence_mas import integration


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'store', 'test')


def capture(store, **kwargs):
    return store.call('obs.capture', dict(tool_name='Bash',
        tool_input={'command': 'unique-sql-input'}, tool_output='answer',
        status='success', completeness='complete', **kwargs), role='collector')


def test_input_discovery_and_clamped_reads(store):
    obs = capture(store)
    rows = store.call('obs.search', {'query': 'unique-sql-input'})['items']
    assert rows[0]['id'] == obs['id']
    assert 'unique-sql-input' in rows[0]['input_summary']
    assert rows[0]['preview'] == 'answer'
    assert 'input_ref' not in rows[0]
    assert 'unique-sql-input' in store.call('obs.read', dict(obs_id=obs['id'], field='input'))['text']
    assert store.call('obs.read', dict(obs_id=obs['id'], end=90000))['text'] == 'answer'
    empty = store.call('obs.read', dict(obs_id=obs['id'], start=90000))
    assert empty['text'] == '' and empty['start'] == empty['end'] == 6
    for args in ({'start': -1}, {'start': True}, {'start': 3, 'end': 1}, {'field': 'bad'}):
        with pytest.raises(StoreError):
            store.call('obs.read', dict(obs_id=obs['id'], **args))


def test_capture_does_not_scan_objects_or_check_decision_cycles(store, monkeypatch):
    def forbidden(*args):
        raise AssertionError('Unnecessary graph scan')
    monkeypatch.setattr(store, 'latest', forbidden)
    obs = capture(store, session_id='s', agent_id='a', tool_call_id='t')
    assert capture(store, session_id='s', agent_id='a', tool_call_id='t')['id'] == obs['id']
    assert store.call('obs.read', {'obs_id': obs['id']})['text'] == 'answer'


def test_read_does_not_reserve_writer_lock(store, monkeypatch):
    obs = capture(store)
    original = store.output_text
    def read(value):
        with store.connect() as other:
            other.execute('PRAGMA busy_timeout=0')
            other.execute('BEGIN IMMEDIATE')
            other.rollback()
        return original(value)
    monkeypatch.setattr(store, 'output_text', read)
    assert store.call('obs.read', {'obs_id': obs['id']})['text'] == 'answer'


def test_audit_requires_no_ceremonial_reads(tmp_path):
    Store(tmp_path / 'native-profile/evidence', 'benchmark-evidence')
    audit = integration.audit(tmp_path, 'full')
    assert audit['complete'] and audit['missing'] == []
    assert audit['delegation']['lead_reads_worker'] is False
    assert audit['audit_policy'] == 'descriptive_only'
    context = response({'hook_event_name': 'PostToolUse'}, {'id': 'obs'})
    assert context == {}


@pytest.mark.parametrize('mode', ['observations', 'full', 'full-prompt-only'])
def test_benchmark_launch_uses_protocol_without_structured_prompt(tmp_path, monkeypatch, mode):
    from harness.evidence_mas import cli
    from scripts.common import evidence
    monkeypatch.setattr(cli, 'run_cli', lambda **kwargs: kwargs)
    result = evidence.launch(mode, 'claude', 'synthetic task', 'shared limits', tmp_path,
        tmp_path, 'fixture-container', model='fixture', allowed_tools=(), disallowed_tools=(), timeout=60)
    from scripts.common.prompts.structured_subagents import PROMPT
    assert result['prompt'] == 'synthetic task\n\nshared limits' + evidence.PROMPT + '\n\n' + cli.workspace_guidance(mode)
    assert PROMPT not in result['prompt']
    argv = result['argv']
    worker = json.loads(argv[argv.index('--agents') + 1])['evidence-worker']
    assert PROMPT not in worker['prompt']
    assert worker['prompt'] == cli.worker_prompt(mode) + '\nShared task rules:\nshared limits'
