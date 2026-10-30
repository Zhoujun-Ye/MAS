import json
import subprocess
import re

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


def test_normal_nonzero_command_is_observation_not_execution_error(monkeypatch):
    def run(argv, **kw):
        marker = re.search(r'__command_exit_[0-9a-f]+:', argv[-3]).group()
        kw['stdout'].write(b'1 failed\n\n' + marker.encode() + b'1\n')
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, 'run', run)
    obs = ContainerWorkspace('fixture').tools()[0].run(dict(command='pytest'), None)
    assert obs.meta['exit_code'] == 1 and obs.meta['error'] is False
    assert obs.text.endswith('1 failed\n')
