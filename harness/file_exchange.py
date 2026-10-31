"""Explicit immutable workspace transfers without model-mediated byte copying."""
import json

from .agent import Observation, Tool


def exchange_tools(get_team, export, apply):
    def share(args, agent):
        team = get_team()
        recipient = args['recipient']
        if recipient == agent.name or recipient not in team.agents:
            raise ValueError('Select a different teammate')
        payload = export(agent.name, args['paths'])
        with team.lock:
            record = team.information.publish(agent.name, 'artifact', dict(
                title='Workspace changes', content=json.dumps(payload),
                format='workspace-patch-v1'))
            team.queue(agent.name, recipient, args.get('message') or 'Shared workspace changes.',
                       [], artifact_ids=[record['id']])
        return Observation('Shared immutable changes as ' + record['id'])

    def receive(args, agent):
        team = get_team()
        with team.lock:
            record = team.information.authorized(agent.name, args['id'])
            if record['kind'] != 'artifact' or record['data'].get('format') != 'workspace-patch-v1':
                raise ValueError('Expected an explicitly shared workspace patch')
            payload = json.loads(record['data']['content'])
        return apply(agent.name, payload)

    return [
        Tool('share_files', 'Share selected implementation changes verbatim with a teammate; no copying into text needed.',
             dict(type='object', properties=dict(recipient=dict(type='string'),
                  paths=dict(type='array', items=dict(type='string'), minItems=1), message=dict(type='string')),
                  required=['recipient', 'paths'], additionalProperties=False), share, read_only=True),
        Tool('import_files', 'Apply an explicitly granted immutable workspace patch in your own workspace. Conflicts are reported, never resolved automatically.',
             dict(type='object', properties=dict(id=dict(type='string')), required=['id'], additionalProperties=False), receive),
    ]
