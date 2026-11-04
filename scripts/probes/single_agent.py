"""Exercise strict Single delegation denial using dummy credentials and loopback only."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--argv-json", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fake-input-tokens", type=int, default=100)
    args = parser.parse_args()
    calls, issued, rejections = [], [], set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if "count_tokens" in self.path:
                response = dict(input_tokens=100)
            else:
                calls.append(body)
                for message in body.get("messages", []):
                    for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
                        if block.get("type") == "tool_result" and block.get("is_error"):
                            rejections.add(block.get("tool_use_id"))
                if len(issued) < 2:
                    name = ("Agent", "Task")[len(issued)]
                    issued.append(name)
                    content = [dict(type="tool_use", id="probe-"+name, name=name, input=dict(
                        description="Forbidden delegation probe", subagent_type="general-purpose",
                        prompt="Reply worker complete without tools."))]
                    stop = "tool_use"
                else:
                    content = [dict(type="text", text="Both delegation attempts were rejected. Root completed directly.")]
                    stop = "end_turn"
                response = dict(id="probe-"+str(len(calls)), type="message", role="assistant",
                    model=body.get("model", "deepseek-flash"), content=content, stop_reason=stop, stop_sequence=None,
                    usage=dict(input_tokens=args.fake_input_tokens, output_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0))
            self.send_response(200)
            streaming = body.get("stream") and "content" in response
            self.send_header("Content-Type", "text/event-stream" if streaming else "application/json")
            self.end_headers()
            if not streaming:
                self.wfile.write(json.dumps(response).encode())
                return
            block = response["content"][0]
            start = dict(block, **({"input": {}} if block["type"] == "tool_use" else {"text": ""}))
            delta = (dict(type="input_json_delta", partial_json=json.dumps(block["input"]))
                     if block["type"] == "tool_use" else dict(type="text_delta", text=block["text"]))
            frames = [dict(type="message_start", message=dict(response, content=[], stop_reason=None)),
                      dict(type="content_block_start", index=0, content_block=start),
                      dict(type="content_block_delta", index=0, delta=delta),
                      dict(type="content_block_stop", index=0),
                      dict(type="message_delta", delta=dict(stop_reason=stop, stop_sequence=None), usage=dict(output_tokens=10)),
                      dict(type="message_stop")]
            for frame in frames:
                self.wfile.write(("event: "+frame["type"]+"\ndata: "+json.dumps(frame)+"\n\n").encode())
                self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, ANTHROPIC_AUTH_TOKEN="offline-placeholder",
               ANTHROPIC_BASE_URL="http://127.0.0.1:"+str(server.server_port))
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        result = subprocess.run(json.loads(args.argv_json), input=b"Offline strict Single denial probe.",
                                capture_output=True, env=env, timeout=120)
    finally:
        server.shutdown()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/"stdout.log").write_bytes(result.stdout)
    (args.output/"stderr.log").write_bytes(result.stderr)
    (args.output/"fake-provider-requests.json").write_text(json.dumps(calls, indent=2))
    proof = dict(returncode=result.returncode, paid_calls=0, real_credentials=False, network="none",
                 fake_model_requests=len(calls), attempted_tools=issued,
                 delegation_rejections_observed=len(rejections & {"probe-Agent", "probe-Task"}))
    (args.output/"transport.json").write_text(json.dumps(proof, indent=2))
    print(json.dumps(proof), flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
