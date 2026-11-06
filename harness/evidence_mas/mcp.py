"""MAS newline JSON-RPC MCP server; local storage only, no execution."""

import argparse
import inspect
import json
import sqlite3
import sys
import uuid

from .store import Store, StoreError, packed
from .decision import DecisionProtocol, TOOLS as DECISION_TOOLS, PROTOCOL


METHODS = {
    'workspace_trace': ('workspace.trace', Store.trace),
    'artifact_read': ('artifact.read', Store.artifact_read),
    'source_register': ('source.register', Store.source),
    'execution_register': ('execution.register', Store.execution),
    'outcome_register': ('outcome.register', Store.outcome),
    'obs_list': ('obs.list', Store.obs_list),
    'obs_search': ('obs.search', Store.obs_search),
    'obs_read': ('obs.read', Store.obs_read),
    'ledger_open_issue': ('ledger.open_issue', Store.issue),
    'ledger_propose': ('ledger.propose', Store.propose),
    'ledger_revise_candidate': ('ledger.revise_candidate', Store.revise),
    'ledger_attach': ('ledger.attach', Store.attach),
    'ledger_record_selection': ('ledger.record_selection', Store.select),
    'ledger_view': ('ledger.view', Store.view),
    'ledger_history': ('ledger.history', Store.history),
    'ledger_retract_evidence': ('ledger.retract_evidence', Store.retract_evidence),
}
OBJECTS = {'parameters', 'filters', 'execution_ref', 'outcome_ref', 'source_ref', 'choice', 'changes', 'ref'}
ARRAYS = {'inputs', 'source_refs', 'assumptions', 'depends_on', 'confirmation_evidence_ids', 'considered_ids', 'evidence_refs'}
INTEGERS = {'start', 'end', 'cursor', 'limit', 'expected_revision', 'since_revision', 'revision', 'max_nodes'}
BOOLEANS = {'dependencies_complete', 'disclose_unconfirmed', 'detail'}
REFERENCE = dict(type='object', properties={'id': {'type': 'string'},
    'revision': {'type': 'integer', 'minimum': 1}}, required=['id', 'revision'], additionalProperties=False)
DESCRIPTIONS = {
    'workspace_trace': 'Trace an object ID, not a tool_call_id or blob hash. direction is both/inbound/outbound; max_nodes must be 1..200. Returns typed provenance, not raw payloads.',
    'source_register': 'Register a snapshot using source_type task, codebook, document, or data_manifest; not a file path reference.',
    'execution_register': 'Register code and parameters without executing them. inputs must be source references {id, revision}.',
    'outcome_register': 'Bind an actual result to an execution reference and observation; status must match the observation.',
    'artifact_read': 'Read a source, execution, or outcome using ref={id, revision}, not an entire returned object.',
    'ledger_propose': 'Propose a candidate. Explicitly declare dependencies_complete: true for a complete dependency list (including empty for independent choices), false if unknown. depends_on contains only candidate/selection references, never sources or observations.',
    'obs_read': 'Read input or output text with field=input/output. Ranges are clamped to available text and at most 16000 characters.',
    'ledger_view': 'Compact decision summary by default. Set detail=true only when full evidence claims and dependency details are needed.',
    'ledger_record_selection': 'Lead selects choice={id, revision} or null. considered_ids are candidate IDs; evidence_refs are EvidenceLink references, not observation IDs. First expected_revision=0. Unknown/stale choice requires disclose_unconfirmed=true.',
    'ledger_attach': 'Link one observation ID OR source_ref={id, revision} to a candidate/issue target_id. This creates an EvidenceLink, distinct from the observation.',
}


def tool_names(role, mode, protocol='ledger-v1'):
    if protocol == PROTOCOL:
        return tool_names(role, 'observations') + [name for name in DECISION_TOOLS if role == 'lead' or name not in ('decision_select', 'decision_check')]
    return [name for name in METHODS
            if (role == 'lead' or name != 'ledger_record_selection')
            and (mode == 'full' or name in ('obs_list', 'obs_search', 'obs_read', 'artifact_read', 'workspace_trace'))]


