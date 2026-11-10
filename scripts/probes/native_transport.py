"""Standalone in-container Single/Subagents fixture, loopback fake API only."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading


class Fixture:
    def __init__(self, mode, tokens):
        self.single = mode == 'single-agent'
        self.tokens = tokens
        self.calls, self.issued, self.rejections = [], [], set()
        self.delegated = False
        self.lock = threading.Lock()

    def reply(self, body):
        with self.lock:
            if len(self.calls) >= 32:
                raise ValueError('Synthetic request ceiling exceeded')
            self.calls.append(body)
            for message in body.get('messages', []):
                for block in message.get('content', []) if isinstance(message.get('content'), list) else []:
                    if block.get('type') == 'tool_result' and block.get('is_error'):
                        self.rejections.add(block.get('tool_use_id'))
            if self.single and len(self.issued) < 2:
                name = ('Agent', 'Task')[len(self.issued)]
                self.issued.append(name)
                block = dict(type='tool_use', id='probe-'+name, name=name, input=dict(
                    description='Forbidden delegation probe', subagent_type='general-purpose',
                    prompt='Reply worker complete without tools.'))
            elif not self.single and not self.delegated and any(t.get('name') == 'Agent' for t in body.get('tools', [])):
                self.delegated = True
                block = dict(type='tool_use', id='probe-delegate', name='Agent', input=dict(
                    name='probe-worker', subagent_type='general-purpose', description='Offline subagent probe',
                    prompt='Reply worker complete, without using any tools.'))
            else:
                block = dict(type='text', text='Offline native probe complete.')
            tokens = self.tokens if self.single or block['type'] == 'text' else 100
            return dict(id='probe-'+str(len(self.calls)), type='message', role='assistant', model=body['model'],
                content=[block], stop_reason='tool_use' if block['type']=='tool_use' else 'end_turn', stop_sequence=None,
                usage=dict(input_tokens=tokens, output_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0))


def frames(response):
    block = response['content'][0]
    start = dict(block, **({'input':{}} if block['type']=='tool_use' else {'text':''}))
    delta = (dict(type='input_json_delta', partial_json=json.dumps(block['input']))
             if block['type']=='tool_use' else dict(type='text_delta', text=block['text']))
    return [dict(type='message_start', message=dict(response, content=[], stop_reason=None)),
        dict(type='content_block_start', index=0, content_block=start),
        dict(type='content_block_delta', index=0, delta=delta), dict(type='content_block_stop', index=0),
        dict(type='message_delta', delta=dict(stop_reason=response['stop_reason'], stop_sequence=None), usage=dict(output_tokens=10)),
        dict(type='message_stop')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('single-agent','subagents'), required=True)
    parser.add_argument('--argv-json', required=True, help='Exact pinned adapter command')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fake-input-tokens', type=int, default=100)
    args = parser.parse_args()
    fixture = Fixture(args.mode, args.fake_input_tokens)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            try:
                response = dict(input_tokens=100) if 'count_tokens' in self.path else fixture.reply(body)
            except ValueError:
                self.send_error(500, 'Synthetic request ceiling exceeded')
                return
            streaming = body.get('stream') and 'content' in response
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream' if streaming else 'application/json')
            self.end_headers()
            if streaming:
                for frame in frames(response):
                    self.wfile.write(('event: '+frame['type']+'\ndata: '+json.dumps(frame)+'\n\n').encode())
                    self.wfile.flush()
            else:self.wfile.write(json.dumps(response).encode())
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, ANTHROPIC_AUTH_TOKEN='offline-placeholder',
               ANTHROPIC_BASE_URL=f'http://127.0.0.1:{server.server_port}')
    env.pop('ANTHROPIC_API_KEY',None)
    prompt = (b'Offline strict Single denial probe.' if fixture.single else
              b'Offline native delegation probe. Use Agent for a small task.')
    try:
        result = subprocess.run(json.loads(args.argv_json), input=prompt, capture_output=True, env=env, timeout=120)
    finally:
        server.shutdown();server.server_close()
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'stdout.log').write_bytes(result.stdout)
    (args.output/'stderr.log').write_bytes(result.stderr)
    (args.output/'fake-provider-requests.json').write_text(json.dumps(fixture.calls,indent=2))
    proof = dict(returncode=result.returncode, paid_calls=0, real_credentials=False, network='none',
        provider='loopback fake only', fake_model_requests=len(fixture.calls), delegate_tool_issued=fixture.delegated,
        attempted_tools=fixture.issued, delegation_rejections_observed=len(fixture.rejections & {'probe-Agent','probe-Task'}))
    (args.output/'transport.json').write_text(json.dumps(proof,indent=2))
    print(json.dumps(proof),flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
