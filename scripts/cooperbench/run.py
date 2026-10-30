#!/usr/bin/env python3
"""One explicitly authorized pair on two pre-provisioned private Docker containers."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import Pair, WORKERS, LIMITS, MEMBER_LIMITS, verify_checkout, make_team, REVISION
from harness.config import load_config, load_env, source_digest
from harness.execution import ContainerWorkspace
from harness.llm import ChatClient, ModelConfig
from harness.information import CommunicationPolicy
from harness.trace import Trace, read_trace
from harness.accounting import observed_balance, report as cost_report
from benchmarks.cooperbench.snapshot import checked, capture
from benchmarks.cooperbench.isolation import verify_worker, ISOLATION_VERSION

TOOL_OUTPUT_LIMIT = 30_000
SNAPSHOT_OUTPUT_LIMIT = 2_000_000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--task', type=int, required=True)
    parser.add_argument('--features', type=int, nargs=2, required=True)
    parser.add_argument('--containers', nargs=2, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scheduler', choices=['controlled', 'async'], default='async')
    parser.add_argument('--authorized-one-paid-pair', action='store_true', required=True)
    args = parser.parse_args()
    pair = Pair(args.repo, args.task, tuple(args.features))
    dataset = verify_checkout()
    pair.private_inputs(dataset)
    inspected = json.loads(subprocess.check_output(['docker', 'inspect', *args.containers], text=True))
    if len(inspected) != 2 or len({c['Id'] for c in inspected}) != 2:
        raise ValueError('Two distinct containers required')
    if len({c['Image'] for c in inspected}) != 1 or any(c['Mounts'] or c['HostConfig']['NetworkMode'] != 'none' for c in inspected):
        raise ValueError('Require the same image, no host mounts and network=none')
    expected_image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', pair.image], text=True))[0]['Id']
    if any(c['Image'] != expected_image for c in inspected):
        raise ValueError('Worker containers must use the selected official task image')
    workspaces = {role: ContainerWorkspace(c['Id'], '/workspace/repo', output_limit=TOOL_OUTPUT_LIMIT)
                  for role, c in zip(WORKERS, inspected)}
    snapshot_workspaces = {role: ContainerWorkspace(c['Id'], '/workspace/repo', output_limit=SNAPSHOT_OUTPUT_LIMIT)
                           for role, c in zip(WORKERS, inspected)}
    bases = {r: checked(w, 'git rev-parse HEAD') for r, w in workspaces.items()}
    if len(set(bases.values())) != 1 or any(checked(w, 'git status --porcelain') for w in workspaces.values()):
        raise ValueError('Both repositories must start clean at the same base commit')
    isolation = {r: verify_worker(w, bases[r]) for r, w in workspaces.items()}
    config = load_config(ROOT / 'configs/base.yaml')
    cfg = replace(ModelConfig(**config['agent_model']), timeout=120, retries=0)
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = dict(pair=asdict(pair), upstream_revision=REVISION, source=source_digest(),
        scheduler=args.scheduler, limits=LIMITS, member_limits=MEMBER_LIMITS, pricing=config["pricing"], model=asdict(cfg), bases=bases,
        communication_policy=CommunicationPolicy().manifest, submission_contract='immutable-snapshot-v1',
        workspace_isolation=ISOLATION_VERSION, worker_preflight=isolation,
        tool_output_limit=TOOL_OUTPUT_LIMIT, snapshot_output_limit=SNAPSHOT_OUTPUT_LIMIT,
        image_id=inspected[0]['Image'], setting='leader-led-adaptation')
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    load_env()
    client = ChatClient(cfg)
    before = observed_balance(cfg)
    (args.output / "balance-before.json").write_text(json.dumps(before, indent=2))
    try:
        with Trace(args.output / 'trace.jsonl', pair.key) as trace:
            trace.emit('run_start')
            try:
                def snapshot(role, revision, paths):
                    return capture(snapshot_workspaces[role], bases[role], paths)
                team = make_team(pair, dataset, workspaces, client, trace, scheduler=args.scheduler,
                                 submission_hook=snapshot)
                result = team.run_task(pair.request)
                for role in WORKERS:
                    if role in team.evaluation_snapshots:
                        submission = team.evaluation_snapshots[role]
                        (args.output / (role + '.submission.json')).write_text(json.dumps(submission, indent=2))
                        patch = submission['artifact']['patch']
                        (args.output / (role + '.patch')).write_text(patch)
                (args.output / 'result.json').write_text(json.dumps(result, indent=2))
                trace.emit('run_end', status=result['status'])
            except Exception as error:
                result = dict(status='error', failure_class='infrastructure_error', error_type=type(error).__name__,
                              error_kind=getattr(error, 'kind', None))
                (args.output / 'result.json').write_text(json.dumps(result, indent=2))
                trace.emit('run_end', **result)
                raise
    finally:
        client._http.close()
        after = observed_balance(cfg)
        events = read_trace(args.output / 'trace.jsonl')
        costs = cost_report(events, config['pricing'], before, after)
        (args.output / 'accounting.json').write_text(json.dumps(costs, indent=2))


if __name__ == '__main__':
    main()
