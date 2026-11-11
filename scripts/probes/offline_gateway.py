"""Exercise pinned native CLIs through the real credential bridge, without paid APIs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import urllib.error
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis.native_evidence import native_single_agent, native_subagents
from benchmarks._external import digest
from common.io import write_json
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from harness.runtime_support import credential_gateway
from harness.runtime_support import runtime
from harness.runtime_support.proof import validate_runtime
from harness.runtime_support.inference import proof_requests


BACKENDS = {"claude-code-single-agent": ClaudeCodeSingleAgentCLI, "claude-code-subagents": ClaudeCodeSubagentsCLI}


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, content_type):
        super().__init__(body)
        self.headers = {"Content-Type": content_type}


def sse(frames):
    return Response("".join("event: " + f["type"] + "\ndata: " + json.dumps(f) + "\n\n"
                            for f in frames).encode(), "text/event-stream")


class Fixture:
    def __init__(self, backend, error_status=None):
        self.backend = backend
        self.error_status = error_status
        self.single = backend.endswith("single-agent")
        self.requests = []
        self.rejections = set()
        self.lock = threading.Lock()

    def respond(self, request):
        body = json.loads(request.data)
        with self.lock:
            if urlsplit(request.full_url).path.endswith("count_tokens"):
                return Response(b'{"input_tokens":100}', "application/json")
            if len(self.requests) >= 32:
                raise ValueError("Offline fixture request ceiling exceeded")
            self.requests.append(body)
            if self.error_status is not None:
                kind = {401: 'authentication_error', 402: 'billing_error', 429: 'rate_limit_error',
                        503: 'api_error'}[self.error_status]
                error = dict(type='error', error=dict(type=kind, message='Synthetic offline failure; do not retry'))
                raise urllib.error.HTTPError(request.full_url, self.error_status, 'Synthetic',
                    {'Content-Type': 'application/json', 'Retry-After': '2'}, io.BytesIO(json.dumps(error).encode()))
            return self.claude(body)

    def claude(self, body):
        for message in body.get("messages", []):
            for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
                if block.get("type") == "tool_result" and block.get("is_error"):
                    self.rejections.add(block.get("tool_use_id"))
        index = len(self.requests) - 1
        if self.single and index < 2:
            name = ("Agent", "Task")[index]
            block = dict(type="tool_use", id="probe-" + name, name=name, input=dict(
                description="Forbidden delegation probe", subagent_type="general-purpose",
                prompt="Reply worker complete without tools."))
        elif not self.single and index == 0:
            block = dict(type="tool_use", id="probe-Agent", name="Agent", input=dict(
                name="probe-worker", description="Gateway delegation probe", subagent_type="general-purpose",
                prompt="Complete the offline shell probe and return its result."))
        elif index == (2 if self.single else 1):
            block = dict(type="tool_use", id="probe-shell", name="Bash", input=dict(
                command="printf probe-ok > /workspace/probe-result.txt", description="Write offline probe marker"))
        else:
            block = dict(type="text", text="Offline gateway probe complete.")
        stop = "tool_use" if block["type"] == "tool_use" else "end_turn"
        response = dict(id="probe-" + str(index), type="message", role="assistant", model=body["model"],
                        content=[block], stop_reason=stop, stop_sequence=None,
                        usage=dict(input_tokens=100, output_tokens=10, cache_creation_input_tokens=0,
                                   cache_read_input_tokens=0))
        if not body.get("stream"):
            return Response(json.dumps(response).encode(), "application/json")
        start = dict(block, **({"input": {}} if block["type"] == "tool_use" else {"text": ""}))
        delta = (dict(type="input_json_delta", partial_json=json.dumps(block["input"]))
                 if block["type"] == "tool_use" else dict(type="text_delta", text=block["text"]))
        return sse([dict(type="message_start", message=dict(response, content=[], stop_reason=None)),
                    dict(type="content_block_start", index=0, content_block=start),
                    dict(type="content_block_delta", index=0, delta=delta),
                    dict(type="content_block_stop", index=0),
                    dict(type="message_delta", delta=dict(stop_reason=stop, stop_sequence=None), usage=dict(output_tokens=10)),
                    dict(type="message_stop")])


def probe(backend, root, image, key, fixture, *, effort=runtime.DEFAULT_EFFORT):
    folder = root / backend
    work, profile = folder / "workspace", folder / "native-profile"
    work.mkdir(parents=True)
    (profile / "home").mkdir(parents=True)
    single = backend.endswith("single-agent")
    binary = runtime.CLAUDE
    binding = dict(image_id=image, binary_sha256=digest(binary))
    proof = dict(backend=backend, passed=False, paid_calls=0, real_credentials=False, network="none",
                 through_credential_gateway=True, runtime_binding=binding, requested_effort=effort)
    identity = None
    gateway = None
    try:
        gateway = credential_gateway.CredentialGateway(key, unix_path=folder / "gateway.sock",
                                                      inference_policy=runtime.inference_configuration(effort))
        gateway.__enter__()
        identity = runtime.container(work, profile, work, image, network="none", backend=backend,
                                     dataset_mounts=[], gateway=gateway, effort=effort)
        inspect = subprocess.check_output(["docker", "inspect", identity], text=True)
        assert key not in inspect
        environment = subprocess.check_output(["docker", "exec", identity, "python3", "-c",
            "import os,pathlib; print(dict(os.environ)); print(pathlib.Path('/proc/1/environ').read_bytes())"], text=True)
        assert key not in environment
        proof["host_key_absent"] = True
        options = runtime.options(backend)
        transport = dict(command_prefix=("docker", "exec", "-i", "--workdir", "/workspace", identity))
        transport.update(observer_dir=profile / "observer", observer_target="/native/observer",
                         hook_script="/adapter-hooks.py")
        result = BACKENDS[backend](str(binary)).run("Offline native gateway and shell probe. Follow the fixture instructions.",
            workspace=work, output=folder / "cli", timeout=120, execute=True, **options, **transport)
        proof["cli_status"] = result["status"]
        proof["native_result"] = result
        marker = work / "probe-result.txt"
        proof["shell_verified"] = marker.is_file() and not marker.is_symlink() and marker.read_text() == "probe-ok"
        name = "native_single_agent" if single else "native_subagents"
        proof[name] = (native_single_agent if single else native_subagents)(folder)
        proof["delegation_rejections_observed"] = len(fixture.rejections & {"probe-Agent", "probe-Task"})
        native_ok = proof[name]["passed"] and (not single or proof["delegation_rejections_observed"] >= 2)
        unchanged = digest(binary) == binding["binary_sha256"]
        proof.update(proof_requests(fixture.requests, effort))
        proof["passed"] = bool(result["status"] == "cli_exited" and proof["shell_verified"] and native_ok and unchanged
                               and proof["request_effort_verified"] and proof['request_configuration_verified'])
        if fixture.error_status is not None:
            proof.update(proof_kind='native_error_injection', injected_http_status=fixture.error_status,
                retry_count=max(0, len(fixture.requests)-1), passed=bool(result['status']=='cli_error'
                    and len(fixture.requests)==1 and unchanged and proof['request_effort_verified']))
        else:
            validate_runtime(proof, backend, **binding)
    except Exception as error:
        proof.update(passed=False, error_type=type(error).__name__)
        if getattr(error, "container_id", None):
            proof["startup_cleanup"] = error.cleanup_details
    finally:
        if identity is not None:
            try:
                try:
                    runtime.stop_container(identity)
                finally:
                    subprocess.run(["docker", "rm", "-f", identity], check=True, capture_output=True)
                proof["container_removed"] = True
            except Exception as error:
                proof.update(passed=False, cleanup_error_type=type(error).__name__)
        if gateway is not None:
            gateway.__exit__(None, None, None)
            proof["socket_removed"] = not gateway.unix_path.exists()
        proof["fake_model_requests"] = len(fixture.requests)
        write_json(folder / "fake-provider-requests.json", fixture.requests)
        write_json(folder / "proof.json", proof)
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--effort", choices=runtime.EFFORTS, default=runtime.DEFAULT_EFFORT)
    parser.add_argument('--error-status', type=int, choices=(401, 402, 429, 503),
                        help='Synthetic native failure/no-retry probe; not a launch-admission proof')
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status="planned", conditions=2, concurrency=2, paid_calls=0, network="none")))
        return 0
    os.umask(0o077)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    fixtures = {"synthetic-" + secrets.token_hex(24): Fixture(backend, args.error_status) for backend in BACKENDS}

    def fake_upstream(request):
        key = request.get_header("Authorization", "").removeprefix("Bearer ")
        if key not in fixtures or not request.full_url.startswith("https://api.deepseek.com/"):
            raise ValueError("Offline probe rejected unknown credential or upstream")
        return fixtures[key].respond(request)

    with patch.object(credential_gateway, "open_upstream", fake_upstream):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(probe, fixture.backend, args.output, image, key, fixture, effort=args.effort)
                       for key, fixture in fixtures.items()]
            proofs = [future.result() for future in futures]
    summary = dict(passed=all(p["passed"] for p in proofs), paid_calls=0, network="none", concurrency=2,
                   results=[dict(backend=p["backend"], passed=p["passed"],
                                 proof=str(args.output / p["backend"] / "proof.json")) for p in proofs])
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
