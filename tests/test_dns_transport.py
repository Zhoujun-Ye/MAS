"""Synthetic Unix-only DNS bridge regressions; no provider or external DNS."""

from concurrent.futures import ThreadPoolExecutor
import http.server
import json
import socket
import socketserver
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from harness.runtime_support import dns_transport as dns, web_fetch
from scripts.server import web_tunnel

CONNECT = socket.socket.connect


@pytest.fixture(autouse=True)
def unix_only(monkeypatch):
    def connect(client, address):
        assert client.family == socket.AF_UNIX, 'Only synthetic Unix IPC is allowed'
        return CONNECT(client, address)
    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: pytest.fail('No server DNS fallback'))


@pytest.fixture
def state(tmp_path):
    p = tmp_path/'private';p.mkdir(mode=0o700)
    return p


def test_bridge_binds_hostname_public_addresses_and_never_calls_server_dns(state, monkeypatch):
    calls = []
    def query(path, host, kind, timeout):
        calls.append((host,kind))
        return ['8.8.8.8'] if kind=='A' else ['2606:4700:4700::1111']
    monkeypatch.setattr(dns, 'controller_query', query)
    path = state/'dns.sock'
    with dns.bridge(path):
        assert path.stat().st_mode & 0o777 == 0o600
        assert dns.resolve('Example.ORG.',1,path)==['8.8.8.8','2606:4700:4700::1111']
        assert calls==[('example.org','A'),('example.org','AAAA')]
        assert dns.resolve('8.8.4.4',1,path)==['8.8.4.4']
        assert len(calls)==2
    assert not path.exists()


@pytest.mark.parametrize('value', ['127.0.0.1','169.254.169.254','198.18.0.1','::1','224.0.0.1'])
def test_private_literal_or_fake_dns_address_is_rejected(value):
    with pytest.raises(dns.DNSError,match='non_public_address'):
        dns.resolve(value,1)


@pytest.mark.parametrize('value', ['', 'localhost', '-bad.example','a..example','a.example/path',
                                   'a.example\nGET /configs','x'*64+'.org','fe80::1%lo'])
def test_invalid_names_do_not_reach_controller(value):
    with pytest.raises(dns.DNSError,match='invalid_target'):
        dns.resolve(value,1)


def test_missing_insecure_and_symlink_socket_fail_closed(state,monkeypatch):
    path = state/'dns.sock'
    for candidate in (path,state/'linked'):
        with pytest.raises(dns.DNSError,match='proxy_unavailable'):
            dns.resolve('example.org',1,candidate)
    monkeypatch.setattr(dns,'controller_query',lambda *a:['8.8.8.8'])
    with dns.bridge(path):
        link=state/'linked';link.symlink_to(path)
        with pytest.raises(dns.DNSError,match='proxy_unavailable'):
            dns.resolve('example.org',1,link)
        path.chmod(0o666)
        with pytest.raises(dns.DNSError,match='proxy_unavailable'):
            dns.resolve('example.org',1,path)


def test_mixed_answers_and_control_failures_do_not_use_fallback(state,monkeypatch):
    monkeypatch.setattr(dns,'controller_query',lambda p,h,k,t:['8.8.8.8','127.0.0.1'] if k=='A' else [])
    path=state/'dns.sock'
    with dns.bridge(path):
        with pytest.raises(dns.DNSError,match='non_public_address'):
            dns.resolve('example.org',1,path)
        monkeypatch.setattr(dns,'controller_query',lambda *a:(_ for _ in ()).throw(OSError('PRIVATE detail')))
        with pytest.raises(dns.DNSError) as e:
            dns.resolve('example.org',1,path)
        assert 'PRIVATE' not in str(e.value)


def test_concurrent_clients_do_not_mix_names_or_answers(state,monkeypatch):
    monkeypatch.setattr(dns,'controller_query',lambda p,h,k,t:['8.8.8.8'] if k=='A' else [])
    path=state/'dns.sock'
    with dns.bridge(path):
        with ThreadPoolExecutor(8) as pool:
            assert list(pool.map(lambda n:dns.resolve(f'{n}.example.org',2,path),range(12)))==[['8.8.8.8']]*12


@pytest.mark.parametrize('fault',['wrong_host','wrong_protocol','oversize','private','slow','error'])
def test_untrusted_or_slow_bridge_response_is_bounded(state,fault):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(8192)
            value=dict(protocol=dns.PROTOCOL,host='example.org',addresses=['8.8.8.8'])
            if fault=='wrong_host':value['host']='other.example'
            elif fault=='wrong_protocol':value['protocol']='other'
            elif fault=='oversize':value['extra']='x'*9000
            elif fault=='private':value['addresses'].append('::1')
            elif fault=='error':value['error']='PRIVATE_PAYLOAD'
            data=(json.dumps(value)+'\n').encode()
            try:
                if fault=='slow':
                    for b in data:
                        self.request.sendall(bytes([b]));time.sleep(.01)
                else:self.request.sendall(data)
            except OSError:pass
    path=state/'dns.sock'
    with socketserver.UnixStreamServer(str(path),Handler) as server:
        path.chmod(0o600)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        started=time.monotonic()
        try:
            with pytest.raises(dns.DNSError) as error:dns.resolve('example.org',.05 if fault=='slow' else 1,path)
            assert 'PRIVATE' not in str(error.value)
            if fault=='slow':assert time.monotonic()-started<.3
        finally:server.shutdown();thread.join()


