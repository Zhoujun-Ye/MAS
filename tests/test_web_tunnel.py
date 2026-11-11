"""Offline reverse-socket lifecycle, TLS identity and fail-closed checks."""

import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.server import web_tunnel
from harness.runtime_support import web_fetch,web_policy


def test_launchd_reinstall_tolerates_only_transient_bootout_race(monkeypatch):
    bootstrap_results=iter([5,0]);sleeps=[]
    def run(command, **kwargs):
        code=next(bootstrap_results) if command[1]=='bootstrap' else 113
        return subprocess.CompletedProcess(command,code)
    monkeypatch.setattr(web_tunnel.subprocess,'run',run)
    monkeypatch.setattr(web_tunnel.time,'sleep',sleeps.append)
    assert web_tunnel.bootstrap_service('gui/fixture/io.mas.web-tunnel')==2
    assert sleeps==[0.2]


@pytest.mark.parametrize('code,loaded', [(1,False),(5,True)])
def test_launchd_other_errors_and_existing_service_are_not_hidden(monkeypatch,code,loaded):
    monkeypatch.setattr(web_tunnel.subprocess,'run',lambda command,**kw:
        subprocess.CompletedProcess(command,code if command[1]=='bootstrap' else (0 if loaded else 113)))
    monkeypatch.setattr(web_tunnel.time,'sleep',lambda *a:pytest.fail('Do not retry this error'))
    with pytest.raises(subprocess.CalledProcessError):
        web_tunnel.bootstrap_service('fixture')


