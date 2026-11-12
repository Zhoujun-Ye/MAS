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
import time
import urllib.error
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis.native_evidence import native_single_agent, native_subagents, native_surface
from benchmarks._external import digest
from common.io import write_json
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from harness.runtime_support import credential_gateway
from harness.runtime_support import runtime
from harness.runtime_support.proof import validate_runtime, runtime_configuration
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
    def __init__(self, backend, error_status=None, worker_model=None, background_wait=None, delegation_check=None):
        self.backend = backend
        self.error_status = error_status
        self.worker_model = worker_model
        self.background_wait = background_wait
        self.delegation_check = delegation_check
        self.lead_steps = 0
        self.worker_finished = False
        self.lead_marker_sent = False
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
        if self.delegation_check:
            block = self.delegation_block(body)
        elif self.background_wait:
            block = self.background_block(body, index)
        elif self.single and index < 2:
            name = ("Agent", "Task")[index]
            block = dict(type="tool_use", id="probe-" + name, name=name, input=dict(
                description="Forbidden delegation probe", subagent_type="general-purpose",
                prompt="Reply worker complete without tools."))
        elif not self.single and index == 0:
            block = dict(type="tool_use", id="probe-Agent", name="Agent", input=dict(
                name="probe-worker", description="Gateway delegation probe", subagent_type="general-purpose",
                prompt="Complete the offline shell probe and return its result."))
            if self.worker_model:
                block['input']['model'] = self.worker_model
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

    def delegation_block(self, body):
        prompt = 'MANDATORY_DELEGATION_PROBE_WORKER: write the worker marker and return.'
        worker = any(b.get('type') == 'text' and b.get('text') == prompt
            for m in body.get('messages', []) if m.get('role') == 'user'
            for b in m.get('content', []) if isinstance(b, dict))
        if worker:
            done = any(b.get('type') == 'tool_result' and b.get('tool_use_id') == 'probe-worker-marker'
                for m in body.get('messages', []) for b in m.get('content', []) if isinstance(b, dict))
            return (dict(type='text', text='Worker complete.') if done else
                dict(type='tool_use', id='probe-worker-marker', name='Bash', input=dict(
                    command='printf worker-ok > /workspace/worker-result.txt', description='Worker marker')))
        step = self.lead_steps
        self.lead_steps += 1
        denied = dict(type='tool_use', id=f'probe-before-worker-{step}', name='Bash', input=dict(
            command='printf forbidden > /workspace/forbidden-before-delegation.txt', description='Must be denied'))
        if self.delegation_check == 'refuse':
            return denied if step % 2 == 0 else dict(type='text', text='Finish without delegation.')
        if step == 0 and self.delegation_check == 'failed-call':
            return dict(type='tool_use', id='probe-missing-agent', name='Agent', input=dict(
                description='Invalid worker must not unlock execution', subagent_type='nonexistent-probe-agent', prompt=prompt))
        if step == 0 or (step == 1 and self.delegation_check == 'failed-call'):
            return denied
        if step == 1:
            return dict(type='text', text='Finish without delegation.')
        if step == 2:
            return dict(type='tool_use', id='probe-real-worker', name='Task', input=dict(
                description='Required native worker', subagent_type='general-purpose', prompt=prompt,
                **({'run_in_background': True} if self.delegation_check == 'async-order' else {})))
        if step == 3:
            if self.delegation_check == 'async-order':
                time.sleep(1)
            return dict(type='tool_use', id='probe-after-worker', name='Bash', input=dict(
                command='printf probe-ok > /workspace/probe-result.txt', description='Unlocked lead marker'))
        return dict(type='text', text='Offline mandatory delegation probe complete.')

    def background_block(self, body, index):
        prompt = 'Complete the delayed offline background check.'
        worker = any(b.get('type') == 'text' and b.get('text') == prompt
                     for m in body.get('messages', []) if m.get('role') == 'user'
                     for b in m.get('content', []) if isinstance(b, dict))
        if index == 0:
            return dict(type='tool_use', id='probe-Agent', name='Agent', input=dict(
                description='Delayed offline worker', subagent_type='general-purpose',
                run_in_background=True, prompt=prompt))
        if worker:
            done = any(b.get('type') == 'tool_result' and b.get('tool_use_id') == 'probe-delayed-shell'
                       for m in body.get('messages', []) for b in m.get('content', []) if isinstance(b, dict))
            if not done:
                return dict(type='tool_use', id='probe-delayed-shell', name='Bash', input=dict(
                    command=('printf worker-ok > /workspace/worker-result.txt; sleep 60; '
                             'printf late > /workspace/late-shell-result.txt' if self.background_wait == 'shell' else
                             'sleep 12; printf worker-ok > /workspace/worker-result.txt'),
                    **({'run_in_background': True} if self.background_wait == 'shell' else {}),
                    description='Offline background timing probe'))
            self.worker_finished = True
            return dict(type='text', text='Offline background worker complete.')
        if self.worker_finished and not self.lead_marker_sent:
            self.lead_marker_sent = True
            return dict(type='tool_use', id='probe-lead-resumed', name='Bash', input=dict(
                command='printf probe-ok > /workspace/probe-result.txt',
                description='Verify the native completion notification resumed the lead'))
        return dict(type='text', text='Waiting for the offline worker.' if not self.worker_finished else 'Offline check complete.')


