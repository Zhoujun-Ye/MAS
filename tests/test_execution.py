import subprocess
import re
import hashlib

import pytest

from harness.execution import ContainerWorkspace


def test_commands_only_execute_inside_explicit_container(monkeypatch):
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        marker = re.search(r'__command_exit_[0-9a-f]+:', argv[-3]).group()
        kwargs['stdout'].write(b'actual output\n' + marker.encode() + b'0\n')
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, 'run', run)
    workspace = ContainerWorkspace('disposable-fixture', output_limit=6)
    tools = {tool.name: tool for tool in workspace.tools()}
    result = tools['terminal'].run(dict(command='python -m pytest'), None)
    assert result.text == 'Exit code: 0; truncated: true\nactual'
    tools['write_file'].run(dict(path='a b.py', content='x=7'), None)
    tools['read_file'].run(dict(path='a b.py'), None)
    assert all(argv[:6] == ['docker', 'exec', '-i', '-w', '/workspace', 'disposable-fixture'] for argv, _ in calls)
    assert calls[1][1]['input'] == 'x=7'
    assert calls[1][0][-1] == "mkdir -p -- . && cat > 'a b.py'"
    assert workspace.execute('python -m pytest')['exit_code'] == 0


def test_nonzero_test_exit_is_not_success(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 1))
    result = ContainerWorkspace('fixture').execute('tests')
    assert result['exit_code'] == 1 and result['execution_error']


@pytest.mark.parametrize('code', [1, 137])
def test_normal_nonzero_command_is_observation_not_execution_error(monkeypatch, code):
    def run(argv, **kw):
        marker = re.search(r'__command_exit_[0-9a-f]+:', argv[-3]).group()
        kw['stdout'].write(b'1 failed\n\n' + marker.encode() + str(code).encode() + b'\n')
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, 'run', run)
    obs = ContainerWorkspace('fixture').tools()[0].run(dict(command='pytest'), None)
    assert obs.meta['exit_code'] == code and obs.meta['error'] is False
    assert obs.meta['execution_confirmed'] and obs.meta['executor_exit_code'] == 0
    assert obs.text.endswith('1 failed\n')


@pytest.mark.parametrize('prefix', [b'', b'x' * (1024 * 1024 - 20)])
def test_exit_record_preserves_late_stderr_and_retained_pages(monkeypatch, tmp_path, prefix):
    late = b'sh: Syntax error: "(" unexpected\n' + b'e' * (1024 * 1024 + 20)
    expected = prefix + late

    def run(argv, **kw):
        marker = re.search(r'__command_exit_[0-9a-f]+:', argv[-3]).group().encode()
        kw['stdout'].write(prefix + b'\n' + marker + b'2\n' + late)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, 'run', run)
    workspace = ContainerWorkspace('fixture', output_limit=40, archive_dir=tmp_path)
    result = workspace.execute('diff <(echo a) <(echo b)', retain=True)
    assert result['exit_code'] == 2 and not result['execution_error']
    assert result['output'] == expected[:40].decode()
    assert result['output_bytes'] == len(expected)
    assert result['output_sha256'] == hashlib.sha256(expected).hexdigest()
    assert workspace.outputs[result['output_id']].read_bytes() == expected
    assert workspace.execute('same', capture_all=True)['output'].encode() == expected


@pytest.mark.parametrize('code,elapsed,kind', [
    (137, 1, 'execution_interrupted'), (-9, 1, 'execution_interrupted'),
    (143, 61, 'execution_timeout'), (124, 1, 'execution_timeout'),
    (125, 1, 'execution_transport'), (1, 1, 'execution_transport'),
    (0, 1, 'execution_transport'), (255, 1, 'execution_transport'),
])
def test_missing_record_does_not_claim_success_or_infer_transport_from_signal(monkeypatch, code, elapsed, kind):
    times = iter([0, elapsed])
    monkeypatch.setattr('harness.execution.time.monotonic', lambda: next(times))
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, code))
    obs = ContainerWorkspace('fixture').tools()[0].run({'command': 'work'}, None)
    assert obs.meta['error'] and obs.meta['exit_code'] == code
    assert obs.meta['error_kind'] == kind
    assert not obs.meta['execution_confirmed'] and obs.meta['executor_exit_code'] == code
    assert 'not a confirmed command result' in obs.text


def test_record_does_not_hide_nonzero_executor_exit(monkeypatch):
    def run(argv, **kw):
        marker = re.search(r'__command_exit_[0-9a-f]+:', argv[-3]).group().encode()
        kw['stdout'].write(b'\n' + marker + b'0\n')
        return subprocess.CompletedProcess(argv, 137)

    monkeypatch.setattr(subprocess, 'run', run)
    result = ContainerWorkspace('fixture').execute('work')
    assert result['execution_error'] and result['exit_code'] == 137
    assert result['error_kind'] == 'execution_interrupted'
