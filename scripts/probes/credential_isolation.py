"""Real Docker transport canary with synthetic credentials and no external network."""

import argparse
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
from unittest.mock import patch

from scripts.common import credential_gateway, runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status="planned", paid_calls=0, containers=2)))
        return
    os.umask(0o077)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    key = "synthetic-" + secrets.token_hex(24)
    calls = []

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "text/event-stream"}

    def upstream(request):
        assert request.full_url.startswith("https://api.deepseek.com/")
        assert request.get_header("Authorization") == "Bearer " + key
        calls.append(request.full_url.split(".com", 1)[1])
        return Response(b'data: {"ok":true}\n\n')

    code = '''import json, os, pathlib, socket, urllib.request, urllib.error
snapshot = json.dumps(dict(os.environ)) + pathlib.Path('/proc/1/environ').read_bytes().decode()
token = os.environ['ANTHROPIC_AUTH_TOKEN']
results = []
for path in ['/responses', '/anthropic/v1/messages', '/v1/tools/search']:
    req = urllib.request.Request('http://127.0.0.1:8765' + path,
        data=b'{"model":"deepseek-flash"}', headers={'Authorization':'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=10) as response:
        results.append(response.read().decode())
pathlib.Path('/native/web-usage.jsonl').write_text('')
try:
    urllib.request.urlopen(req, timeout=10)
    quota_status = 200
except urllib.error.HTTPError as error:
    quota_status = error.code
with socket.socket() as direct:
    direct.settimeout(2)
    external_blocked = direct.connect_ex(('1.1.1.1', 443)) != 0
print(json.dumps({'snapshot':snapshot, 'results':results,
    'quota_status':quota_status, 'external_blocked':external_blocked,
    'host_ledger_visible':pathlib.Path('/gateway-requests.jsonl').exists(),
    'host_env_visible':pathlib.Path('/home/zhoujunye/MAS-information/.env').exists()}))
'''
    proofs = []
    with patch.object(credential_gateway, "open_upstream", upstream):
        for backend in ("claude-code-single-agent", "codex-single-agent"):
            folder = args.output / backend
            work, profile = folder / "workspace", folder / "native-profile"
            work.mkdir(parents=True)
            (profile / "home").mkdir(parents=True)
            socket_path = folder / "gateway.sock"
            with credential_gateway.CredentialGateway(key, unix_path=socket_path, web_limit=1) as gateway:
                identity = runtime.container(work, profile, work, args.image, backend=backend,
                    gateway=gateway, dataset_mounts=[])
                try:
                    raw = subprocess.check_output(["docker", "exec", identity, "python3", "-c", code], text=True, timeout=30)
                    assert key not in raw
                    result = json.loads(raw)
                    assert not result["host_env_visible"]
                    assert not result["host_ledger_visible"]
                    assert result["external_blocked"] and result["quota_status"] == 429
                    assert result["results"] == ['data: {"ok":true}\n\n'] * 3
                    inspection = subprocess.check_output(["docker", "inspect", identity], text=True)
                    assert key not in inspection
                    assert json.loads(inspection)[0]["HostConfig"]["NetworkMode"] == "none"
                finally:
                    runtime.stop_container(identity)
                    subprocess.run(["docker", "rm", identity], check=True, capture_output=True)
            assert not socket_path.exists()
            proofs.append(dict(backend=backend, passed=True, host_key_absent=True,
                               host_env_inaccessible=True, gateway_routes=3, cleanup=True,
                               external_network_blocked=True, quota_survives_local_ledger_reset=True,
                               host_ledger=gateway.summary()))
    proof = dict(passed=True, paid_calls=0, network="none", provider_calls_mocked=len(calls), conditions=proofs)
    runtime.write_json(args.output / "proof.json", proof)
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
