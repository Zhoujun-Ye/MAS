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


def test_tunnel_is_reverse_unix_not_a_public_tcp_proxy():
    command=web_tunnel.ssh_command()
    assert command[command.index('-R')+1]==web_tunnel.REMOTE_SOCKET+':127.0.0.1:7897'
    assert 'BatchMode=yes' in command and 'ExitOnForwardFailure=yes' in command
    assert 'StreamLocalBindMask=0177' in command and '-g' not in command
    assert 'ServerAliveInterval=15' in command


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
    connection._context=SimpleNamespace(wrap_socket=lambda value,server_hostname:
        observed.update(socket=value,server_hostname=server_hostname) or value)
    connection.connect()
    assert observed==dict(tunnel_host='8.8.8.8',socket=sock,server_hostname='en.wikipedia.org')
    connection.sock=None


def test_frozen_policy_requires_tunnel_without_environment_proxy_fallback():
    policy=web_policy.configuration()
    assert policy['protocol']=='web-v3' and policy['fetch_backend']=='local-clash-unix'
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