def test_launchd_transient_retry_is_bounded(monkeypatch):
    clock=iter([0,11])
    monkeypatch.setattr(web_tunnel.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(web_tunnel.subprocess,'run',lambda command,**kw:subprocess.CompletedProcess(command,5))
    with pytest.raises(subprocess.CalledProcessError):web_tunnel.bootstrap_service('fixture')


def test_install_waits_for_known_old_registration_to_disappear(monkeypatch):
    states=iter([0,0,113]);commands=[];sleeps=[]
    def run(cmd,**kw):
        commands.append(cmd[1])
        return subprocess.CompletedProcess(cmd,next(states) if cmd[1]=='print' else 0)
    monkeypatch.setattr(web_tunnel.subprocess,'run',run)
    monkeypatch.setattr(web_tunnel.time,'sleep',sleeps.append)
    web_tunnel.unload_service('fixture')
    assert commands==['print','bootout','print','print'] and sleeps==[0.2]


def test_install_does_not_bootout_an_absent_registration(monkeypatch):
    commands=[]
    def run(cmd,**kw):
        commands.append(cmd[1]);return subprocess.CompletedProcess(cmd,113)
    monkeypatch.setattr(web_tunnel.subprocess,'run',run)
    web_tunnel.unload_service('fixture')
    assert commands==['print']


def test_install_does_not_hide_failed_bootout_of_live_service(monkeypatch):
    monkeypatch.setattr(web_tunnel.subprocess,'run',lambda cmd,**kw:subprocess.CompletedProcess(cmd,5 if cmd[1]=='bootout' else 0))
    with pytest.raises(subprocess.CalledProcessError):web_tunnel.unload_service('fixture')


def test_tunnel_is_reverse_unix_not_a_public_tcp_proxy():
    command=web_tunnel.ssh_command()
    assert command[command.index('-R')+1]==web_tunnel.REMOTE_SOCKET+':127.0.0.1:7897'
    assert 'BatchMode=yes' in command and 'ExitOnForwardFailure=yes' in command
    assert 'StreamLocalBindMask=0177' in command and '-g' not in command
    assert 'ServerAliveInterval=15' in command
    assert '-NT' not in command and command[-1].endswith(' 60')


@pytest.mark.parametrize('mode',['absent','stale','live','symlink','file'])
def test_only_stale_owned_local_control_socket_is_removed(tmp_path,mode):
    path=tmp_path/'control';listener=None
    target=tmp_path/'protected';target.write_text('unchanged')
    if mode in {'stale','live'}:
        listener=socket.socket(socket.AF_UNIX);listener.bind(str(path))
        if mode=='live':listener.listen(1)
        else:listener.close()
    elif mode=='symlink':path.symlink_to(target)
    elif mode=='file':path.write_text('not a socket')
    try:
        result=subprocess.run([sys.executable,'-c',
            'import sys;from pathlib import Path;from scripts.server import web_tunnel;'
            'web_tunnel.STATE=Path(sys.argv[1]);web_tunnel.clear_stale_control()',str(tmp_path)],
            capture_output=True,text=True,timeout=5)
        assert (result.returncode==0)==(mode in {'absent','stale'})
        assert path.exists()==(mode not in {'absent','stale'})
        assert target.read_text()=='unchanged'
    finally:
        if listener:listener.close()


def test_remote_watchdog_exits_without_heartbeats():
    child=subprocess.Popen([sys.executable,'-c',web_tunnel.WATCHDOG,'0.1'],stdin=subprocess.PIPE)
    try:
        assert child.wait(timeout=3)==0
    finally:
        child.stdin.close()
        if child.poll() is None:child.kill();child.wait()


def test_remote_watchdog_accepts_heartbeats_then_exits_on_eof():
    child=subprocess.Popen([sys.executable,'-c',web_tunnel.WATCHDOG,'2'],stdin=subprocess.PIPE)
    try:
        child.stdin.write(b'\n');child.stdin.flush()
        assert child.poll() is None
        child.stdin.close()
        assert child.wait(timeout=3)==0
    finally:
        if not child.stdin.closed:child.stdin.close()
        if child.poll() is None:child.kill();child.wait()


def test_round_trip_heartbeat_acknowledges_remote_session():
    child=subprocess.Popen([sys.executable,'-c',web_tunnel.WATCHDOG,'2'],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        web_tunnel.heartbeat(child,timeout=1)
        assert child.poll() is None
        child.stdin.close()
        assert child.wait(timeout=3)==0
    finally:
        web_tunnel.stop_child(child)
        if not child.stdin.closed:child.stdin.close()
        child.stdout.close()


def test_alive_master_with_closed_primary_session_is_stopped():
    child=subprocess.Popen([sys.executable,'-c','import os,time;os.close(1);time.sleep(30)'],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        with pytest.raises(ConnectionError,match='session closed'):
            web_tunnel.heartbeat(child,timeout=2)
        assert child.poll() is None
        web_tunnel.stop_child(child)
        assert child.poll() is not None
    finally:
        web_tunnel.stop_child(child);child.stdin.close();child.stdout.close()


def test_heartbeat_is_bounded_even_when_master_process_stays_alive(monkeypatch):
    from io import BytesIO
    child=SimpleNamespace(stdin=BytesIO(),stdout=object())
    seen=[]
    monkeypatch.setattr(web_tunnel.select,'select',lambda r,w,e,t:seen.append(t) or ([],[],[]))
    with pytest.raises(TimeoutError):web_tunnel.heartbeat(child,timeout=.1)
    assert seen==[.1] and child.stdin.getvalue()==b'\n'


def test_stubborn_owned_ssh_is_killed_within_launchd_exit_window():
    calls=[]
    def wait(timeout):
        calls.append(('wait',timeout))
        if len(calls)==2:raise subprocess.TimeoutExpired('synthetic-ssh',timeout)
        return 0
    child=SimpleNamespace(poll=lambda:None,terminate=lambda:calls.append('terminate'),
                          kill=lambda:calls.append('kill'),wait=wait)
    web_tunnel.stop_child(child)
    assert calls==['terminate',('wait',2),'kill',('wait',2)]


@pytest.mark.parametrize('mode',['absent','stale','live','symlink','open-directory'])
def test_remote_prepare_only_unlinks_stale_owned_socket(tmp_path,mode):
    root=tmp_path/'.cache/mas-web';root.mkdir(parents=True,mode=0o700)
    path=root/'clash.sock';listener=None
    target=tmp_path/'do-not-delete';target.write_text('protected')
    if mode in {'stale','live'}:
        listener=socket.socket(socket.AF_UNIX);listener.bind(str(path))
        if mode=='live':listener.listen(1)
        else:listener.close()
    if mode=='symlink':path.symlink_to(target)
    if mode=='open-directory':root.chmod(0o755)
    try:
        result=subprocess.run([sys.executable,'-c',web_tunnel.PREPARE,str(path)],
            env={**os.environ,'HOME':str(tmp_path)},capture_output=True,text=True,timeout=5)
        assert (result.returncode==0)==(mode in {'absent','stale'})
        assert target.read_text()=='protected'
        if mode in {'live','symlink'}:assert path.exists()
    finally:
        if listener:listener.close()


def test_proxy_socket_permissions_and_missing_tunnel_fail_closed(tmp_path,monkeypatch):
    root=tmp_path/'proxy';root.mkdir(mode=0o700)
    path=root/'clash.sock'
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:pytest.fail('No direct TCP fallback'))
    with pytest.raises(web_fetch.ProxyUnavailable):web_fetch.open_proxy(path,1)
    server=socket.socket(socket.AF_UNIX);server.bind(str(path));server.listen(1);path.chmod(0o600)
    try:
        web_fetch.check_proxy(path)
        path.chmod(0o666)
        with pytest.raises(web_fetch.ProxyUnavailable):web_fetch.open_proxy(path,1)
    finally:server.close()


def test_https_connect_pins_ip_but_verifies_hostname(monkeypatch):
    observed={};sock=object()
    connection=web_fetch.ProxyHTTPSConnection('en.wikipedia.org',443)
    connection.set_tunnel('8.8.8.8',443)
    def connected(value):
        observed['tunnel_host']=value._tunnel_host;value.sock=sock
    monkeypatch.setattr(web_fetch.ProxyHTTPConnection,'connect',connected)
    secure=SimpleNamespace(do_handshake=lambda:observed.update(handshake=True))
    connection._context=SimpleNamespace(wrap_socket=lambda value,server_hostname,do_handshake_on_connect:
        observed.update(socket=value,server_hostname=server_hostname,
                        automatic_handshake=do_handshake_on_connect) or secure)
    connection.connect()
    assert observed==dict(tunnel_host='8.8.8.8',socket=sock,server_hostname='en.wikipedia.org',
                         automatic_handshake=False,handshake=True)
    connection.sock=None


def test_frozen_policy_requires_tunnel_without_environment_proxy_fallback():
    policy=web_policy.configuration()
    assert policy['protocol']=='web-v5' and policy['fetch_backend']=='local-clash-unix'
    assert policy['dns_backend']=='local-clash-dns-unix'
    assert policy['fetch_proxy_socket']==str(web_policy.PROXY_SOCKET)
    assert policy['fetch_proxy_failure']=='fail closed; no direct fallback'


def test_lost_proxy_pauses_new_dispatch_without_killing_active_solver(tmp_path,monkeypatch):
    import json,time
    from scripts.studies import benchmark_matrix as matrix
    from test_fullscale_infra import setup_matrix,FakeProcess
    args=setup_matrix(tmp_path,monkeypatch);terminated=[]
    class LostProxy(FakeProcess):
        def __init__(self,cmd,**kw):
            self.paid='--execute' in cmd
            super().__init__(cmd,**kw)
            if self.paid:
                out=Path(cmd[cmd.index('--output')+1]);task=cmd[cmd.index('--task-id')+1]
                (out/task/'claude-code-subagents/gateway-requests.jsonl').write_text(json.dumps(dict(
                    event='finished',route='/v1/tools/fetch',web_proxy_unavailable=True)))
        def wait(self,**kw):
            if self.paid:time.sleep(1.2)
            return 0
        def terminate(self):terminated.append(True)
    monkeypatch.setattr(matrix.subprocess,'Popen',LostProxy)
    monkeypatch.setattr(matrix,'grade_attempt',lambda b,t,k,*a,**kw:dict(
        benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0))
    assert matrix.main(args(tmp_path/'out'))==1
    summary=json.loads((tmp_path/'out/summary.json').read_text())
    assert summary['interrupted'] and not terminated
    assert sorted(r['status'] for r in summary['rows'])==['cli_exited','not_started']
