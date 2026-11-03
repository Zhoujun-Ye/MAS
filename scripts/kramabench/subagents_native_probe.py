"""Run installed Claude print/subagent transport against a no-network fake API."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--claude', required=True)
    parser.add_argument('--hooks', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    calls, delegated = [], False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            nonlocal delegated
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if 'count_tokens' in self.path:
                response = dict(input_tokens=100)
            else:
                calls.append(body)
                tools = {t.get('name') for t in body.get('tools', [])}
                if not delegated and 'Agent' in tools:
                    delegated = True
                    content = [dict(type='tool_use', id='probe-delegate', name='Agent', input=dict(
                        name='probe-worker', subagent_type='general-purpose', description='Offline subagent probe',
                        prompt='Reply worker complete, without using any tools.'))]
                    stop = 'tool_use'
                else:
                    content = [dict(type='text', text='offline subagent probe complete')]
                    stop = 'end_turn'
                response = dict(id='probe-'+str(len(calls)), type='message', role='assistant',
                    model=body.get('model','deepseek-flash'), content=content, stop_reason=stop, stop_sequence=None,
                    usage=dict(input_tokens=100, output_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0))
            self.send_response(200)
            streaming = body.get('stream') and 'content' in response
            self.send_header('Content-Type','text/event-stream' if streaming else 'application/json')
            self.end_headers()
            if streaming:
                block = response['content'][0]
                start = dict(block, **({'input':{}} if block['type']=='tool_use' else {'text':''}))
                delta = (dict(type='input_json_delta',partial_json=json.dumps(block['input']))
                         if block['type']=='tool_use' else dict(type='text_delta',text=block['text']))
                frames = [dict(type='message_start',message=dict(response,content=[],stop_reason=None)),
                          dict(type='content_block_start',index=0,content_block=start),
                          dict(type='content_block_delta',index=0,delta=delta),
                          dict(type='content_block_stop',index=0),
                          dict(type='message_delta',delta=dict(stop_reason=stop,stop_sequence=None),usage=dict(output_tokens=10)),
                          dict(type='message_stop')]
                for frame in frames:
                    self.wfile.write(('event: '+frame['type']+'\ndata: '+json.dumps(frame)+'\n\n').encode())
                    self.wfile.flush()
            else:
                self.wfile.write(json.dumps(response).encode())
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    hook = dict(type='command',command=f'python3 -I {args.hooks} --output /native/observer/events.jsonl')
    settings = dict(env=dict(CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS='0'), hooks={
        event:[dict(hooks=[hook])] for event in ('SessionStart','SessionEnd','SubagentStart','SubagentStop','TeammateIdle')})
    env = dict(os.environ, ANTHROPIC_AUTH_TOKEN='offline-placeholder',
               ANTHROPIC_BASE_URL=f'http://127.0.0.1:{server.server_port}',CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS='0')
    env.pop('ANTHROPIC_API_KEY',None)
    command = [args.claude,'--print','--verbose','--output-format','stream-json','--model','deepseek-flash[1m]',
               '--settings',json.dumps(settings),'--setting-sources','','--strict-mcp-config',
               '--mcp-config','{"mcpServers":{}}','--allowedTools','Agent,Read']
    try:
        result = subprocess.run(command,input=b'Offline native delegation probe. Use Agent for a small task.',
                                capture_output=True,env=env,timeout=90)
    finally:
        server.shutdown()
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'stdout.log').write_bytes(result.stdout)
    (args.output/'stderr.log').write_bytes(result.stderr)
    (args.output/'fake-provider-requests.json').write_text(json.dumps(calls,indent=2))
    proof = dict(returncode=result.returncode,paid_calls=0,real_credentials=False,network='none',
                 provider='loopback fake only',fake_model_requests=len(calls),delegate_tool_issued=delegated)
    (args.output/'transport.json').write_text(json.dumps(proof,indent=2))
    print(json.dumps(proof),flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
