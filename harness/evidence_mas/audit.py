"""Read-only checks of explicitly requested workflow steps, not answer grading."""

import json

from .mcp import METHODS


def check_workflow(store, requirements):
    known = {method for method, _ in METHODS.values()}
    for role, methods in requirements.items():
        if role not in ('lead', 'worker') or not isinstance(methods, (list, tuple)):
            raise ValueError('Expected lead/worker method lists')
        if any(method not in known for method in methods):
            raise ValueError('Unknown required workspace method')
    with store.connect() as db:
        events = [json.loads(row[0]) for row in db.execute('SELECT body FROM events')]
    observed = {(event['role'], event['method']) for event in events}
    missing = [{'role': role, 'method': method} for role, methods in requirements.items()
               for method in methods if (role, method) not in observed]
    return dict(complete=not missing, missing=missing,
                scope='Successful recorded calls only; not evidence of comprehension, correctness, or submission validity')
