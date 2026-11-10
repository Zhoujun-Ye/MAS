import json
import signal
import subprocess
from types import SimpleNamespace

import pytest

from scripts.common import run
from harness.runtime_support import runtime
from harness.runtime_support.credential_gateway import CredentialGateway


def test_creation_interrupt_uses_registered_name(tmp_path, monkeypatch):
    calls = []
    expected = "mas-cli6-0123456789ab"
    monkeypatch.setattr(runtime.uuid, "uuid4", lambda: SimpleNamespace(hex="0123456789abcdef"))

    def create(command, **kwargs):
        registered = json.loads((tmp_path / "container-ownership.json").read_text())
        assert registered == dict(container_name=expected, status="creating")
        assert command[command.index("--name") + 1] == expected
        assert kwargs["timeout"] == 60
        raise KeyboardInterrupt

    def cleanup(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 15
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime.subprocess, "check_output", create)
    monkeypatch.setattr(runtime.subprocess, "run", cleanup)
    with pytest.raises(KeyboardInterrupt) as caught:
        runtime.container(tmp_path, tmp_path, tmp_path, "fixture-image")
    assert caught.value.container_id == expected
    assert caught.value.cleanup_details["removed"] is True
    assert calls == [["docker", "stop", "--time", "2", expected], ["docker", "rm", "-f", expected]]
    ownership = json.loads((tmp_path / "container-ownership.json").read_text())
    assert ownership["status"] == "startup_failed"
    assert ownership["cleanup"]["removed"] is True


def test_bridge_failure_removes_even_when_stop_fails(tmp_path, monkeypatch):
    calls = []
    gateway = object.__new__(CredentialGateway)
    gateway.unix_path = tmp_path / "fixture.sock"
    gateway.token = "synthetic-run-token"
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *a, **kw: "owned-container\n")

    def execute(command, **kwargs):
        calls.append(command)
        if command[1] == "exec":
            raise subprocess.CalledProcessError(1, command, stderr=b"untrusted-secret-output")
        if command[1] == "stop":
            return SimpleNamespace(returncode=1)
        assert command == ["docker", "rm", "-f", "owned-container"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime.subprocess, "run", execute)
    with pytest.raises(runtime.ContainerStartupError) as caught:
        runtime.container(tmp_path, tmp_path, tmp_path, "fixture-image", gateway=gateway)
    assert caught.value.container_id == "owned-container"
    assert caught.value.cleanup_details == dict(stopped=False, removed=True, errors=["RuntimeError"])
    receipt = (tmp_path / "container-ownership.json").read_text()
    assert "untrusted-secret-output" not in receipt + str(caught.value)
    assert calls[-1] == ["docker", "rm", "-f", "owned-container"]


def test_sigterm_unwinds_attempt_and_restores_handlers(tmp_path, monkeypatch):
    state = []
    before = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}

    class Gateway:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            state.append("gateway-open")
        def __exit__(self, *args):
            state.append("gateway-closed")

    class Adapter:
        def __init__(self, *args):
            pass
        def run(self, *args, **kwargs):
            signal.raise_signal(signal.SIGTERM)
            pytest.fail("SIGTERM should interrupt the solver")

    def stop(identity):
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_IGN
        state.append("container-stopped")
        return dict(stopped=True)

    monkeypatch.setattr(run, "CredentialGateway", Gateway)
    monkeypatch.setattr(run, "mounts", lambda *args: [])
    monkeypatch.setattr(run, "instructions", lambda *args, **kwargs: "offline fixture")
    monkeypatch.setitem(run.BACKENDS, "claude-code-single-agent", Adapter)
    monkeypatch.setattr(runtime, "container", lambda *args, **kwargs: "owned-container")
    monkeypatch.setattr(runtime, "stop_container", stop)
    monkeypatch.setattr(run.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    args = SimpleNamespace(output=tmp_path, backend="claude-code-single-agent", data=tmp_path,
                           image="fixture", timeout=900, web_search=None, max_web_requests=None)
    task = SimpleNamespace(id="fixture", benchmark="dataclawbench", question="offline", web=False)
    with pytest.raises(KeyboardInterrupt):
        with run.graceful_signals():
            run.attempt(task, args, "synthetic-host-secret")
    assert state == ["gateway-open", "container-stopped", "gateway-closed"]
    assert {number: signal.getsignal(number) for number in before} == before
    report = json.loads((tmp_path / task.id / args.backend / "report.json").read_text())
    assert report["status"] == "interrupted"
    assert report["cleanup"]["stopped"] is True


@pytest.mark.parametrize('backend', ['claude-code-single-agent','claude-code-subagents'])
def test_failed_stop_still_force_removes_baseline_container(tmp_path, monkeypatch, backend):
    events=[]
    class Gateway:
        def __init__(self, *a, **kw):pass
        def __enter__(self):return self
        def __exit__(self, *a):events.append('gateway-closed')
    class Adapter:
        def __init__(self, *a):pass
        def run(self, *a, **kw):return dict(status='cli_exited')
    def stop(identity):raise RuntimeError('synthetic stop failure')
    def remove(command, **kwargs):
        assert command==['docker','rm','-f','owned-container']
        assert kwargs['timeout']==15
        events.append('force-removed')
    monkeypatch.setattr(run, 'CredentialGateway', Gateway)
    monkeypatch.setattr(run, 'mounts', lambda *a:[])
    monkeypatch.setattr(run, 'instructions', lambda *a, **kw:'offline')
    monkeypatch.setitem(run.BACKENDS, backend, Adapter)
    monkeypatch.setattr(runtime, 'container', lambda *a, **kw:'owned-container')
    monkeypatch.setattr(runtime, 'stop_container', stop)
    monkeypatch.setattr(run.subprocess, 'run', remove)
    args=SimpleNamespace(output=tmp_path,backend=backend,data=tmp_path,image='fixture',
                         timeout=60,web_search=None,max_web_requests=None)
    task=SimpleNamespace(id='fixture',benchmark='dataclawbench',question='offline',web=False)
    result=run.attempt(task,args,'synthetic')
    assert result['status']=='cleanup_failed'
    assert events==['force-removed','gateway-closed']
    assert json.loads((tmp_path/task.id/backend/'report.json').read_text())['status']=='cleanup_failed'