@pytest.mark.parametrize('fault',[None,'wrong_question','truncated','nxdomain','oversize','slow_headers','malformed_json'])
def test_controller_is_dns_only_and_validates_response_and_absolute_deadline(state,fault):
    calls=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u=urlsplit(self.path);q=parse_qs(u.query)
            assert u.path=='/dns/query' and set(q)=={'name','type'}
            calls.append(q)
            value=dict(Status=0,TC=False,Question=[dict(Name=q['name'][0]+'.',Qtype=1,Qclass=1)],
                       Answer=[dict(type=5,data='alias.example.'),dict(type=1,data='8.8.8.8')])
            if fault=='wrong_question':value['Question'][0]['Name']='other.example.'
            elif fault=='truncated':value['TC']=True
            elif fault=='nxdomain':value['Status']=3
            elif fault=='oversize':value['extra']='x'*65536
            body=json.dumps(value).encode()
            if fault=='malformed_json':body=b'{broken'
            try:
                if fault=='slow_headers':
                    for b in b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\n':
                        self.connection.sendall(bytes([b]));time.sleep(.01)
                else:
                    self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
                    self.wfile.write(body)
            except OSError:pass
        def log_message(self,*args):pass
    path=state/'controller.sock'
    with socketserver.UnixStreamServer(str(path),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        started=time.monotonic()
        try:
            if fault:
                with pytest.raises(dns.DNSError) as error:dns.controller_query(path,'example.org','A',.05 if fault=='slow_headers' else 1)
                if fault=='slow_headers':assert time.monotonic()-started<.3
                if fault=='malformed_json':
                    assert error.value.reason=='dns_response_invalid'
                    assert error.value.stage=='clash_dns_decode'
            else:assert dns.controller_query(path,'example.org','A',1)==['8.8.8.8']
            assert len(calls)==1
        finally:server.shutdown();thread.join()


def test_controller_socket_timeout_is_dns_timeout_even_before_timer_fires(state,monkeypatch):
    def fail(*a):raise socket.timeout('PRIVATE detail')
    monkeypatch.setattr(socket.socket,'connect',fail)
    with pytest.raises(dns.DNSError) as error:
        dns.controller_query(state/'controller.sock','example.org','A',1)
    assert error.value.reason=='dns_timeout' and error.value.stage=='clash_dns_connect'
    assert 'PRIVATE' not in str(error.value)


def test_controller_failure_stage_crosses_bridge_without_private_error_text(state,monkeypatch):
    def fail(*a):raise dns.DNSError('proxy_unavailable','clash_dns_connect')
    monkeypatch.setattr(dns,'controller_query',fail)
    path=state/'dns.sock'
    with dns.bridge(path):
        with pytest.raises(dns.DNSError) as error:dns.resolve('example.org',1,path)
        assert error.value.stage=='clash_dns_connect'
        with pytest.raises(web_fetch.ProxyUnavailable) as error:
            monkeypatch.setattr(web_fetch,'resolve_dns',lambda host,timeout:dns.resolve(host,timeout,path))
            web_fetch.public_address('example.org',443,1)
        assert error.value.stage=='clash_dns_connect'


def test_refuse_live_or_foreign_local_socket_and_preserve_replacement(state,monkeypatch):
    path=state/'dns.sock'
    monkeypatch.setattr(dns,'controller_query',lambda *a:['8.8.8.8'])
    with dns.bridge(path):
        with pytest.raises(dns.DNSError):
            with dns.bridge(path):pass
        path.unlink();path.write_text('unrelated replacement')
    assert path.read_text()=='unrelated replacement'


def test_dns_forward_is_separate_private_unix_not_controller_api():
    cmd=web_tunnel.ssh_command()
    forwards=[cmd[i+1] for i,x in enumerate(cmd) if x=='-R']
    assert forwards==[web_tunnel.REMOTE_SOCKET+':127.0.0.1:7897',
                      web_tunnel.REMOTE_DNS_SOCKET+':'+str(web_tunnel.STATE/'dns.sock')]
    assert not any('mihomo' in x or '9097' in x for x in forwards)


def test_dns_proxy_failure_pauses_web_dispatch(monkeypatch):
    monkeypatch.setattr(web_fetch,'resolve_dns',lambda *a:(_ for _ in ()).throw(dns.DNSError('proxy_unavailable')))
    with pytest.raises(web_fetch.ProxyUnavailable):web_fetch.public_address('example.org',443,1)
