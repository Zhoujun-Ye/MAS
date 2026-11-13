"""Absolute host transport deadlines, using local socket pairs only."""

import http.client
import socket
import threading
from types import SimpleNamespace

import pytest

from harness.runtime_support import web_fetch


def test_slow_drip_headers_cannot_extend_fetch_deadline(monkeypatch):
    client, server = socket.socketpair()
    done = threading.Event()

    class Connection:
        sock = client
        def set_tunnel(self, *args):pass
        def request(self, *args, **kwargs):pass
        def getresponse(self):
            response = http.client.HTTPResponse(self.sock)
            try:response.begin()
            except BaseException:
                response.close()
                raise
            return response
        def close(self):self.sock.close()

    def drip():
        try:
            server.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 0\r\nX-Slow: ')
            for _ in range(30):
                if done.wait(0.02):return
                server.sendall(b'x')
            server.sendall(b'\r\n\r\n')
        except OSError:pass

    monkeypatch.setattr(web_fetch, 'public_address', lambda *a:'8.8.8.8')
    monkeypatch.setattr(web_fetch, 'proxy_connection', lambda *a:Connection())
    worker = threading.Thread(target=drip)
    worker.start()
    try:
        with pytest.raises(TimeoutError):
            web_fetch.fetch('https://example.org', timeout=0.15)
    finally:
        done.set()
        server.close()
        client.close()
        worker.join(timeout=2)
    assert not worker.is_alive()


def test_readiness_interrupts_blocked_connect(monkeypatch):
    client, server = socket.socketpair()
    class Connection:
        sock = client
        def set_tunnel(self, *args):pass
        def connect(self):self.sock.recv(1)
        def close(self):self.sock.close()
    monkeypatch.setattr(web_fetch, 'check_proxy', lambda:None)
    monkeypatch.setattr(web_fetch, 'public_address', lambda *a:'8.8.8.8')
    monkeypatch.setattr(web_fetch, 'proxy_connection', lambda *a:Connection())
    try:
        with pytest.raises(TimeoutError, match='readiness deadline'):
            web_fetch.check_ready(timeout=0.1)
    finally:
        client.close()
        server.close()


def test_late_socket_is_interrupted_and_successful_guard_is_cancelled(monkeypatch):
    stopped=[]
    resource=SimpleNamespace(shutdown=lambda how:stopped.append(how))
    guard=web_fetch.RequestDeadline(0.01)
    guard.expire()
    with pytest.raises(TimeoutError):guard.watch(resource)
    assert stopped == [socket.SHUT_RDWR]
    stopped.clear()
    class Timer:
        def __init__(self, timeout, callback):self.callback=callback;self.cancelled=False
        def start(self):pass
        def cancel(self):self.cancelled=True
        def join(self):pass
        def is_alive(self):return False
        def fire(self):
            if not self.cancelled:self.callback()
    monkeypatch.setattr(web_fetch.threading,'Timer',Timer)
    with web_fetch.RequestDeadline(0.02) as active:
        active.watch(resource)
    active.timer.fire()
    assert active.timer.cancelled
    assert not stopped
    assert not active.timer.is_alive()


@pytest.mark.parametrize('timeout', [0, -1, float('nan'), float('inf')])
def test_deadline_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError):web_fetch.RequestDeadline(timeout)
