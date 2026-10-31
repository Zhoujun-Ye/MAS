from dataclasses import replace
import json
import re
import subprocess

import pytest

from fakes import ScriptedClient
from harness.agent import Agent
from harness.execution import ContainerWorkspace
from harness.llm import ProviderError
from harness.trace import Trace, read_trace
from benchmarks.cooperbench.adapter import EVALUATION_CONTRACT, Pair
from benchmarks.cooperbench.selection import choose, load_selection


def test_token_capacity_uses_receipts_and_keeps_full_history(tmp_path):
    client = ScriptedClient(lambda *a: dict(content='answer', reasoning='kept'))
    client.cfg = replace(client.cfg, context_window=1_000_000, max_tokens=65536)
    with Trace(tmp_path / 'trace.jsonl', 'capacity') as trace:
        agent = Agent('worker', client, trace, 'system')
        agent.append(dict(role='user', content='a' * 850000))
        agent.call()  # Old 800k character guard would stop this admissible input.
        assert agent.last_input_length == 2
        anchor = agent.last_prompt_tokens
        agent.append(dict(role='user', content='more'))
        estimate = agent.input_capacity()['estimated_input_tokens']
        assert anchor < estimate < anchor + 2000
        assert agent.messages[1]['content'] == 'a' * 850000
        assert agent.messages[2]['reasoning_content'] == 'kept'
        before = len(client.requests)
        agent.append(dict(role='user', content='b' * 950000))
        with pytest.raises(ProviderError, match='context_length'):
            agent.call()
        assert len(client.requests) == before
    assert len([e for e in read_trace(trace.path) if e['type'] == 'input_capacity']) == 2


def test_full_tool_output_recoverable_and_private(tmp_path, monkeypatch):
    payload = ('abc' + '\u4f60\u597d' + '\n') * 10000
    def run(argv, **kwargs):
        marker = re.search(r'__command_exit_[0-9a-f]+:', argv[-3]).group()
        kwargs['stdout'].write(payload.encode() + b'\n' + marker.encode() + b'1\n')
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, 'run', run)
    w = ContainerWorkspace('fixture', output_limit=10001, archive_dir=tmp_path / 'a')
    tools = {t.name: t for t in w.tools()}
    obs = tools['terminal'].run(dict(command='test', timeout_seconds=500), None)
    assert not obs.meta['error'] and obs.meta['exit_code'] == 1
    assert obs.meta['output_preserved'] and obs.meta['paginated'] and not obs.meta['truncated']
    key, offset = obs.meta['output_id'], obs.meta['next_offset']
    text = obs.text.split('\n', 1)[1]
    while offset < obs.meta['output_bytes']:
        page = tools['read_output'].run(dict(id=key, offset=offset), None)
        text += page.text.split('\n', 1)[1]
        assert page.meta['next_offset'] > offset
        offset = page.meta['next_offset']
    assert text == payload
    assert w.outputs[key].read_bytes() == payload.encode()
    other = {t.name: t for t in ContainerWorkspace('other', archive_dir=tmp_path / 'b').tools()}
    with pytest.raises(ValueError, match='private'):
        other['read_output'].run(dict(id=key), None)
    assert tools['read_output'].read_only


def test_joint_contract_is_initial_input_for_every_assignment():
    text = Pair('pallets_jinja_task', 1465, (1, 7)).request
    assert EVALUATION_CONTRACT in text
    for required in ('SAME merged codebase', 'zero conflicts', 'no shared Git remote',
                     'Identical patches', 'NOT scored only', 'no\nhuman or LLM'):
        assert required in text


def test_selection_is_unique_and_stratified_before_outcomes(tmp_path):
    subset = tmp_path / 'subsets'
    subset.mkdir()
    (subset / 'lite.json').write_text(json.dumps(dict(tasks=[dict(repo=f'r{i}_task', task_id=1,
          pairs=[[1,2],[1,3],[2,3]]) for i in range(12)])))
    selection = choose(tmp_path)
    assert selection == choose(tmp_path)
    path = tmp_path / 'selection.json'
    path.write_text(json.dumps(selection))
    pairs = load_selection(path)
    assert len(pairs) == len({p.key for p in pairs}) == 20
    assert len({p.repo for p in pairs}) == 12
    assert max(sum(p.repo == repo for p in pairs) for repo in {p.repo for p in pairs}) == 2


