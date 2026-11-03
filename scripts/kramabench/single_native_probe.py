"""No-network native dcode check against a loopback fake provider, no paid calls."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dcode", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if "count_tokens" in self.path:
                response = dict(input_tokens=100)
            else:
                calls.append(body)
                if len(calls) == 1:
                    content = [dict(type="tool_use", id="guard-attempt", name="task", input=dict(
                        description="Say delegated; this tool call must be denied", subagent_type="general-purpose"))]
                    stop = "tool_use"
                else:
                    content, stop = [dict(type="text", text="native single guard probe complete")], "end_turn"
                response = dict(id="probe-" + str(len(calls)), type="message", role="assistant",
                    model="deepseek-flash", content=content, stop_reason=stop, stop_sequence=None,
                    usage=dict(input_tokens=100, output_tokens=10))
            self.send_response(200)
            streaming = body.get("stream") and "content" in response
            self.send_header("Content-Type", "text/event-stream" if streaming else "application/json")
            self.end_headers()
            if streaming:
                block = response["content"][0]
                start = dict(block, **({"input": {}} if block["type"] == "tool_use" else {"text": ""}))
                delta = (dict(type="input_json_delta", partial_json=json.dumps(block["input"]))
                         if block["type"] == "tool_use" else dict(type="text_delta", text=block["text"]))
                frames = [dict(type="message_start", message=dict(response, content=[], stop_reason=None)),
                          dict(type="content_block_start", index=0, content_block=start),
                          dict(type="content_block_delta", index=0, delta=delta),
                          dict(type="content_block_stop", index=0),
                          dict(type="message_delta", delta=dict(stop_reason=response["stop_reason"], stop_sequence=None),
                               usage=dict(output_tokens=10)), dict(type="message_stop")]
                for frame in frames:
                    self.wfile.write(("event: " + frame["type"] + "\ndata: " + json.dumps(frame) + "\n\n").encode())
                    self.wfile.flush()
            else:
                self.wfile.write(json.dumps(response).encode())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, ANTHROPIC_API_KEY="offline-placeholder",
               ANTHROPIC_BASE_URL=f"http://127.0.0.1:{server.server_port}",
               DEEPAGENTS_CODE_EXTENSIONS="0", DEEPAGENTS_CODE_EXPERIMENTAL="0")
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    command = [args.dcode, "--stdin", "--quiet", "--no-stream", "--no-interpreter", "--no-mcp",
               "--model", "anthropic:deepseek-flash", "--max-retries", "0", "--max-turns", "3"]
    try:
        value = subprocess.run(command, input=b"Offline policy probe. Respond normally after the denied tool.",
                               capture_output=True, timeout=90, env=env)
    finally:
        server.shutdown()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "stdout.log").write_bytes(value.stdout)
    (args.output / "stderr.log").write_bytes(value.stderr)
    (args.output / "fake-provider-requests.json").write_text(json.dumps(calls, indent=2))
    denied_returned = len(calls) == 2 and "Strict single-agent experiment" in json.dumps(calls[1]["messages"])
    evidence = dict(passed=value.returncode == 0 and denied_returned, returncode=value.returncode,
                    paid_calls=0, real_credentials=False, network="none", provider="loopback fake only",
                    fake_model_requests=len(calls), native_denial_returned_to_root=denied_returned)
    (args.output / "proof.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence), flush=True)
    raise SystemExit(0 if evidence["passed"] else 1)


if __name__ == "__main__":
    main()