def probe(backend, root, image, key, fixture, *, effort=runtime.DEFAULT_EFFORT):
    folder = root / backend
    work, profile = folder / "workspace", folder / "native-profile"
    work.mkdir(parents=True)
    (profile / "home").mkdir(parents=True)
    single = backend.endswith("single-agent")
    binary = runtime.CLAUDE
    binding = dict(image_id=image, binary_sha256=digest(binary))
    proof = dict(backend=backend, passed=False, paid_calls=0, real_credentials=False, network="none",
                 through_credential_gateway=True, runtime_binding=binding, requested_effort=effort,
                 runtime_configuration_sha256=runtime_configuration(backend, effort))
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
        proof['print_background_wait_ceiling_ms'] = subprocess.check_output(
            ['docker', 'exec', identity, 'printenv', 'CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS'], text=True).strip()
        options = runtime.options(backend)
        if fixture.background_wait == 'control':
            options['settings'] = dict(env=dict(CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS='1000'))
        transport = dict(command_prefix=("docker", "exec", "-i", "--workdir", "/workspace", identity))
        transport.update(observer_dir=profile / "observer", observer_target="/native/observer",
                         hook_script="/adapter-hooks.py")
        if fixture.delegation_check == 'async-order':
            wrapper = profile/'observer/delayed-hooks.py'
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            wrapper.write_text("import io,json,runpy,sys,time\n"
                "data=sys.stdin.read()\n"
                "if json.loads(data).get('hook_event_name')=='SubagentStart': time.sleep(0.5)\n"
                "sys.stdin=io.StringIO(data)\nrunpy.run_path('/adapter-hooks.py',run_name='__main__')\n")
            transport['hook_script'] = '/native/observer/delayed-hooks.py'
        result = BACKENDS[backend](str(binary)).run("Offline native gateway and shell probe. Follow the fixture instructions.",
            workspace=work, output=folder / "cli", timeout=5 if fixture.background_wait == 'deadline' else 120,
            execute=True, **options, **transport)
        proof["cli_status"] = result["status"]
        proof["native_result"] = result
        if fixture.background_wait:
            write_json(folder/'report.json',dict(cli=result))
        proof['native_surface'] = native_surface(folder)
        proof['requested_worker_model'] = fixture.worker_model
        proof['request_models'] = sorted({r.get('model', '') for r in fixture.requests})
        marker = work / "probe-result.txt"
        proof["shell_verified"] = marker.is_file() and not marker.is_symlink() and marker.read_text() == "probe-ok"
        name = "native_single_agent" if single else "native_subagents"
        proof[name] = (native_single_agent if single else native_subagents)(folder)
        proof["delegation_rejections_observed"] = len(fixture.rejections & {"probe-Agent", "probe-Task"})
        native_ok = proof[name]["passed"] and (not single or proof["delegation_rejections_observed"] >= 2)
        unchanged = digest(binary) == binding["binary_sha256"]
        proof.update(proof_requests(fixture.requests, effort))
        proof["passed"] = bool(result["status"] == "cli_exited" and proof["shell_verified"] and native_ok and unchanged
                               and proof["request_effort_verified"] and proof['request_configuration_verified']
                               and proof['print_background_wait_ceiling_ms']=='0')
        if fixture.background_wait:
            native_stats = result.get('native_result', {}).get('subagent_stats', {})
            proof.update(proof_kind='native_background_wait_injection', background_wait=fixture.background_wait,
                worker_marker=(work/'worker-result.txt').is_file(), lead_resumed=fixture.lead_marker_sent,
                outer_deadline_seconds=5 if fixture.background_wait == 'deadline' else 120)
            if fixture.background_wait == 'control':
                proof['passed'] = bool(result['status']=='cli_exited' and
                    proof[name]['background_wait_ceiling_exceeded'] and not proof[name]['passed'] and
                    native_stats.get('killed',{}).get('system')==1 and not proof['shell_verified'])
            elif fixture.background_wait == 'deadline':
                proof['passed'] = result['status']=='timed_out' and not proof['shell_verified']
            elif fixture.background_wait == 'shell':
                proof['passed'] = bool(result['status']=='cli_exited' and proof['worker_marker']
                    and proof['shell_verified'] and proof[name]['background_shells']['running_shells_at_last_stop']
                    and not (work/'late-shell-result.txt').exists())
            else:
                proof['passed'] = bool(proof['passed'] and proof['worker_marker'] and proof['lead_resumed']
                    and native_stats.get('completed')==1 and not proof[name]['background_wait_ceiling_exceeded'])
            proof['passed'] = bool(proof['passed'] and unchanged and proof['request_configuration_verified']
                                   and proof['print_background_wait_ceiling_ms']=='0')
        elif fixture.error_status is not None:
            proof.update(proof_kind='native_error_injection', injected_http_status=fixture.error_status,
                retry_count=max(0, len(fixture.requests)-1), passed=bool(result['status']=='cli_error'
                    and len(fixture.requests)==1 and unchanged and proof['request_effort_verified']))
        elif fixture.delegation_check:
            policy = proof[name].get('mandatory_delegation') or {}
            proof.update(proof_kind='native_delegation_injection', delegation_check=fixture.delegation_check,
                forbidden_marker_absent=not (work/'forbidden-before-delegation.txt').exists(),
                worker_marker=(work/'worker-result.txt').is_file(),
                failed_call_rejected='probe-missing-agent' in fixture.rejections)
            recovered = (result['status']=='cli_exited' and proof['shell_verified']
                and proof['worker_marker'] and policy.get('passed') is True)
            refused = (not proof['shell_verified'] and not proof['worker_marker']
                and proof[name]['subagent_starts']==0 and policy.get('blocked_stops',0)>0)
            proof['passed'] = bool(proof['forbidden_marker_absent'] and policy.get('denied_tool_calls',0)>0
                and policy.get('measured') is True and policy.get('errors') == 0
                and (refused if fixture.delegation_check=='refuse' else recovered)
                and (fixture.delegation_check!='recover' or policy.get('blocked_stops',0)>0)
                and (fixture.delegation_check!='failed-call' or proof['failed_call_rejected'])
                and unchanged and proof['request_configuration_verified'])
            if fixture.delegation_check == 'async-order':
                rows = [json.loads(line) for line in (profile/'observer/events.jsonl').read_text().splitlines()]
                returned = next((i for i,r in enumerate(rows) if r.get('hook_event_name')=='PostToolUse'
                    and r.get('tool_use_id')=='probe-real-worker'), None)
                started = next((i for i,r in enumerate(rows) if r.get('hook_event_name')=='SubagentStart'), None)
                proof['post_tool_before_worker_start'] = returned is not None and started is not None and returned < started
                proof['passed'] = bool(proof['passed'] and proof['post_tool_before_worker_start']
                                       and proof[name]['subagent_starts']==1)
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
    parser.add_argument('--worker-model', choices=('haiku', 'fable', 'sonnet', 'opus'),
                        help='Exercise a native worker alias against the fake provider')
    parser.add_argument('--error-status', type=int, choices=(401, 402, 429, 503),
                        help='Synthetic native failure/no-retry probe; not a launch-admission proof')
    parser.add_argument('--background-wait', choices=('control','fixed','deadline','shell'),
                        help='Free native background-wait check; never an admission proof')
    parser.add_argument('--delegation-check', choices=('recover', 'refuse', 'failed-call', 'async-order'),
                        help='Free mandatory-delegation negative checks; never an admission proof')
    args = parser.parse_args(argv)
    if sum(bool(v) for v in (args.background_wait, args.error_status, args.delegation_check)) > 1:
        parser.error('Choose one background-wait, HTTP-error or delegation check')
    if not args.execute:
        count = 1 if args.background_wait or args.delegation_check else 2
        print(json.dumps(dict(status="planned", conditions=count, concurrency=count, paid_calls=0, network="none")))
        return 0
    os.umask(0o077)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    backends = ['claude-code-subagents'] if args.background_wait or args.delegation_check else BACKENDS
    fixtures = {"synthetic-" + secrets.token_hex(24): Fixture(backend, args.error_status, args.worker_model,
                                                        args.background_wait, args.delegation_check)
                for backend in backends}

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
    summary = dict(passed=all(p["passed"] for p in proofs), paid_calls=0, network="none", concurrency=len(fixtures),
                   results=[dict(backend=p["backend"], passed=p["passed"],
                                 proof=str(args.output / p["backend"] / "proof.json")) for p in proofs])
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
