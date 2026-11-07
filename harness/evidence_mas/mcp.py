"""MAS newline JSON-RPC MCP server; local storage only, no execution."""

import argparse
import inspect
import json
import sys
import uuid

from .store import Store, StoreError, packed
from .decision import DecisionProtocol, TOOLS as DECISION_TOOLS, PROTOCOL


METHODS = {
    'workspace_trace': ('workspace.trace', Store.trace),
    'obs_list': ('obs.list', Store.obs_list),
    'obs_search': ('obs.search', Store.obs_search),
    'obs_read': ('obs.read', Store.obs_read),
}
DESCRIPTIONS = {
    'workspace_trace': 'Trace an observation/object ID with direction both/inbound/outbound and max_nodes 1..200. Metadata is not a semantic verdict.',
    'obs_read': 'Read field=input/output with bounded start/end offsets, at most 16000 characters.',
}


def tool_names(role, mode, protocol='observations-v1'):
    if protocol == PROTOCOL:
        return tool_names(role, 'observations') + [name for name in DECISION_TOOLS if role == 'lead' or name not in ('decision_select', 'decision_check')]
    return list(METHODS)


def schema(function):
    properties, required = {}, []
    for name, parameter in inspect.signature(function).parameters.items():
        if name in ('self', 'db', 'actor', 'role'):
            continue
        kind = 'object' if name=='filters' else 'integer' if name in ('start','end','cursor','limit','revision','max_nodes') else 'string'
        entry = {'type':[kind,'null'] if parameter.default is None else kind}
        if name in ('start','end','cursor'):
            entry['minimum'] = 0
        if name in ('limit','revision','max_nodes'):
            entry['minimum'] = 1
        if name in ('limit','max_nodes'):
            entry['maximum'] = 100 if name=='limit' else 200
        if name=='field':
            entry['enum'] = ['input','output']
        if name=='direction':
            entry['enum'] = ['both','inbound','outbound']
        properties[name] = entry
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    properties['operation_id'] = {'type':'string'}
    return dict(type='object', properties=properties, required=required, additionalProperties=False)


