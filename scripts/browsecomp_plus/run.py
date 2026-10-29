#!/usr/bin/env python3
"""Six once-only Leader plans and 24 fixed-plan team executions; no paid judge."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import signal
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.browsecomp_plus.adapter import (ROOT as BENCH, BM25, CorpusTools, FORMS, LIMITS,
    OUTPUT, PLAN_SYSTEM, task_rows, public_task, planning_input, parse_plan, valid_final, exact_grade)
from harness.agent import Agent
from harness.agent_team import AgentTeam
from harness.config import load_config, load_env, source_digest, digest
from harness.llm import ChatClient, ModelConfig
from harness.pool import Member, TeamSpec, bind_permissions
from harness.runner import RunSpec, prepare_output, record_balance, run_batch, write_json
from harness.trace import Trace, read_trace, usage_summary, validate
from harness.accounting import estimate


def frozen_plan(row, cfg, directory, stopping, pricing):
    task_id = str(row['query_id'])
    path = directory / f'{task_id}.json'
    request = public_task(row)
    if path.exists():
        record = json.loads(path.read_text())
        plan = TeamSpec(record['plan']['task_digest'], tuple(Member(**m) for m in record['plan']['members']),
                        record['plan']['selector'])
        plan.validate_task(request)
        if record['plan_digest'] != plan.digest:
            raise ValueError('Saved plan digest mismatch')
        return plan
    trace_path = directory / f'{task_id}.jsonl'
    if trace_path.exists():
        raise RuntimeError('Prior planning attempt has no saved plan; stop instead of silently adding paid planning calls')
    if stopping.is_set():
        raise RuntimeError('Interrupted before planning')
    client = ChatClient(cfg)
    try:
        with Trace(trace_path, f'plan_{task_id}') as trace:
            trace.emit('run_start', task_id=task_id, phase='planning')
            agent = Agent('leader_planner', client, trace, PLAN_SYSTEM, usage_role='planning')
            agent.append(dict(role='user', content=planning_input(request)))
            try:
                reply = agent.call(tool_choice='none')
                if reply.finish_reason == 'length' or reply.message.get('tool_calls'):
                    agent.refuse(reply.message.get('tool_calls') or [])
                    raise ValueError('Invalid or truncated plan; no paid repair authorized')
                plan = parse_plan(request, reply.message.get('content') or '')
                trace.emit('final', agent=agent.name, content=reply.message['content'])
                trace.emit('run_end', status='completed')
            except Exception as error:
                trace.emit('error', message=str(error))
                trace.emit('run_end', status='error')
                raise
        events = read_trace(trace_path)
        write_json(path, dict(plan=plan.payload(), plan_digest=plan.digest, usage=usage_summary(events),
                              cost_usd_estimate=estimate(events, pricing)))
        print(json.dumps(dict(planned=task_id, roles=[m.role for m in plan.members], plan_digest=plan.digest)), flush=True)
        return plan
    finally:
        client._http.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorized-6-plans-24-runs', action='store_true', required=True)
    parser.add_argument('--plan-only', action='store_true', help='Generate the same six frozen plans, then stop for review')
    args = parser.parse_args()
    config = load_config(ROOT / 'configs/base.yaml')
    cfg = ModelConfig(**config['agent_model'])
    prepared = json.loads((BENCH / 'assets/team-prepared-v1.json').read_text())
    rows = {str(r['query_id']): r for r in task_rows()}
    ids = prepared['task_ids']
    if len(ids) != 6 or len(set(ids)) != 6:
        raise ValueError('Scope is exactly six tasks')
    base = dict(prepared=prepared, model=asdict(cfg), limits=LIMITS, forms=FORMS, source=source_digest(),
                driver=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), pricing=config['pricing'],
                planner_system=PLAN_SYSTEM, public_tasks={k: public_task(rows[k]) for k in ids}, concurrency=3,
                scope='6 planning calls + 24 team runs; no paid judge, no automatic expansion or paid replay')
    prepare_output(args.output, base)
    stopping = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())
    # Initialize native retrieval before credentials and before any paid call.
    retriever = BM25()
    if not retriever.search('history', 1):
        raise RuntimeError('Native retrieval startup check failed')
    load_env()
    phase = 'planning' if args.plan_only else 'execution'
    record_balance(args.output, cfg, phase + '_start')
    try:
        plans = {k: frozen_plan(rows[k], cfg, args.output / 'plans', stopping, config['pricing']) for k in ids}
        if args.plan_only:
            print(json.dumps(dict(plans_saved=len(plans), team_runs_started=0)), flush=True)
            return
        runout = args.output / 'runs'
        specs = [RunSpec('browsecomp_plus', k, f, 0) for i, k in enumerate(ids)
                 for f in FORMS[i % 4:] + FORMS[:i % 4]]
        prepare_output(runout, dict(base_digest=digest(base), plans={k: p.payload() for k, p in plans.items()},
                                    specs=[asdict(s) for s in specs]))

        def execute(spec, trace):
            if stopping.is_set():
                return dict(status='skipped', reason='interrupted')
            corpus = CorpusTools(retriever)
            tools = corpus.tools()
            plan = plans[spec.task_id]
            client = ChatClient(cfg)
            try:
                team = AgentTeam(plan, spec.condition, client, trace, tools,
                                 bind_permissions(plan, {t.name: 'search' for t in tools}),
                                 final_validator=valid_final, final_contract=OUTPUT,
                                 should_stop=lambda: stopping.is_set() or bool(corpus.errors), **LIMITS)
                result = team.run_task(public_task(rows[spec.task_id]))
                if corpus.errors:
                    raise RuntimeError('Native retrieval failure: ' + str(corpus.errors))
                if result['status'] == 'completed':
                    result['grade'] = exact_grade(json.loads(result['final'])['answer'], rows[spec.task_id]['answer'])
                    result['success'] = result['grade']['correct']
                result.update(retrieved_docids=sorted(corpus.retrieved), plan_digest=plan.digest, semantic_loss=None)
                if result['status'] != 'completed':
                    stopping.set()  # Investigate an engineering stop before launching more paid work.
                return result
            except Exception:
                stopping.set()
                raise
            finally:
                client._http.close()

        print(json.dumps(run_batch(specs, execute, runout, 3, config['pricing'])), flush=True)
        problems = {p.name: issues for p in (runout / 'traces').glob('*.jsonl') if (issues := validate(read_trace(p)))}
        print(json.dumps(dict(integrity_errors=problems)), flush=True)
    finally:
        record_balance(args.output, cfg, phase + '_end')


if __name__ == '__main__':
    main()