def test_batch_refuses_incomplete_gates_before_inspecting_images(tmp_path, monkeypatch):
    from scripts.cooperbench.pilot import validate_gates
    from benchmarks.cooperbench.adapter import REVISION
    from benchmarks.cooperbench.native import BACKEND_VERSION
    from benchmarks.cooperbench.isolation import ISOLATION_VERSION
    (tmp_path / 'summary.json').write_text(json.dumps(dict(revision=REVISION, backend=BACKEND_VERSION,
                  worker_isolation=ISOLATION_VERSION, all_passed=False, results=[])))
    def forbidden(*a, **k):
        raise AssertionError('No Docker/model access for a failing gate')
    monkeypatch.setattr(subprocess, 'check_output', forbidden)
    with pytest.raises(ValueError, match='no paid calls'):
        validate_gates(tmp_path, [Pair('sample_task', 1, (1,2))])


@pytest.mark.parametrize('result,events', [
    ({'halted_members': {'worker_a': 'context_length'}}, []),
    ({'snapshot_errors': {'worker_b': 'ValueError'}}, []),
    ({'reason': 'time_limit'}, []),
    ({'termination': 'budget_finalization'}, []),
    ({}, [{'type': 'output_recovery'}]),
    ({}, [{'type': 'tool_call', 'budget_exhausted': True}]),
    ({}, [{'type': 'tool_call', 'truncated': True}]),
])
def test_batch_stops_after_capacity_failure(result, events):
    from scripts.cooperbench.pilot import capacity_failure
    assert capacity_failure(result, events)
    assert not capacity_failure({'status': 'incomplete', 'reason': 'team_waiting_without_messages'}, [])


def test_dependency_derivative_bound_to_official_image(tmp_path, monkeypatch):
    from benchmarks.cooperbench import environment as env
    source, derived = 'sha256:' + 'a' * 64, 'sha256:' + 'b' * 64
    monkeypatch.setattr(env, 'CACHE', tmp_path)
    def inspect(image):
        return dict(Id=source) if image == 'official' else dict(Id=derived, Config=dict(
            Labels={'mas-information.source-image': source}))
    monkeypatch.setattr(env, 'inspect', inspect)
    assert env.resolve('official')['image_id'] == source
    path = tmp_path / ('a' * 64 + '.json')
    path.write_text(json.dumps(dict(version=env.VERSION, source_image_id=source, image_id=derived)))
    assert env.resolve('official')['image_id'] == derived
    monkeypatch.setattr(env, 'inspect', lambda image: dict(Id=source) if image == 'official'
                        else dict(Id=derived, Config=dict(Labels={})))
    with pytest.raises(ValueError, match='official source'):
        env.resolve('official')


def test_container_creation_interruption_cleans_own_name(monkeypatch):
    from benchmarks.cooperbench import native
    monkeypatch.setattr(native, 'resolve', lambda _: dict(image_id='image', runtime_env={}))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[:2] == ['docker', 'run']:
            raise KeyboardInterrupt()
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(native.subprocess, 'run', run)
    with pytest.raises(KeyboardInterrupt):
        native.DockerBackend().create_sandbox('official')
    name = calls[0][calls[0].index('--name') + 1]
    assert name.startswith('mas-info-eval-')
    assert calls[-1] == ['docker', 'rm', '-f', name]


def test_evaluator_distinguishes_runner_exit_from_transport_timeout(monkeypatch):
    from benchmarks.cooperbench import native
    result = dict(exit_code=124, output='test exceeded its timeout', truncated=False,
                  execution_error=False, error_kind=None)
    monkeypatch.setattr(native.ContainerWorkspace, 'execute', lambda *a, **kw: result)
    sandbox = native.Sandbox('fixture', 30, '/workspace')
    assert sandbox.exec('bash', 'runner.sh').returncode == 124
    result.update(execution_error=True, error_kind='execution_timeout')
    with pytest.raises(TimeoutError, match='test exceeded its timeout'):
        sandbox.exec('bash', 'runner.sh')


def test_large_evaluator_script_uses_stdin_without_clipping(monkeypatch):
    from benchmarks.cooperbench import native
    script = "printf '%s' '" + 'x' * 200_000 + "'"
    def execute(workspace, command, **kwargs):
        assert len(command) < 1000
        assert kwargs['stdin'] == script
        return dict(exit_code=0, output='', truncated=False, execution_error=False)
    monkeypatch.setattr(native.ContainerWorkspace, 'execute', execute)
    assert native.Sandbox('fixture', 30, '/workspace').exec('bash', '-c', script).returncode == 0


