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
    OUTPUT, TOOL_CAPABILITIES, task_rows, public_task, valid_final, exact_grade)
from harness.agent_team import AgentTeam
from harness.config import load_config, load_env, source_digest, digest
from harness.llm import ChatClient, ModelConfig
from harness.pool import bind_permissions
from harness.planning import PLAN_SYSTEM, frozen_plan
from harness.runner import RunSpec, prepare_output, record_balance, run_batch
from harness.trace import read_trace, validate


def concurrency_value(value):
    value = int(value)
    if not 1 <= value <= 16:
        raise argparse.ArgumentTypeError('Experiment concurrency must be between 1 and 16')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorized-6-plans-24-runs', action='store_true', required=True)
    parser.add_argument('--plan-only', action='store_true', help='Generate the same six frozen plans, then stop for review')
    parser.add_argument('--concurrency', type=concurrency_value, default=6,
                        help='Independent experiments in flight (1-16); does not change within-team scheduling')
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
                planner_system=PLAN_SYSTEM, public_tasks={k: public_task(rows[k]) for k in ids}, concurrency=args.concurrency,
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
        plans = {k: frozen_plan(k, public_task(rows[k]), cfg, args.output / 'plans', stopping,
                                config['pricing'], TOOL_CAPABILITIES) for k in ids}
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
                                 bind_permissions(plan, TOOL_CAPABILITIES),
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

        print(json.dumps(run_batch(specs, execute, runout, args.concurrency, config['pricing'])), flush=True)
        problems = {p.name: issues for p in (runout / 'traces').glob('*.jsonl') if (issues := validate(read_trace(p)))}
        print(json.dumps(dict(integrity_errors=problems)), flush=True)
    finally:
        record_balance(args.output, cfg, phase + '_end')


if __name__ == '__main__':
    main()
