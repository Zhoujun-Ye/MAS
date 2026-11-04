import pytest
import json
import urllib.request
import urllib.error
import socket
import stat
from scripts.common.credential_gateway import CredentialGateway
from scripts.common import credential_gateway

from scripts.common import runtime

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch):
    def guarded(original):
        def connect(sock, address):
            if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                raise AssertionError("Credential tests permit loopback only")
            return original(sock, address)
        return connect
    monkeypatch.setattr(socket.socket, "connect", guarded(_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(_connect_ex))


def test_live_credentials_rejected_before_docker(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Docker must not run with real credentials")
    monkeypatch.setattr(runtime.subprocess, "check_output", forbidden)
    with pytest.raises(RuntimeError, match="credential isolation"):
        runtime.container(tmp_path, tmp_path, tmp_path, "image", key="test-secret-not-real")
    with pytest.raises(RuntimeError, match="Forwarding host credentials"):
        runtime.container(tmp_path, tmp_path, tmp_path, "image", forwarded_env=("TAVILY_API_KEY",))
    with pytest.raises(ValueError, match="override container environment"):
        runtime.container(tmp_path, tmp_path, tmp_path, "image", environment_overrides={"DEEPSEEK_API_KEY": "secret"})


def test_gateway_denies_unscoped_requests():
    with CredentialGateway("synthetic-secret", bind="127.0.0.1", web_limit=0) as gateway:
        for path, token, expected in [("/responses", "wrong", 403), ("/user/balance", gateway.token, 404),
                                       ("/v1/tools/search", gateway.token, 429)]:
            request = urllib.request.Request(gateway.url + path, data=b'{}',
                headers={"Authorization": "Bearer " + token})
            with pytest.raises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=2)
            assert caught.value.code == expected
            assert b"synthetic-secret" not in caught.value.read()


def test_gateway_injects_key_only_upstream(monkeypatch):
    original = urllib.request.urlopen
    calls = []
    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self):
            self.parts = iter([b'{"text":"synthetic-', b'secret"}', b''])
        def read1(self, size):
            return next(self.parts)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    def open_request(request, **kwargs):
        if request.full_url.startswith("https://api.deepseek.com/"):
            calls.append(request)
            return Response()
        return original(request, **kwargs)
    monkeypatch.setattr(credential_gateway, "open_upstream", open_request)
    with CredentialGateway("synthetic-secret", bind="127.0.0.1") as gateway:
        request = urllib.request.Request(gateway.url + "/responses",
            data=json.dumps({"model": "deepseek-flash", "input": "hi"}).encode(),
            headers={"Authorization": "Bearer " + gateway.token})
        with original(request, timeout=2) as response:
            body = response.read()
        assert b"synthetic-secret" not in body
        assert b"[REDACTED]" in body
        assert calls[0].get_header("Authorization") == "Bearer synthetic-secret"
        assert gateway.token != "synthetic-secret"


@pytest.mark.parametrize("path,payload", [
    ("/responses?redirect=https://example.com", {"model": "deepseek-flash"}),
    ("/responses", {"model": "unauthorized-model"}),
    ("/responses", []),
])
def test_invalid_requests_never_reach_provider(monkeypatch, path, payload):
    monkeypatch.setattr(credential_gateway, "open_upstream", lambda *a: pytest.fail("Unexpected provider call"))
    with CredentialGateway("synthetic-secret") as gateway:
        request = urllib.request.Request(gateway.url + path, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + gateway.token})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        assert caught.value.code in (400, 404)
        caught.value.close()


def test_provider_errors_are_generic_and_not_retried(monkeypatch):
    import io
    calls = []
    def fail(request):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 401, "synthetic-secret", {}, io.BytesIO(b"synthetic-secret"))
    monkeypatch.setattr(credential_gateway, "open_upstream", fail)
    with CredentialGateway("synthetic-secret") as gateway:
        request = urllib.request.Request(gateway.url + "/responses", data=b'{"model":"deepseek-flash"}',
            headers={"Authorization": "Bearer " + gateway.token})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        assert caught.value.code == 401
        assert b"synthetic-secret" not in caught.value.read()
        assert len(calls) == 1


def test_unix_socket_private_and_removed(tmp_path):
    path = tmp_path / "gateway.sock"
    with CredentialGateway("synthetic-secret", unix_path=path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not path.exists()


@pytest.mark.parametrize("key", ["", "invalid credential", None])
def test_invalid_credentials_fail_closed(key):
    with pytest.raises(ValueError, match="credential format"):
        CredentialGateway(key)


def test_public_gateway_bind_rejected():
    with pytest.raises(ValueError, match="loopback"):
        CredentialGateway("synthetic-secret", bind="0.0.0.0")


def test_long_output_path_uses_private_short_socket(tmp_path):
    path = tmp_path / ("x" * 120) / "gateway.sock"
    with CredentialGateway("synthetic-secret", unix_path=path) as gateway:
        actual = gateway.unix_path
        assert actual != path
        assert stat.S_IMODE(actual.parent.stat().st_mode) == 0o700
        assert actual.exists()
    assert not actual.parent.exists()
