"""Exercise pinned native CLIs through the real credential bridge, without paid APIs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from unittest.mock import patch
import uuid
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis.codex_evidence import inspect as codex_evidence
from analysis.native_evidence import native_single_agent, native_subagents
from benchmarks._io import write_json
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI, CodexSingleAgentCLI, CodexSubagentsCLI
from scripts.common import credential_gateway, runtime
from scripts.common.proof import validate_runtime
from scripts.server.offline_codex import tool_names


BACKENDS = {"claude-code-single-agent": ClaudeCodeSingleAgentCLI,
            "claude-code-subagents": ClaudeCodeSubagentsCLI,
            "codex-single-agent": CodexSingleAgentCLI, "codex-subagents": CodexSubagentsCLI}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, content_type):
        super().__init__(body)
        self.headers = {"Content-Type": content_type}


def sse(frames):
    return Response("".join("event: " + f["type"] + "\ndata: " + json.dumps(f) + "\n\n"
                            for f in frames).encode(), "text/event-stream")


class Fixture:
    def __init__(self, backend):
        self.backend = backend
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
            if self.backend.startswith("codex-"):
                return self.codex(body)
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

    def codex(self, body):
        inputs = body.get("input", [])
        child = any("Message Type: NEW_TASK" in json.dumps(x) for x in inputs
                    if isinstance(x, dict) and x.get("type") != "function_call")
        outputs = [x for x in inputs if isinstance(x, dict) and x.get("type") == "function_call_output"]
        if not self.single and not child and not outputs:
            item = dict(type="function_call", id="fc_spawn", call_id="call_spawn", name="spawn_agent",
                        namespace="collaboration", arguments=json.dumps(dict(message="PROBE_CHILD: reply OK",
                        task_name="probe_child", fork_turns="none")))
        elif not self.single and not child and len(outputs) == 1:
            item = dict(type="function_call", id="fc_wait", call_id="call_wait", name="wait_agent",
                        namespace="collaboration", arguments=json.dumps(dict(timeout_ms=10000)))
        elif not child and len(outputs) == (0 if self.single else 2):
            item = dict(type="function_call", id="fc_shell", call_id="call_shell", name="exec_command",
                        arguments=json.dumps(dict(cmd="printf probe-ok > /workspace/probe-result.txt")))
        else:
            item = dict(type="message", id="msg_" + uuid.uuid4().hex, role="assistant", status="completed",
                        content=[dict(type="output_text", text="Offline gateway probe complete.", annotations=[])])
        response = dict(id="resp_" + uuid.uuid4().hex, object="response", status="completed", output=[item],
                        usage=dict(input_tokens=100, output_tokens=10, total_tokens=110))
        return sse([dict(type="response.created", response={**response, "status": "in_progress", "output": []}),
                    dict(type="response.output_item.added", output_index=0, item=item),
                    dict(type="response.output_item.done", output_index=0, item=item),
                    dict(type="response.completed", response=response)])


def probe(backend, root, image, key, fixture):
    folder = root / backend
    work, profile = folder / "workspace", folder / "native-profile"
    work.mkdir(parents=True)
    (profile / "home").mkdir(parents=True)
    codex, single = backend.startswith("codex-"), backend.endswith("single-agent")
    binary = runtime.CODEX if codex else runtime.CLAUDE
    binding = dict(image_id=image, binary_sha256=digest(binary))
    catalog = runtime.CODEX_CATALOG.with_name("deepseek-single-models.json") if single else runtime.CODEX_CATALOG
    if codex:
        binding["catalog_sha256"] = digest(catalog)
    proof = dict(backend=backend, passed=False, paid_calls=0, real_credentials=False, network="none",
                 through_credential_gateway=True, runtime_binding=binding)
    identity = None
    gateway = None
    try:
        gateway = credential_gateway.CredentialGateway(key, unix_path=folder / "gateway.sock")
        gateway.__enter__()
        identity = runtime.container(work, profile, work, image, network="none", backend=backend,
                                     dataset_mounts=[], gateway=gateway)
        inspect = subprocess.check_output(["docker", "inspect", identity], text=True)
        assert key not in inspect
        environment = subprocess.check_output(["docker", "exec", identity, "python3", "-c",
            "import os,pathlib; print(dict(os.environ)); print(pathlib.Path('/proc/1/environ').read_bytes())"], text=True)
        assert key not in environment
        proof["host_key_absent"] = True
        options = runtime.options(backend)
        transport = dict(command_prefix=("docker", "exec", "-i", "--workdir", "/workspace", identity))
        if codex:
            options.update(base_url=gateway.url, docker_isolated=True)
            transport.update(profile=profile / "codex", profile_target="/native/codex")
        else:
            transport.update(observer_dir=profile / "observer", observer_target="/native/observer",
                             hook_script="/adapter-hooks.py")
        result = BACKENDS[backend](str(binary)).run("Offline native gateway and shell probe. Follow the fixture instructions.",
            workspace=work, output=folder / "cli", timeout=120, execute=True, **options, **transport)
        proof["cli_status"] = result["status"]
        proof["native_result"] = result
        marker = work / "probe-result.txt"
        proof["shell_verified"] = marker.is_file() and not marker.is_symlink() and marker.read_text() == "probe-ok"
        if codex:
            names = tool_names(fixture.requests[0].get("tools", [])) if fixture.requests else set()
            spawn = any(n.endswith("spawn_agent") for n in names)
            proof["tool_exposure_verified"] = bool(fixture.requests) and (not spawn if single else spawn)
            proof["native_codex"] = codex_evidence(profile / "codex", single=single)
            native_ok = proof["native_codex"]["passed"] and proof["tool_exposure_verified"]
        else:
            name = "native_single_agent" if single else "native_subagents"
            proof[name] = (native_single_agent if single else native_subagents)(folder)
            proof["delegation_rejections_observed"] = len(fixture.rejections & {"probe-Agent", "probe-Task"})
            native_ok = proof[name]["passed"] and (not single or proof["delegation_rejections_observed"] >= 2)
        unchanged = digest(binary) == binding["binary_sha256"] and (not codex or digest(catalog) == binding["catalog_sha256"])
        proof["passed"] = bool(result["status"] == "cli_exited" and proof["shell_verified"] and native_ok and unchanged)
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
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status="planned", conditions=4, concurrency=4, paid_calls=0, network="none")))
        return 0
    os.umask(0o077)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    fixtures = {"synthetic-" + secrets.token_hex(24): Fixture(backend) for backend in BACKENDS}

    def fake_upstream(request):
        key = request.get_header("Authorization", "").removeprefix("Bearer ")
        if key not in fixtures or not request.full_url.startswith("https://api.deepseek.com/"):
            raise ValueError("Offline probe rejected unknown credential or upstream")
        return fixtures[key].respond(request)

    with patch.object(credential_gateway, "open_upstream", fake_upstream):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(probe, fixture.backend, args.output, image, key, fixture)
                       for key, fixture in fixtures.items()]
            proofs = [future.result() for future in futures]
    summary = dict(passed=all(p["passed"] for p in proofs), paid_calls=0, network="none", concurrency=4,
                   results=[dict(backend=p["backend"], passed=p["passed"],
                                 proof=str(args.output / p["backend"] / "proof.json")) for p in proofs])
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
