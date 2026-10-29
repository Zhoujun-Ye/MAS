#!/usr/bin/env python3
"""Exercise native retrieval and four-form team control with zero paid calls."""
import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from fakes import ScriptedClient
from benchmarks.browsecomp_plus.adapter import (ROOT as BENCH, BM25, CorpusTools, FORMS, LIMITS,
    OUTPUT, task_rows, public_task, parse_plan, valid_final)
from harness.agent_team import AgentTeam
from harness.config import source_digest
from harness.pool import bind_permissions
from harness.trace import Trace, read_trace, validate


def policy(messages, tools, choice):
    if messages[0]['content'].startswith('You are a message encoder'):
        value = json.loads(messages[-1]['content'])
        content = value['intent']
        if 'schema' in value['handoff_instruction']:
            content = json.dumps(dict(conclusion=content, key_facts=[], ruled_out=[], open_questions=[], confidence='low'))
        return dict(content=content)
    role = messages[0]['content'].split('Reusable role: ')[1].split('.')[0]
    count = sum(m['role'] == 'assistant' for m in messages)
    if role == 'leader':
        if count == 0:
            return dict(calls=[('search', dict(query='university history', k=1))])
        return dict(content=json.dumps(dict(answer='offline_fixture', reasoning='No model inference performed', citations=[])))
    if count == 0:
        return dict(calls=[('search', dict(query='university history', k=1))])
    return dict(calls=[('finish_assignment', dict(report='Scripted observation available', evidence_ids=[]))])


def deny(*args, **kwargs):
    raise AssertionError('Offline test attempted Python network access')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    socket.create_connection = deny
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    args.output.mkdir(parents=True, exist_ok=False)
    prepared = json.loads((BENCH / 'assets/team-prepared-v1.json').read_text())
    rows = {str(r['query_id']): r for r in task_rows()}
    native = BM25()
    hits = native.search('university history', 2)
    assert len(hits) == 2
    assert native.get_document(hits[0]['docid'])['text'] == hits[0]['text']
    outcomes = []
    for task_id in prepared['task_ids']:
        request = public_task(rows[task_id])
        plan = parse_plan(request, json.dumps(dict(members=[dict(role=r, assignment='Scripted transport check')
                                                            for r in ('researcher', 'reviewer', 'leader')])))
        controls = set()
        for form in FORMS:
            corpus = CorpusTools(native)
            tools = corpus.tools()
            path = args.output / 'traces' / f'{task_id}-{form}.jsonl'
            with Trace(path, f'{task_id}-{form}') as trace:
                trace.emit('run_start', kind='offline_fixture')
                team = AgentTeam(plan, form, ScriptedClient(policy), trace, tools,
                                 bind_permissions(plan, {t.name: 'search' for t in tools}),
                                 final_validator=valid_final, final_contract=OUTPUT, **LIMITS)
                result = team.run_task(request)
                assert result['status'] == 'completed' and result['termination'] == 'workers_completed', result
                assert not corpus.errors
                trace.emit('run_end', status=result['status'])
            assert not validate(read_trace(path))
            controls.add(team.control_digest)
            outcomes.append(dict(task_id=task_id, form=form, status=result['status'], calls=result['calls']))
        assert len(controls) == 1
    summary = dict(paid_calls=0, source=source_digest(), runs=outcomes,
                   conclusion='Native tools and control flow only; no model quality, saturation or semantic-loss claim')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
