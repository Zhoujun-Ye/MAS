import io
import http.client
import json
import socket
import threading
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

from harness.runtime_support import credential_gateway, tools
from harness.runtime_support.credential_gateway import CredentialGateway


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch):
    def guarded(original):
        def connect(sock, address):
            if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                raise AssertionError("Gateway protocol tests permit loopback only")
            return original(sock, address)
        return connect
    monkeypatch.setattr(socket.socket, "connect", guarded(_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(_connect_ex))


def post(gateway, path="/anthropic/v1/messages", payload=None):
    request = urllib.request.Request(gateway.url + path,
        data=json.dumps(payload or {"model": "deepseek-flash", "input": "private question"}).encode(),
        headers={"Authorization": "Bearer " + gateway.token})
    return urllib.request.urlopen(request, timeout=3)


@pytest.mark.parametrize('override', [
    {'temperature': 0}, {'temperature': '1.0'}, {'temperature': True},
    {'thinking': {'type': 'adaptive'}}, {'thinking': None},
    {'output_config': {'effort': 'high'}},
])
def test_inference_drift_is_rejected_before_paid_dispatch(tmp_path, monkeypatch, override):
    from harness.runtime_support.inference import configuration
    monkeypatch.setattr(credential_gateway, 'open_upstream', lambda *a: pytest.fail('Configuration drift dispatched'))
    payload = dict(model='deepseek-flash', temperature=1.0, thinking={'type': 'disabled'}, max_tokens=32000)
    payload.update(override)
    with CredentialGateway('synthetic', ledger_path=tmp_path/'ledger', inference_policy=configuration()) as gateway:
        with pytest.raises(urllib.error.HTTPError) as caught:
            post(gateway, payload=payload)
        assert caught.value.code == 400
    assert gateway.summary()['upstream_attempts'] == 0


def test_inference_validation_never_rewrites_native_payload(tmp_path, monkeypatch):
    from harness.runtime_support.inference import configuration
    payload = dict(model='deepseek-flash', temperature=1.0, thinking={'type': 'disabled'}, max_tokens=32000,
                   messages=[{'role': 'user', 'content': 'private question'}])
    def upstream(request):
        assert request.data == json.dumps(payload).encode()
        response = io.BytesIO(b'{"id":"synthetic","usage":{"input_tokens":1,"output_tokens":1}}')
        response.status = 200; response.headers = {'Content-Type': 'application/json'}
        return response
    monkeypatch.setattr(credential_gateway, 'open_upstream', upstream)
    with CredentialGateway('synthetic', ledger_path=tmp_path/'ledger', inference_policy=configuration()) as gateway:
        post(gateway, payload=payload).close()
    rows = [json.loads(x) for x in (tmp_path/'ledger').read_text().splitlines()]
    assert rows[-1]['request_parameters']['temperature'] == 1.0
    assert rows[-1]['request_parameters']['thinking'] == 'disabled'
    assert rows[-1]['request_parameters']['max_tokens'] == 32000
    assert rows[-1]['request_parameters']['effort'] is None
    assert 'private question' not in (tmp_path/'ledger').read_text()


def test_error_preserves_protocol_without_secrets(tmp_path, monkeypatch):
    ledger = tmp_path / "host-ledger.jsonl"
    calls = []
    def upstream(request):
        calls.append(request)
        body = dict(type="error", error=dict(type="rate_limit_error", message="Back off synthetic-secret",
                                            headers={"Authorization": "Bearer synthetic-secret"}))
        raise urllib.error.HTTPError(request.full_url, 429, "ignored", {
            "request-id": "req-fixture", "Retry-After": "2", "x-ratelimit-remaining-requests": "0",
            "Set-Cookie": "unsafe", "Location": "https://example.invalid/"}, io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(credential_gateway, "open_upstream", upstream)
    with CredentialGateway("synthetic-secret", ledger_path=ledger) as gateway:
        with pytest.raises(urllib.error.HTTPError) as caught:
            post(gateway)
        assert caught.value.code == 429
        assert caught.value.headers["Retry-After"] == "2"
        assert caught.value.headers["request-id"] == "req-fixture"
        assert caught.value.headers.get("Set-Cookie") is None
        assert caught.value.headers.get("Location") is None
        body = json.loads(caught.value.read())
        assert body["error"]["type"] == "rate_limit_error"
        assert body["error"]["headers"] == "[REDACTED]"
        assert "synthetic-secret" not in json.dumps(body)
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [r["event"] for r in rows] == ["started", "dispatched", "finished"]
    assert rows[-1]["provider_request_id"] == "req-fixture"
    assert rows[-1]["outcome"] == "upstream_rejected"
    assert rows[-1]['rate_limit_headers'] == {'retry-after': '2', 'x-ratelimit-remaining-requests': '0'}
    assert len(calls) == 1
    assert "private question" not in ledger.read_text()
    assert "synthetic-secret" not in ledger.read_text()
    assert gateway.summary()["upstream_attempts"] == 1


def test_sse_usage_recorded_without_output_text(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "text/event-stream", "x-request-id": "req-sse"}
    frames = [dict(type="message_start", message=dict(id="msg-fixture", usage=dict(input_tokens=100))),
              dict(type="content_block_delta", delta=dict(text="private generated answer")),
              dict(type="message_delta", usage=dict(output_tokens=12))]
    body = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames).encode()
    monkeypatch.setattr(credential_gateway, "open_upstream", lambda request: Response(body))
    ledger = tmp_path / "ledger.jsonl"
    with CredentialGateway("synthetic-secret", ledger_path=ledger) as gateway:
        with post(gateway, "/anthropic/v1/messages") as response:
            assert response.read() == body
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row["usage"] == dict(input_tokens=100, output_tokens=12)
    assert row["usage_status"] == "observed"
    assert row["provider_response_id"] == "msg-fixture"
    assert "private generated answer" not in ledger.read_text()
    assert row["origin"] == "unverified"


def test_open_transport_failure_is_not_provider_502_and_is_not_retried(tmp_path, monkeypatch):
    calls = []
    def upstream(request):
        calls.append(request)
        raise ConnectionResetError('synthetic-secret private transport detail')
    monkeypatch.setattr(credential_gateway, 'open_upstream', upstream)
    ledger = tmp_path/'ledger'
    with CredentialGateway('synthetic-secret', ledger_path=ledger) as gateway:
        with pytest.raises(urllib.error.HTTPError) as caught:
            post(gateway)
        assert caught.value.code == 502
        caught.value.close()
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row['outcome'] == 'transport_error' and row['transport_error_class'] == 'ConnectionResetError'
    assert len(calls) == 1 and 'synthetic-secret' not in ledger.read_text()


@pytest.mark.parametrize('failure', ['transport', 'http', 'error_body'])
def test_upstream_failure_is_preserved_when_error_response_is_interrupted(tmp_path, monkeypatch, failure):
    from harness.runtime_support.admission import infrastructure_health
    class BrokenBody(io.BytesIO):
        def read(self, *args):
            raise ConnectionResetError('synthetic-secret')
    calls = []
    def upstream(request):
        calls.append(request)
        if failure == 'transport':
            raise ConnectionResetError('synthetic-secret')
        body = BrokenBody() if failure == 'error_body' else io.BytesIO(b'{"type":"error"}')
        raise urllib.error.HTTPError(request.full_url, 503, 'synthetic-secret', {}, body)
    def broken_headers(self):
        raise BrokenPipeError('synthetic-secret')
    monkeypatch.setattr(credential_gateway, 'open_upstream', upstream)
    ledger = tmp_path/'ledger'
    with CredentialGateway('synthetic-secret', ledger_path=ledger) as gateway:
        monkeypatch.setattr(gateway.server.RequestHandlerClass, 'end_headers', broken_headers)
        with pytest.raises(http.client.RemoteDisconnected):
            post(gateway)
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row['outcome'] == ('transport_error' if failure == 'transport' else 'upstream_rejected')
    assert row['http_status'] == (502 if failure == 'transport' else 503)
    assert row['response_delivery'] == 'interrupted'
    health = infrastructure_health(ledger)
    assert health['infra_degraded'] is True
    assert bool(health['upstream_5xx']) is (failure != 'transport')
    assert len(calls) == 1 and 'synthetic-secret' not in ledger.read_text()


def test_observer_fault_is_not_misreported_as_upstream_transport_error(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        status = 200
        headers = {'Content-Type': 'application/json'}
    def broken_observer(self, chunk):
        raise ValueError('synthetic-secret')
    monkeypatch.setattr(credential_gateway, 'open_upstream', lambda request: Response(b'{}'))
    monkeypatch.setattr(credential_gateway.UsageObserver, 'feed', broken_observer)
    ledger = tmp_path/'ledger'
    with CredentialGateway('synthetic-secret', ledger_path=ledger) as gateway:
        with post(gateway) as response:
            response.read()
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row['outcome'] == 'gateway_error' and row['error_type'] == 'ValueError'
    assert 'synthetic-secret' not in ledger.read_text()


@pytest.mark.parametrize('error', [TimeoutError, ConnectionResetError, BrokenPipeError])
def test_partial_stream_is_unknown_not_zero(tmp_path, monkeypatch, error):
    class Response:
        status = 200
        headers = {"Content-Type": "text/event-stream"}
        count = 0
        def read1(self, size):
            self.count += 1
            if self.count == 1:
                return b'data: {"usage":{"input_tokens":17}}\n\n'
            raise error('synthetic-secret must never appear in ledger')
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(credential_gateway, "open_upstream", lambda request: Response())
    ledger = tmp_path / "ledger.jsonl"
    with CredentialGateway("synthetic-secret", ledger_path=ledger) as gateway:
        with post(gateway) as response:
            response.read()
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row["outcome"] == "transport_interrupted"
    assert row['transport_error_class'] == error.__name__
    assert 'synthetic-secret' not in ledger.read_text()
    assert row["completion"] == "unknown"
    assert row["usage"] == {"input_tokens": 17}
    assert row["usage_status"] == "partial"
    assert gateway.summary()["unknown_completions"] == 1


def test_invalid_web_payload_does_not_consume_reservation(tmp_path, monkeypatch):
    calls = []
    class Response(io.BytesIO):
        status = 200
        headers = {}
    monkeypatch.setattr(credential_gateway, "open_upstream", lambda request: calls.append(request) or Response(
        b'{"results":[{"url":"https://example.org","title":"fixture"}]}'))
    ledger = tmp_path / "ledger.jsonl"
    with CredentialGateway("synthetic-secret", ledger_path=ledger, web_limit=1) as gateway:
        invalid = urllib.request.Request(gateway.url + "/v1/tools/search", data=b'[]',
            headers={"Authorization": "Bearer " + gateway.token})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(invalid, timeout=3)
        assert caught.value.code == 400
        caught.value.close()
        with post(gateway, "/v1/tools/search", {"query": "fixture"}) as response:
            response.read()
        with pytest.raises(urllib.error.HTTPError) as caught:
            post(gateway, "/v1/tools/fetch", {"url": "https://example.invalid"})
        assert caught.value.code == 429
        assert json.loads(caught.value.read())["error"]["type"] == "run_web_limit_exhausted"
    assert len(calls) == 1
    assert gateway.summary()["web_reservations"] == 1
    assert gateway.summary()["requests_received"] == 3


@pytest.mark.parametrize("kind,message", [("run_web_limit_exhausted", "budget exhausted"),
                                         ("rate_limit_error", "provider rate limit")])
def test_helper_429_is_actionable_and_not_retried(monkeypatch, kind, message):
    calls = []
    def invoke(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(error=dict(type=kind))) + "\n429")
    monkeypatch.setattr(tools.subprocess, "run", invoke)
    with pytest.raises(RuntimeError, match=message):
        tools.json_post("http://127.0.0.1/example", {}, "synthetic-token")
    assert len(calls) == 1


def test_shutdown_blocks_incomplete_body_before_provider(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(credential_gateway, "open_upstream", lambda request: calls.append(request))
    gateway = CredentialGateway("synthetic-secret", ledger_path=tmp_path / "ledger.jsonl")
    started = threading.Event()
    receipt = gateway.receipt
    def observe(row):
        receipt(row)
        if row["event"] == "started":
            started.set()
    monkeypatch.setattr(gateway, "receipt", observe)
    gateway.__enter__()
    with socket.create_connection(gateway.server.server_address, timeout=3) as client:
        headers = ("POST /anthropic/v1/messages HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer " + gateway.token
                   + "\r\nContent-Length: 100\r\n\r\n{")
        client.sendall(headers.encode())
        assert started.wait(3)
        gateway.__exit__(None, None, None)
    assert calls == []
    assert gateway.summary()["upstream_attempts"] == 0
    assert gateway.ledger_closed


def test_shutdown_records_committed_request_as_unknown(tmp_path, monkeypatch):
    dispatched, release, returned = threading.Event(), threading.Event(), threading.Event()
    class Response(io.BytesIO):
        status = 200
        headers = {}
    def upstream(request):
        dispatched.set()
        assert release.wait(5)
        returned.set()
        return Response(b'{}')
    monkeypatch.setattr(credential_gateway, "open_upstream", upstream)
    ledger = tmp_path / "ledger.jsonl"
    gateway = CredentialGateway("synthetic-secret", ledger_path=ledger)
    gateway.__enter__()
    def client():
        try:
            with post(gateway) as response:
                response.read()
        except (OSError, urllib.error.URLError):
            pass
        except Exception:
            # A deliberately closed HTTP connection can also raise RemoteDisconnected.
            pass
    thread = threading.Thread(target=client)
    thread.start()
    try:
        assert dispatched.wait(3)
        gateway.__exit__(None, None, None)
        frozen = ledger.read_bytes()
        assert gateway.summary()["unknown_completions"] == 1
        assert json.loads(frozen.splitlines()[-1])["outcome"] == "shutdown_inflight"
    finally:
        release.set()
        thread.join(timeout=5)
    assert returned.wait(3)
    assert not thread.is_alive()
    assert ledger.read_bytes() == frozen
