#!/usr/bin/env python3
"""Exercise real CooperBench private descriptions with scripted agents, no Docker/API."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from fakes import ScriptedClient
from benchmarks.cooperbench.adapter import verify_checkout, discover, make_team, REVISION
from harness.execution import ContainerWorkspace
from harness.trace import Trace, read_trace, validate


def policy(messages, tools, choice):
    if 'submit_assignment' in tools:
        return dict(calls=[('submit_assignment', dict(report='Scripted control-flow check, not implemented code.'))])
    return dict(content='Offline submission only; not a solution.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scheduler', choices=['controlled', 'async'], default='async')
    args = parser.parse_args()
    def deny(*args, **kwargs):
        raise AssertionError('Offline model network prohibited')
    socket.socket.connect = deny
    socket.create_connection = deny
    dataset = verify_checkout()
    # One deterministic pair per repository, selected without inspecting results.
    selected = {}
    for pair in discover(dataset):
        selected.setdefault(pair.repo, pair)
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    class UnusedWorkspace:
        def tools(self):
            tools = ContainerWorkspace('never-started').tools()
            for tool in tools:
                tool.run = deny
            return tools
    for i, pair in enumerate(selected.values()):
        folder = args.output / str(i)
        folder.mkdir()
        with Trace(folder / 'trace.jsonl', str(i)) as trace:
            trace.emit('run_start', kind='scripted')
            team = make_team(pair, dataset, {r: UnusedWorkspace() for r in ('worker_a', 'worker_b')},
                             ScriptedClient(policy), trace, scheduler=args.scheduler)
            manifest = dict(pair=asdict(pair), scheduler=args.scheduler, upstream_revision=REVISION,
                            communication_policy=team.control['communication_policy'], kind='scripted',
                            member_limits=team.member_limits, submission_contract='report-only-v1')
            (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2))
            result = team.run_task(pair.request)
            (folder / 'result.json').write_text(json.dumps(result, indent=2))
            (folder / 'accounting.json').write_text(json.dumps(dict(cost_usd_estimate=0, paid_calls=0)))
            trace.emit('run_end', status=result['status'])
        assert result['termination'] == 'tasks_submitted', result
        assert result['submission_status'] == 'submitted', result
        assert result['verification']['status'] == 'not_run', result
        assert team.control['submission_contract'] == 'report-only-v1'
        assert validate(read_trace(trace.path)) == []
        results.append(dict(pair=pair.key, calls=result['calls'], control_digest=team.control_digest,
                            submission_status=result['submission_status'], verification=result['verification']['status']))
    summary = dict(upstream_revision=REVISION, scheduler=args.scheduler, runs=results,
                   communication_policy=team.control['communication_policy'],
                   submission_contract='report-only-v1', paid_calls=0, native_code_evaluation=False)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