def validate(value, spec, path='arguments'):
    """Validate the bounded schema vocabulary generated above, before mutation."""
    kinds = {'string': str, 'integer': int, 'object': dict, 'array': list,
             'boolean': bool, 'null': type(None)}
    expected = spec.get('type')
    allowed = expected if isinstance(expected, list) else [expected]
    if expected and type(value) not in [kinds[k] for k in allowed]:
        raise StoreError(f'{path}: expected {expected}')
    if 'enum' in spec and value not in spec['enum']:
        raise StoreError(f'{path}: expected one of {spec["enum"]}')
    if value is None:
        return
    if isinstance(value, dict):
        properties = spec.get('properties', {})
        missing = set(spec.get('required', [])) - value.keys()
        extra = value.keys() - properties.keys() if spec.get('additionalProperties') is False else set()
        if missing:
            raise StoreError(f'{path}: missing fields {sorted(missing)}')
        if extra:
            raise StoreError(f'{path}: unexpected fields {sorted(extra)}')
        for key, child in value.items():
            if key in properties:
                validate(child, properties[key], path+'.'+key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate(child, spec.get('items', {}), f'{path}[{index}]')
    elif type(value) is int:
        if 'minimum' in spec and value < spec['minimum'] or 'maximum' in spec and value > spec['maximum']:
            raise StoreError(f'{path}: outside allowed range {spec.get("minimum")}..{spec.get("maximum")}')


class Server:
    def __init__(self, store, actor, role, mode='full', protocol='observations-v1'):
        self.store, self.actor, self.role = store, actor, role
        self.mode = mode
        if protocol not in ('observations-v1', PROTOCOL) or (protocol == PROTOCOL and mode != 'full'):
            raise StoreError('Invalid protocol/mode combination')
        self.protocol = protocol
        store.bind_mode(mode)
        self.initialized = False

    def available(self, name):
        return name in tool_names(self.role, self.mode, self.protocol)

    def handle(self, request):
        if isinstance(request, list):
            if not request:
                return dict(jsonrpc='2.0', id=None, error=dict(code=-32600, message='Empty batch'))
            replies = [self.handle(item) for item in request]
            return [r for r in replies if r is not None] or None
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
            return dict(jsonrpc='2.0', id=None, error=dict(code=-32600, message='Invalid request'))
        rid = request.get('id')
        method = request.get('method')
        if 'id' not in request:
            return None
        try:
            params = request.get('params', {})
            if not isinstance(params, dict):
                raise StoreError('Invalid params')
            if method == 'initialize':
                self.initialized = True
                result = dict(protocolVersion='2025-03-26', capabilities=dict(tools=dict(listChanged=False)),
                              serverInfo=dict(name='evidence', version='0.1.0'))
            elif method == 'ping':
                result = {}
            elif not self.initialized:
                raise StoreError('Initialize first')
            elif method == 'tools/list':
                result = dict(tools=[dict(name=name, description=entry[0] + ' in the current private run store. ' + DESCRIPTIONS.get(name, ''),
                                         inputSchema=schema(entry[1])) for name, entry in METHODS.items()
                                     if self.available(name)])
                if self.protocol == PROTOCOL:
                    result['tools'] += [dict(name=name, **DECISION_TOOLS[name])
                                       for name in DECISION_TOOLS if self.available(name)]
            elif method == 'tools/call':
                name = params.get('name')
                if not self.available(name):
                    raise StoreError('Unavailable tool')
                try:
                    arguments = params.get('arguments', {})
                    validate(arguments, DECISION_TOOLS[name]['inputSchema'] if name in DECISION_TOOLS else schema(METHODS[name][1]))
                    arguments = dict(arguments)
                    operation = arguments.pop('operation_id', None)
                    if name in DECISION_TOOLS:
                        function = getattr(DecisionProtocol(self.store), name.removeprefix('decision_'))
                        if name in ('decision_select', 'decision_read', 'decision_view'):
                            arguments.update(role=self.role, actor=self.actor)
                        value = function(**arguments)
                        if name != 'decision_select':
                            event = self.store.event(name.replace('_', '.', 1), arguments,
                                                     value, self.actor, self.role, None)
                            with self.store.connect() as db:
                                db.execute('INSERT INTO events(body) VALUES(?)', (event,))
                    else:
                        value = self.store.call(METHODS[name][0], arguments, self.actor, self.role, operation)
                    result = dict(content=[dict(type='text', text=packed(value))], isError=False)
                except Exception as exc:
                    try:
                        metadata = dict(tool=name, error_type=type(exc).__name__,
                                        error_code=getattr(exc,'code','tool_failure'))
                        with self.store.connect() as db:
                            db.execute('INSERT INTO events(body) VALUES(?)',
                                (self.store.event('workspace.error', {}, metadata, self.actor, self.role, None),))
                    except Exception:
                        pass  # Keep the original failure visible even if its audit cannot be persisted.
                    message = (str(exc) if isinstance(exc, StoreError) else
                               'Tool failed; outcome may be incomplete. No automatic retry was performed.')
                    if isinstance(exc, StoreError) and name in DESCRIPTIONS:
                        message += '\nUsage: ' + DESCRIPTIONS[name]
                    result = dict(content=[dict(type='text', text=message)], isError=True)
            else:
                return dict(jsonrpc='2.0', id=rid, error=dict(code=-32601, message='Method not found'))
            return dict(jsonrpc='2.0', id=rid, result=result)
        except (StoreError, TypeError):
            return dict(jsonrpc='2.0', id=rid, error=dict(code=-32602, message='Invalid parameters'))
        except Exception:
            return dict(jsonrpc='2.0', id=rid, error=dict(code=-32603, message='Internal error'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--actor', default='unknown')
    parser.add_argument('--role', choices=('lead', 'worker'), default='worker')
    parser.add_argument('--mode', choices=('full', 'observations'), default='full')
    parser.add_argument('--protocol', choices=('observations-v1', PROTOCOL), default='observations-v1')
    args = parser.parse_args()
    # Scope the native worker MCP process, never pretend this is a native agent ID.
    actor = args.actor + ':mcp:' + uuid.uuid4().hex if args.role == 'worker' else args.actor
    server = Server(Store(args.root, args.run_id), actor, args.role, args.mode, args.protocol)
    for line in sys.stdin:
        try:
            response = server.handle(json.loads(line))
        except ValueError:
            response = dict(jsonrpc='2.0', id=None, error=dict(code=-32700, message='Parse error'))
        if response is not None:
            print(packed(response), flush=True)


if __name__ == '__main__':
    main()
