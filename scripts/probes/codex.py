"""Loopback Responses fixture for pinned native Codex, never a real provider."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--argv-json", required=True)
    parser.add_argument("--subagents", action="store_true")
    args = parser.parse_args()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            Path("/native/probe-requests.json").write_text(json.dumps(requests))
            tools = request.get("tools", [])
            names = {t.get("name") for t in tools}
            for tool in tools:
                names.update(t.get("name") for t in tool.get("tools", []))
            child = any("Message Type: NEW_TASK" in json.dumps(x) for x in request.get("input", [])
                        if isinstance(x, dict) and x.get("type") != "function_call")
            outputs = [x for x in request.get("input", []) if isinstance(x, dict) and x.get("type") == "function_call_output"]
            if args.subagents and not child and not outputs:
                item = dict(type="function_call", id="fc_1", call_id="call_spawn", name="spawn_agent",
                            namespace="collaboration", arguments=json.dumps(dict(message="PROBE_CHILD: reply OK", task_name="probe_child", fork_turns="none")))
            elif args.subagents and not child and len(outputs) == 1:
                item = dict(type="function_call", id="fc_2", call_id="call_wait", name="wait_agent",
                            namespace="collaboration", arguments=json.dumps(dict(timeout_ms=10000)))
            elif not child and len(outputs) == (2 if args.subagents else 0):
                item = dict(type="function_call", id="fc_shell", call_id="call_shell", name="exec_command",
                            arguments=json.dumps(dict(cmd="printf probe-ok > /workspace/probe-result.txt")))
            else:
                item = dict(type="message", id="msg_"+uuid.uuid4().hex, role="assistant", status="completed",
                            content=[dict(type="output_text", text="OK", annotations=[])])
            response = dict(id="resp_"+uuid.uuid4().hex, object="response", status="completed", output=[item],
                            usage=dict(input_tokens=100, output_tokens=10, total_tokens=110))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            events = [dict(type="response.created", response={**response, "status":"in_progress", "output":[]}),
                      dict(type="response.output_item.added", output_index=0, item=item),
                      dict(type="response.output_item.done", output_index=0, item=item),
                      dict(type="response.completed", response=response)]
            for event in events:
                self.wfile.write(("event: "+event["type"]+"\ndata: "+json.dumps(event)+"\n\n").encode())
            self.wfile.flush()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    command = json.loads(args.argv_json)
    command[-1:-1] = ["-c", 'model_providers.deepseek.base_url="http://127.0.0.1:'+str(server.server_port)+'"']
    try:
        result = subprocess.run(command, input="Use native subagents; reply OK.", text=True, capture_output=True, timeout=60)
        Path("/native/probe-stdout.jsonl").write_text(result.stdout)
        Path("/native/probe-stderr.log").write_text(result.stderr)
        print(json.dumps(dict(returncode=result.returncode, requests=len(requests))))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
