"""One explicitly authorized real task, selected arms once each; no paid judge.

Requires --execute-paid. Creates only two disposable task containers from an
already prepared image, and removes those containers (not evidence) at exit.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench.adapter import run_task
from benchmarks.kramabench.evaluation import grade_numeric
from benchmarks.kramabench.roles import (ALL_TOOLS, LEADER_SYSTEM, PROJECT_CONTEXT,
                                        SUBMISSION_SCHEMA, SUBMISSION_INSTRUCTIONS, TEMPLATES)
from benchmarks.kramabench.tasks import load_tasks
from harness.accounting import observed_balance, report as cost_report
from harness.catalog import catalog_manifest
from harness.comparison import validate_pair
from harness.config import ROOT, load_env, source_digest
from harness.container_contract import validate_data_container
from harness.data_tools import inspection_tools
from harness.execution import ContainerWorkspace
from harness.llm import ChatClient, ModelConfig, ProviderError
from harness.runner import write_json
from harness.trace import read_trace

MODEL = ModelConfig(model='deepseek-flash', thinking='enabled', reasoning_effort='high',
                    max_tokens=16384, context_window=1_000_000, retries=0, timeout=180)
LIMITS = dict(session_model_calls=64, session_tool_calls=120, session_seconds=1800, audit_seconds=120,
              max_parallel=4, max_subagents=8, max_delegations=16)
PRICING = {'source': 'https://api-docs.deepseek.com/quick_start/pricing/', 'checked_date': '2026-11-01',
           'models': {'deepseek-flash': {'cache_hit': 0.003, 'cache_miss': 0.15, 'output': 0.60}},
           'peak_hours_utc': [[1, 4], [6, 10]], 'peak_multiplier': 2,
           'note': 'USD per million tokens; weekday peak, Chinese holidays not modeled; receipt estimate, not invoice'}

PROBE = r'''
import errno, json
from pathlib import Path
probe = Path('/workspace/.harness-preflight-probe')
probe.write_text('isolated workspace')
assert probe.read_text() == 'isolated workspace'
probe.unlink()
assert list(Path('/data').iterdir())
data_probe = Path('/data/.harness-preflight-probe')
try:
    data_probe.write_text('must fail')
except OSError as error:
    assert error.errno in (errno.EROFS, errno.EACCES)
else:
    data_probe.unlink()
    raise AssertionError('Dataset is writable')
import numpy, pandas, scipy, openpyxl
print(json.dumps({'workspace_read_write': True, 'dataset_readonly': True, 'analysis_imports': True}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--task-id', default='archeology-hard-1')
    parser.add_argument('--execute-paid', action='store_true')
    parser.add_argument('--mode', choices=('both', 'single', 'mas'), default='both')
    parser.add_argument('--resume-unstarted-from', type=Path,
                        help='Finish only a MAS arm with zero prior requests; never replay single')
    args = parser.parse_args()
    if not args.execute_paid:
        parser.error('Real calls require --execute-paid and run-specific user authorization')
    if args.resume_unstarted_from and args.mode != 'both':
        parser.error('--mode cannot be combined with --resume-unstarted-from')
    if (ROOT / '.env').stat().st_mode & 0o077:
        raise ValueError('.env must be private (0600)')
    tasks, provenance = load_tasks(args.upstream)
    task = next(t for t in tasks if t.id == args.task_id)
    dataset = (args.upstream / 'data' / task.domain / 'input').resolve(strict=True)
    previous = None
    if args.resume_unstarted_from:
        previous_root = args.resume_unstarted_from.resolve(strict=True)
        previous = json.loads((previous_root / 'pair-manifest.json').read_text())
        previous_summary = json.loads((previous_root / 'summary.json').read_text())
        previous_launch = json.loads((previous_root / 'launch.json').read_text())
        if (previous_summary['arms'].get('mas', {}).get('status') != 'preflight_error'
                or (previous_root / 'mas/trace.jsonl').exists()
                or previous_summary['arms'].get('single', {}).get('status') != 'completed'
                or previous_launch['model'] != asdict(MODEL) or previous_launch['limits'] != LIMITS
                or previous_launch['task'] != asdict(task)):
            raise ValueError('Continuation requires the same authorized pair and an entirely unstarted MAS arm')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    load_env()
    # Constructor checks credentials without sending an API request.
    order = ['mas'] if previous else (['single', 'mas'] if args.mode == 'both' else [args.mode])
    clients = {mode: ChatClient(MODEL) for mode in order}
    owned, workspaces, arms = [], {}, {}
    summary = {'task': asdict(task), 'task_count': 1, 'attempts_per_mode': 1,
               'order': order, 'monetary_limit_usd': None, 'retries': 0,
               'paid_judge_calls': 0, 'arms': {}, 'status': 'preparing',
               'cache_order_policy': 'Recorded selected-arm order; not cache-balanced efficacy evidence'}
    if previous:
        summary.update(continued_from=str(previous_root), single_not_rerun=True,
                       comparison_quality='engineering_only_source_revision_changed')
    write_json(root / 'launch.json', dict(summary, model=asdict(MODEL), limits=LIMITS, pricing=PRICING))
    write_json(root / 'summary.json', summary)
    try:
        for mode in ('single', 'mas'):
            work = root / 'workspaces' / mode
            work.mkdir(parents=True)
            subprocess.run(['git', 'init', '--quiet', str(work)], check=True)
            name = 'kramabench-pilot-' + mode + '-' + uuid.uuid4().hex[:10]
            container_id = subprocess.check_output(['docker', 'run', '-d', '--name', name,
                '--label', 'project=mas-information', '--label', 'purpose=kramabench-pilot',
                '--network', 'none', '--cpus', '2', '--memory', '4g', '--pids-limit', '128',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--user', f'{os.getuid()}:{os.getgid()}',
                '--mount', f'type=bind,src={dataset},dst=/data,readonly',
                '--mount', f'type=bind,src={work},dst=/workspace',
                args.image, 'sleep', 'infinity'], text=True).strip()
            owned.append(container_id)
            workspace = ContainerWorkspace(container_id, archive_dir=root / mode / 'retained')
            probe = workspace.execute('python3 -I -c ' + shlex.quote(PROBE))
            if probe['execution_error'] or probe['exit_code'] != 0:
                raise RuntimeError('Container smoke failed: ' + probe['output'])
            audit = workspace.audit_snapshot()
            write_json(root / (mode + '-container-smoke.json'), {'probe': probe, 'audit': audit})
            environment = validate_data_container(workspace, dataset, output=root / mode)
            tools = workspace.tools() + inspection_tools(workspace)
            contract = {'task': asdict(task), 'model': asdict(MODEL), 'tools': catalog_manifest(TEMPLATES, tools),
                'common_prompt': {'leader_system': LEADER_SYSTEM, 'project_context': PROJECT_CONTEXT,
                                 'submission_tool': 'submit', 'submission_schema': SUBMISSION_SCHEMA,
                                 'final_tool_policy': 'submit_only_auto_no_forced_named_tool',
                                 'final_prompt': SUBMISSION_INSTRUCTIONS},
                'budgets': LIMITS, 'pricing': PRICING, 'source_digest': source_digest()}
            arms[mode] = {'contract': contract, 'environment': environment,
                          'output': str(root / mode), 'archive': str(workspace.archive_dir)}
            workspaces[mode] = workspace
        preflight = validate_pair(arms)
        if previous:
            old_contract, new_contract = previous['contract'], preflight['contract']
            if {k: v for k, v in old_contract.items() if k != 'source_digest'} != {
                    k: v for k, v in new_contract.items() if k != 'source_digest'}:
                raise ValueError('Task/model/tool/prompt/budget/pricing changed since the original arm')
            for key in ('image_id', 'dataset_files', 'resources', 'network'):
                if previous['arms']['mas']['environment'][key] != arms['mas']['environment'][key]:
                    raise ValueError('Continuation environment differs: ' + key)
            summary['source_revisions'] = {'original': old_contract['source_digest'],
                                           'continuation': new_contract['source_digest']}
        write_json(root / 'pair-manifest.json', preflight)
        if previous:
            # An unstarted arm may be claimed once; never silently replay it.
            with (previous_root / 'unstarted-mas-claim.json').open('x') as claim:
                json.dump({'continuation': str(root), 'pair_sha256': preflight['sha256']}, claim)
        print('Both real containers and matched pair preflight passed. Starting authorized calls.', flush=True)
        summary['status'] = 'running'
        write_json(root / 'summary.json', summary)
        fatal = False
        for mode in summary['order']:
            if fatal:
                summary['arms'][mode] = {'status': 'not_run_after_fatal'}
                continue
            before = observed_balance(MODEL)
            write_json(root / (mode + '-balance-before.json'), before)
            failure = None
            try:
                run_task(task, client=clients[mode], workspace=workspaces[mode], dataset=dataset,
                    output=root / mode, provenance=provenance, pricing=PRICING, mode=mode,
                    expected_environment=arms[mode]['environment'], comparison_sha256=preflight['sha256'], **LIMITS)
            except Exception as error:
                failure = {'type': type(error).__name__, 'message': str(error)}
                fatal = isinstance(error, ProviderError) and error.fatal
            after = observed_balance(MODEL)
            write_json(root / (mode + '-balance-after.json'), after)
            report_path = root / mode / 'report.json'
            result = json.loads(report_path.read_text()) if report_path.exists() else {'status': 'preflight_error', 'failure': failure}
            if (root / mode / 'trace.jsonl').exists():
                events = read_trace(root / mode / 'trace.jsonl')
                costs = cost_report(events, PRICING, before, after)
                write_json(root / mode / 'cost.json', costs)
            summary['arms'][mode] = result
            write_json(root / 'summary.json', summary)
            print(json.dumps({'mode': mode, 'status': result['status'], 'usage': result.get('usage', {}).get('total'),
                              'estimated_usd': result.get('cost_usd_estimate')}, ensure_ascii=False), flush=True)
        # Reference answers are accessed only after all authorized attempts ended.
        for mode in summary['order']:
            submission = root / mode / 'submission.json'
            if submission.exists():
                grade = grade_numeric(args.upstream, task.id, submission)
                write_json(root / mode / 'grade.json', grade)
                summary['arms'][mode]['numeric_grade'] = grade
            elif summary['arms'].get(mode, {}).get('status') not in {'not_run_after_fatal', 'preflight_error'}:
                summary['arms'][mode]['numeric_grade'] = {'score': 0, 'reason': 'no_valid_submission', 'judge_calls': 0}
        summary['status'] = ('stopped_after_fatal' if fatal else 'incomplete_pair'
                             if any(r['status'] == 'preflight_error' for r in summary['arms'].values()) else 'attempts_finished')
        write_json(root / 'summary.json', summary)
    except Exception as error:
        summary.update(status='error', error_type=type(error).__name__, error=str(error))
        write_json(root / 'summary.json', summary)
        raise
    finally:
        cleanup = []
        for container in owned:
            result = subprocess.run(['docker', 'rm', '-f', container], capture_output=True, text=True)
            cleanup.append({'container_id': container, 'returncode': result.returncode, 'stderr': result.stderr})
        write_json(root / 'container-cleanup.json', cleanup)
        for client in clients.values():
            client._http.close()
    print(json.dumps({'status': summary['status'], 'output': str(root), 'arms': {
        mode: {'status': result['status'], 'score': result.get('numeric_grade', {}).get('score'),
               'cost_usd_estimate': result.get('cost_usd_estimate')}
        for mode, result in summary['arms'].items()}}, indent=2))


if __name__ == '__main__':
    main()