def schema(function):
    properties, required = {}, []
    for name, parameter in inspect.signature(function).parameters.items():
        if name in ('self', 'db', 'actor', 'role'):
            continue
        kind = ('object' if name in OBJECTS else 'array' if name in ARRAYS else
                'integer' if name in INTEGERS else 'boolean' if name in BOOLEANS else 'string')
        entry = {} if name == 'result' else {'type': [kind, 'null'] if parameter.default is None or name == 'choice' else kind}
        if kind == 'array':
            entry['items'] = REFERENCE if name in {'inputs', 'source_refs', 'depends_on', 'evidence_refs'} else {'type': 'string'}
        if name in {'execution_ref', 'outcome_ref', 'source_ref', 'choice', 'ref'}:
            entry.update(REFERENCE)
            if parameter.default is None or name == 'choice':
                entry['type'] = ['object', 'null']
            entry['description'] = 'Exact version reference: {"id": "returned-object-id", "revision": 1}; no extra fields.'
        if name == 'source_type':
            entry['enum'] = ['task', 'codebook', 'document', 'data_manifest']
        if name == 'status':
            entry['enum'] = ['success', 'failed', 'cancelled', 'unknown']
        if name == 'relation':
            entry['enum'] = ['supports', 'contradicts', 'contextual']
        if name == 'direction':
            entry['enum'] = ['both', 'inbound', 'outbound']
        if name == 'field':
            entry['enum'] = ['input', 'output']
        if name == 'max_nodes':
            entry.update(minimum=1, maximum=200)
        if name in {'cursor', 'start', 'expected_revision', 'since_revision'}:
            entry['minimum'] = 0
        if name in {'revision', 'limit'}:
            entry['minimum'] = 1
        if name == 'limit':
            entry['maximum'] = 100
        if name == 'obs_id':
            entry['description'] = 'The observation id returned by obs_list/obs_search or hook context; not tool_call_id, output_ref, or a whole object.'
        if name == 'target_id':
            entry['description'] = 'Issue or Candidate object id only; this is not a version reference or observation id.'
        if name == 'depends_on':
            entry['description'] = 'Only candidate or selection version references. Sources/observations are evidence or inputs, not decision dependencies.'
        properties[name] = entry
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    if function is Store.propose:
        required.append('dependencies_complete')
    properties['operation_id'] = {'type': 'string', 'description': 'Optional retry key scoped to this actor and role; reuse only for the exact same request.'}
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
    def __init__(self, store, actor, role, mode='full', protocol='ledger-v1'):
        self.store, self.actor, self.role = store, actor, role
        self.mode = mode
        if protocol not in ('ledger-v1', PROTOCOL) or (protocol == PROTOCOL and mode != 'full'):
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
                        if name == 'decision_select':
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
                except (StoreError, OSError, ValueError, sqlite3.Error) as exc:
                    message = str(exc) if isinstance(exc, StoreError) else 'Storage or encoding failure'
                    if isinstance(exc, StoreError) and name in DESCRIPTIONS:
                        message += '\nUsage: ' + DESCRIPTIONS[name]
                    result = dict(content=[dict(type='text', text=message)], isError=True)
            else:
                return dict(jsonrpc='2.0', id=rid, error=dict(code=-32601, message='Method not found'))
            return dict(jsonrpc='2.0', id=rid, result=result)
        except (StoreError, TypeError):
            return dict(jsonrpc='2.0', id=rid, error=dict(code=-32602, message='Invalid parameters'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--actor', default='unknown')
    parser.add_argument('--role', choices=('lead', 'worker'), default='worker')
    parser.add_argument('--mode', choices=('full', 'observations'), default='full')
    parser.add_argument('--protocol', choices=('ledger-v1', PROTOCOL), default='ledger-v1')
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