def test_public_pdf_transport_preserves_bytes_and_other_requests(tmp_path, monkeypatch):
    import hashlib
    import requests
    import httpx
    from benchmarks.cooperbench.offline_assets import PDF_URL, install_pdf
    body = b'%PDF-fixture\x00\xff'
    path = tmp_path / 'dummy.pdf'
    path.write_bytes(body)
    def no_network(*a, **kw):
        raise RuntimeError('normal transport')
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', no_network)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', no_network)
    with pytest.raises(ValueError, match='digest'):
        install_pdf(path, 'incorrect')
    install_pdf(path, hashlib.sha256(body).hexdigest())
    assert requests.get(PDF_URL).content == body
    assert httpx.get(PDF_URL).content == body
    assert b''.join(requests.get(PDF_URL, stream=True).iter_content(3)) == body
    with pytest.raises(RuntimeError, match='normal transport'):
        requests.get(PDF_URL + '?different=1')
    with pytest.raises(RuntimeError, match='normal transport'):
        httpx.get('https://example.org/unrelated')


def test_gguf_offline_transport_uses_real_cache_and_constructor(monkeypatch):
    import sys
    import types
    from benchmarks.cooperbench.offline_assets import install_gguf
    class Llama:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        @classmethod
        def from_pretrained(cls, *a, **kw):
            return 'online-original'
    seen = []
    def download(**kw):
        seen.append(kw)
        return '/real/cached/model.gguf'
    monkeypatch.setitem(sys.modules, 'llama_cpp', types.SimpleNamespace(Llama=Llama))
    monkeypatch.setitem(sys.modules, 'huggingface_hub', types.SimpleNamespace(hf_hub_download=download))
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    install_gguf()
    model = Llama.from_pretrained('owner/repo', 'model.gguf', n_ctx=512)
    assert model.kwargs == dict(model_path='/real/cached/model.gguf', n_ctx=512)
    assert seen == [dict(repo_id='owner/repo', filename='model.gguf', cache_dir=None, local_files_only=True)]
    with pytest.raises(ValueError, match='exact'):
        Llama.from_pretrained('owner/repo', '*.gguf')
    monkeypatch.setenv('HF_HUB_OFFLINE', '0')
    assert Llama.from_pretrained('owner/repo', 'model.gguf') == 'online-original'


@pytest.mark.parametrize('elapsed,code,kind', [(1.01,143,'execution_timeout'),
    (1.01,137,'execution_timeout'), (0.01,137,'execution_transport')])
def test_busybox_timeout_is_not_a_docker_failure(monkeypatch, elapsed, code, kind):
    from harness import execution
    ticks = iter([10, 10 + elapsed])
    monkeypatch.setattr(execution.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(execution.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, code))
    result = ContainerWorkspace('fixture', timeout=1).execute('sleep 3')
    assert result['execution_error'] and result['error_kind'] == kind


def test_native_cache_requires_same_code_environment_and_real_passes():
    from scripts.cooperbench.native_check import reusable, cache_key
    pair = Pair('sample_task', 1, (1, 2))
    environment = dict(image_id='image-a', runtime_env={})
    row = dict(pair=pair.key, validation_fingerprint='code-a', gate_passed=True, **environment,
        features=[dict(feature=f, gate_passed=True, baseline=dict(tests_failed=1),
                       gold=dict(passed=True)) for f in pair.features], gold_joint=dict(both_passed=True))
    assert reusable(row, pair, environment, 'code-a')
    assert not reusable(row, pair, environment, 'code-b')
    assert not reusable(row, pair, dict(environment, image_id='image-b'), 'code-a')
    assert not reusable(dict(row, validation_fingerprint=None), pair, environment, 'code-a')
    assert cache_key(pair, environment, 'code-a') != cache_key(pair, environment, 'code-b')
    row['features'][0]['gold']['passed'] = False
    assert not reusable(row, pair, environment, 'code-a')


def test_bounded_batch_overlaps_jobs_and_stops_dispatch_without_abandoning():
    import threading
    from harness.runner import bounded_jobs
    barrier = threading.Barrier(4)
    failed = threading.Event()
    started, finished = [], []
    def worker(index):
        started.append(index)
        barrier.wait(timeout=5)
        if index == 0:
            failed.set()
        else:
            assert failed.wait(5)
        finished.append(index)
        return dict(index=index, stop=index == 0)
    results = list(bounded_jobs(range(20), worker, 4, lambda r: r['stop'], failed))
    assert sorted(started) == sorted(finished) == [0, 1, 2, 3]
    assert len(results) == 4


def test_bounded_batch_runs_every_job_once_without_retry():
    from harness.runner import bounded_jobs
    results = list(bounded_jobs(range(20), lambda x: x, 4, lambda r: False))
    assert sorted(results) == list(range(20))
