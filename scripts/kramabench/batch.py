"""Bounded question-parallel engineering pilot; three independent arms per task."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench.tasks import load_tasks
from benchmarks.kramabench.evaluation import scoring_contract
from benchmarks.kramabench.semantic import adjudicate, judge_contract
from harness.config import source_digest
from harness.llm import ChatClient, ProviderError
from harness.runner import bounded_jobs, write_json
from scripts.kramabench import pilot


def guarded_client(stop):
    class BatchClient(ChatClient):
        def _post(self, body, *, timeout=None):
            if stop.is_set():
                raise ProviderError('batch_stopped', 'Another attempt encountered a fatal key/balance error')
            try:
                return super()._post(body, timeout=timeout)
            except ProviderError as error:
                if error.fatal:
                    stop.set()
                raise
    return BatchClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--task-ids', nargs='+')
    selection.add_argument('--all-tasks', action='store_true', help='All 104 pinned public tasks, not tiny/quick-start duplicates')
    parser.add_argument('--concurrency', type=int, default=12)
    parser.add_argument('--execute-paid', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Write scope/scoring/resource plan without credentials, containers or model calls')
    parser.add_argument('--model-calls', type=int, default=pilot.LIMITS['session_model_calls'])
    parser.add_argument('--tool-calls', type=int, default=pilot.LIMITS['session_tool_calls'])
    parser.add_argument('--judge-model', choices=('deepseek-flash',), help='Explicitly authorize up to 30 one-call semantic judgments after all solvers drain')
    args = parser.parse_args()
    if args.execute_paid == args.dry_run:
        parser.error('Choose exactly one of --dry-run or explicitly authorized --execute-paid')
    if args.model_calls < 2 or args.tool_calls < 1:
        parser.error('Invalid call budgets')
    tasks, provenance = load_tasks(args.upstream)
    grading = scoring_contract(args.upstream)
    if args.all_tasks:
        args.task_ids = [task.id for task in tasks]
    if not 1 <= args.concurrency <= 32 or len(set(args.task_ids)) != len(args.task_ids):
        parser.error('Use 1-32 concurrent questions and unique task IDs')
    by_id = {t.id: t for t in tasks}
    if not set(args.task_ids) <= by_id.keys():
        parser.error('Unknown task ID')
    for task_id in args.task_ids:
        if not (args.upstream / 'data' / by_id[task_id].domain / 'input').is_dir():
            parser.error('Missing prepared domain input: ' + by_id[task_id].domain)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()
    factory = guarded_client(stop)
    summary = dict(status='preflight_only' if args.dry_run else 'running', task_ids=args.task_ids, question_concurrency=args.concurrency,
                   attempts_per_task=3, planned_attempts=3 * len(args.task_ids),
                   authorized_attempts=0 if args.dry_run else 3 * len(args.task_ids), retries=0,
                   paid_judge_calls=0, source_digest=source_digest(), provenance=provenance,
                   model_calls_per_attempt=args.model_calls, tool_calls_per_attempt=args.tool_calls,
                   scoring=grading, thread_limits=pilot.THREAD_ENV,
                   image=args.image, limits=dict(pilot.LIMITS, session_model_calls=args.model_calls,
                                                session_tool_calls=args.tool_calls),
                   tasks=[asdict(by_id[k]) for k in args.task_ids], results={},
                   balance_scope='Concurrent account deltas overlap; do not sum as run costs',
                   cache_order_policy='Single, coordinator, full within each question; questions overlap')
    summary['judge'] = judge_contract(pilot.MODEL) if args.judge_model else None
    active = min(args.concurrency, len(args.task_ids))
    summary['resource_plan'] = dict(active_questions=active, max_precreated_containers=3*active,
        cpu_quota_active_arms=2*active, memory_quota_all_containers_gib=12*active,
        max_simultaneous_model_requests=active*(pilot.LIMITS['max_parallel']+1),
        note='Planning ceilings, not measured utilization or provider rate-limit guarantees')
    write_json(root / 'batch.json', summary)
    if args.dry_run:
        return summary

    def run(task_id):
        try:
            result = pilot.main(['--upstream', str(args.upstream), '--image', args.image,
                '--output', str(root / task_id), '--task-id', task_id, '--mode', 'all', '--execute-paid',
                '--model-calls', str(args.model_calls), '--tool-calls', str(args.tool_calls)],
                client_factory=factory, stop_event=stop)
            return task_id, dict(status=result['status'])
        except Exception as error:
            return task_id, dict(status='launcher_error', error_type=type(error).__name__, error=str(error))

    try:
        for task_id, result in bounded_jobs(args.task_ids, run, args.concurrency,
                                            lambda result: stop.is_set(), stop_event=stop):
            summary['results'][task_id] = result
            write_json(root / 'batch.json', summary)
        for task_id in args.task_ids:
            summary['results'].setdefault(task_id, dict(status='not_run_after_fatal'))
        summary['status'] = ('stopped_after_fatal' if stop.is_set() else 'finished_with_errors'
                             if any(r['status'] != 'attempts_finished' for r in summary['results'].values())
                             else 'attempts_finished')
        if args.judge_model and not stop.is_set():
            summary['solver_status'] = summary['status']
            summary['status'] = 'judging'
            write_json(root / 'batch.json', summary)
            judged = adjudicate(root, args.upstream, pilot.MODEL, pilot.PRICING, stop, client_factory=factory)
            summary['paid_judge_calls'] = judged['attempted_calls']
            summary['judge_status'] = judged['status']
            summary['status'] = (summary['solver_status'] if judged['status'] == 'completed' else
                                 'stopped_after_fatal' if stop.is_set() else 'finished_with_errors')
    except KeyboardInterrupt:
        # bounded_jobs has drained the active questions before propagating here.
        summary['status'] = 'interrupted'
        for task_id in args.task_ids:
            receipt = root / task_id / 'summary.json'
            summary['results'][task_id] = (dict(status=json.loads(receipt.read_text())['status'])
                if receipt.exists() else dict(status='not_run_after_interruption'))
        raise
    except Exception as error:
        summary.update(status='postprocessing_error', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        write_json(root / 'batch.json', summary)


if __name__ == '__main__':
    main()
