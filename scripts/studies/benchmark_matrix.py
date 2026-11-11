"""Explicit matched Claude benchmark matrix; independent processes, no retries."""

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common.prompts.conditions import organization_override, backend_instructions, NATIVE_SUBAGENTS_PROMPT, runtime_backend
from common.io import write_json
from benchmarks.dataclawbench.tasks import load_tasks as dc_tasks
from benchmarks.fdabench.tasks import load_tasks as fda_tasks
from benchmarks.hybriddeepresearch.tasks import load_tasks as hdr_tasks
from benchmarks.kramabench.tasks import load_tasks as krama_tasks
from harness.runtime_support import runtime
from scripts.common.grading import grade_attempt, needs_judge
from scripts.studies import finalization
from harness.runtime_support import web_policy
from harness.runtime_support.proof import validate_runtime, validate_effort
from benchmarks._external import digest
from benchmarks.policy import default_timeout, timeout_policy
from common.io import fingerprint
from common.journal import Journal, exclusive
from harness.runtime_support.admission import admit_balance, amount, BalanceWatch, fatal_provider_record, unavailable_web_proxy

BACKENDS = ("claude-code-single-agent", "claude-code-subagents",)
CONDITIONS = (*BACKENDS, "native")
BENCHMARKS = ("dataclawbench", "hybriddeepresearch", "kramabench")
SUPPORTED_BENCHMARKS = BENCHMARKS + ("fdabench",)


def task_fingerprint(benchmark, task):
    public = dict(benchmark=benchmark, id=task.id,
                  question=getattr(task, "question", getattr(task, "query", None)),
                  source_sha256=getattr(task, "source_sha256", None))
    return hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()


def task_pools(root, benchmarks=BENCHMARKS):
    loaders = dict(dataclawbench=lambda:dc_tasks(root/'dataclawbench/upstream'),
        hybriddeepresearch=lambda:hdr_tasks(root/'hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl'),
        kramabench=lambda:krama_tasks(root/'kramabench/upstream')[0],
        fdabench=lambda:fda_tasks(root/'fdabench/release'))
    return {b:loaders[b]() for b in benchmarks}


def manifest_selections(root, manifest, offset, count):
    full = manifest.get('kind')=='benchmark-full-v1'
    validation = manifest.get('kind')=='validation20-v1'
    if (manifest.get("kind") not in {"validation20-v1","benchmark-full-v1","matched-study-v1"} or offset < 0
            or (count is not None and count<1) or (not full and (count is None or offset+count>20))):
        raise ValueError("Invalid validation manifest or task slice")
    names = list(manifest['benchmarks'])
    if not names or set(names)-set(SUPPORTED_BENCHMARKS):
        raise ValueError('Unknown or empty manifest benchmarks')
    pools = task_pools(root,names)
    result = []
    for benchmark in names:
        frozen = manifest["benchmarks"][benchmark]
        ids = [row["task_id"] for row in frozen]
        if not ids or len(set(ids))!=len(ids) or (validation and len(ids)!=20):
            raise ValueError("Each validation benchmark must contain 20 unique IDs")
        if offset>=len(ids) or (count is not None and offset+count>len(ids)):
            raise ValueError('Manifest slice exceeds task count')
        by_id = {t.id: t for t in pools[benchmark]}
        if full and (len(by_id)!=len(pools[benchmark]) or set(ids)!=set(by_id)):
            raise ValueError('Full manifest must cover every current task exactly once')
        if full and ids!=[t.id for t in pools[benchmark]]:
            raise ValueError('Full manifest must preserve upstream task order')
        for row in frozen:
            task = by_id.get(row["task_id"])
            if task is None or task_fingerprint(benchmark, task) != row["task_sha256"]:
                raise ValueError("Frozen validation task changed or disappeared")
        result.extend((benchmark, by_id[i]) for i in ids[offset:None if count is None else offset + count])
    return result


def balanced_sample(tasks, count, group, seed):
    """Round-robin public strata with stable seeded ordering, never inspect gold."""
    groups = {}
    for task in tasks:
        groups.setdefault(group(task), []).append(task)
    if len(tasks) < count:
        raise ValueError("Not enough tasks for the requested sample")
    def rank(value):
        return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()
    names = sorted(groups, key=rank)
    for values in groups.values():
        values.sort(key=lambda task: rank(task.id))
    selected = []
    while len(selected) < count:
        for name in names:
            if groups[name] and len(selected) < count:
                selected.append(groups[name].pop(0))
    return selected


def selections(root, count=2, seed=42, benchmarks=BENCHMARKS):
    pools = task_pools(root, benchmarks)
    return [(bench, task) for bench, tasks in pools.items()
            for task in balanced_sample(tasks, count,
                (lambda t: t.domain) if bench == 'kramabench' else (lambda t: t.category), seed)]


def solver_dispatch_status(folder):
    """Only host gateway write-ahead records establish possible upstream dispatch."""
    ledger = folder / 'gateway-requests.jsonl'
    if not ledger.exists():
        return 'not_started'
    try:
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        if any(not isinstance(row, dict) for row in records):
            return 'dispatch_unknown'
        return 'dispatch_unknown' if any(row.get('upstream_attempted') is True for row in records) else 'not_started'
    except (OSError, ValueError):
        return 'dispatch_unknown'


def cleanup_owned_containers(path):
    for receipt in path.glob('**/container-ownership.json'):
        owned=json.loads(receipt.read_text())
        name=owned.get('container_name','')
        if name.startswith('mas-cli6-'):
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)


def reconcile_solver_status(status, folder):
    if status not in {'cli_exited','native_condition_unverified','not_started'}:
        if solver_dispatch_status(folder)=='not_started':
            return 'not_started'
    return status


def grade_binding(benchmark, task, backend, run, source):
    actual=runtime_backend(backend)
    submission=run/task.id/actual/'submission.json' if benchmark=='kramabench' else run/'predictions.jsonl'
    return fingerprint(dict(submission=digest(submission) if submission.exists() else None,
        source=source,task=task_fingerprint(benchmark,task),backend=backend,
        summary=digest(run/'summary.json') if (run/'summary.json').exists() else None))


def batch_chain(path):
    seen = set()
    while path:
        path = Path(path).resolve()
        if path in seen:
            raise ValueError('Resume provenance cycle')
        seen.add(path)
        auth_path = path / 'authorization.json'
        auth = (json.loads(auth_path.read_text()) if auth_path.exists()
                else json.loads((path / 'summary.json').read_text())['authorization'])
        yield path, auth
        path = auth.get('retained_from')


def retained_attempts(path, jobs, settings, manifest_sha, _seen=None, *, allow_grading_recovery=False):
    if path is None:
        return {}
    seen=set() if _seen is None else set(_seen)
    if path.resolve() in seen:
        raise ValueError('Resume provenance cycle')
    seen.add(path.resolve())
    summary_path=path/'summary.json'
    previous=json.loads(summary_path.read_text()) if summary_path.exists() else dict(
        authorization=json.loads((path/'authorization.json').read_text()),interrupted=True)
    authorization=previous['authorization']
    if ((not previous.get('interrupted') and not allow_grading_recovery)
            or authorization['protocol_settings']!=settings or authorization['task_manifest_sha256']!=manifest_sha):
        raise ValueError('Only a sealed interrupted batch with identical task/settings scope may continue')
    key=lambda r:(r['benchmark'],r['task_id'],r['backend'])
    expected={(b,t.id,k) for b,t,k,_ in jobs}
    if (path/'journal.sqlite').exists():
        with exclusive(path/'controller.lock'):
            assert_quiescent(path)
            if authorization.get('source_manifest') != runtime.source_manifest():
                raise ValueError('Resume source changed; retain the frozen source stage')
            journal=Journal(path/'journal.sqlite')
            inherited=retained_attempts(Path(authorization['retained_from']),jobs,settings,manifest_sha,seen,
                allow_grading_recovery=allow_grading_recovery) if authorization.get('retained_from') else {}
            rows=[]
            for b,t,k,out in jobs:
                entry=journal.get('solver',(b,t.id,k))
                if entry is None:
                    rows.append(inherited.get((b,t.id,k),dict(benchmark=b,task_id=t.id,backend=k,status='not_started',run=str(out))))
                    continue
                row=dict(entry['body'])
                if entry['state']!='complete':
                    report=Path(row['run'])/t.id/runtime_backend(k)/'report.json'
                    record=json.loads(report.read_text()) if report.exists() else {}
                    row['status']=record.get('status') if record.get('status') not in {None,'running'} else solver_dispatch_status(report.parent)
                row['status']=reconcile_solver_status(row['status'],Path(row['run'])/t.id/runtime_backend(k))
                rows.append(row)
    else:
        raise ValueError('Continuation requires a durable journal; old evidence remains read-only')
    if len(rows)!=len(expected) or {key(r) for r in rows}!=expected:
        raise ValueError('Retained batch question/condition scope differs')
    if any(r['status']=='running' for r in rows):
        raise ValueError('Cannot continue a live batch')
    retained={key(r):r for r in rows if r['status']!='not_started'}
    roots=[(path/'solvers').resolve()]
    ancestor=authorization.get('retained_from')
    visited={path.resolve()}
    while ancestor:
        parent=Path(ancestor).resolve()
        if parent in visited:
            raise ValueError('Resume provenance cycle')
        visited.add(parent)
        roots.append((parent/'solvers').resolve())
        parent_auth=json.loads((parent/'authorization.json').read_text())
        ancestor=parent_auth.get('retained_from')
    for r in retained.values():
        if not any(Path(r['run']).resolve().is_relative_to(root) for root in roots):
            raise ValueError('Retained artifact lies outside its original batch')
    return retained


def assert_quiescent(path):
    for proc in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            argv=proc.read_bytes().decode().split('\0')
            for flag in ('--output','--run'):
                if flag not in argv:
                    continue
                output=Path(argv[argv.index(flag)+1]).resolve()
                if output.is_relative_to(path.resolve()):
                    raise ValueError('A prior solver/grader process is still live')
        except (OSError,UnicodeError,IndexError):
            continue
    for receipt in path.glob('solvers/**/container-ownership.json'):
        name=json.loads(receipt.read_text()).get('container_name','')
        if not name.startswith('mas-cli6-'):
            raise ValueError('Invalid owned container receipt')
        listed=subprocess.run(['docker','ps','-aq','--filter','name=^/'+re.escape(name)+'$'],
                              capture_output=True,text=True,timeout=15)
        if listed.returncode:
            raise ValueError('Cannot verify prior container quiescence')
        if not listed.stdout.strip():
            continue
        result=subprocess.run(['docker','inspect','--format','{{.State.Running}}',name],capture_output=True,text=True,timeout=15)
        if result.returncode or result.stdout.strip() not in {'true','false'}:
            raise ValueError('Cannot verify prior container quiescence')
        if result.stdout.strip()=='true':
            raise ValueError('Owned container is still running; reconcile it before resuming')


def prior_grade(path, identity):
    seen=set()
    while path:
        path=Path(path)
        if path.resolve() in seen:
            raise ValueError('Resume provenance cycle')
        seen.add(path.resolve())
        if (path/'journal.sqlite').exists():
            entry=Journal(path/'journal.sqlite').get('grade',identity)
            if entry and entry['body'].get('status') != 'not_started':return entry
        path=json.loads((path/'authorization.json').read_text()).get('retained_from')
    return None


def judge_recovery_evidence(entry):
    body=entry['body']
    if (entry['state']!='complete' or body.get('judge_recovery')
            or body.get('status') not in {'grading_failed','judge_error'}
            or body.get('original_judge_calls',body.get('judge_calls'))!=1):
        return None
    target=Path(body['grading_artifact'])
    path=target/'result.json'
    if path.exists():
        records=[json.loads(path.read_text())]
    else:
        path=target/'judge-results.jsonl'
        if not path.exists():return None
        records=[json.loads(line) for line in path.read_text().splitlines()]
    if len(records)!=1:return None
    record=records[0]
    status=record.get('http_status')
    if record.get('status')!='judge_error' or type(status) is not int or not 500<=status<600:
        return None
    return dict(original_artifact=str(target),receipt_sha256=digest(path),http_status=status)


def upstream_recovery(path, jobs, settings, manifest_sha):
    """Select only terminal CLI failures whose last model response is upstream 5xx."""
    if path is None:
        return {}
    previous = json.loads((path / 'summary.json').read_text())
    auth = previous['authorization']
    if (previous.get('interrupted') or auth.get('upstream_recovery_from')
            or auth['protocol_settings'] != settings or auth['task_manifest_sha256'] != manifest_sha):
        raise ValueError('Upstream recovery requires a sealed original batch with identical tasks/settings')
    claim = Path(str(path) + '.upstream-recovery-claim.json')
    if claim.exists():
        raise ValueError('Upstream recovery has already been claimed; no repeated recovery')
    key = lambda row: (row['benchmark'], row['task_id'], row['backend'])
    expected = {(b, t.id, k) for b, t, k, _ in jobs}
    rows = previous['rows']
    if len(rows) != len(expected) or {key(row) for row in rows} != expected:
        raise ValueError('Original question/condition scope differs')
    if any(row['status'] in {'running', 'not_started'} for row in rows):
        raise ValueError('Original batch has unfinished attempts')
    eligible = {}
    chain = list(batch_chain(path))
    for parent, parent_auth in chain:
        if (parent_auth.get('protocol_settings') != settings
                or parent_auth.get('task_manifest_sha256') != manifest_sha
                or parent_auth.get('upstream_recovery_from')
                or Path(str(parent)+'.upstream-recovery-claim.json').exists()):
            raise ValueError('Changed or already recovered ancestor scope')
    for row in rows:
        if row['status'] != 'cli_error':
            continue
        output = Path(row['run']).resolve()
        if not any(output.is_relative_to(parent / 'solvers') for parent, _ in chain):
            raise ValueError('Original attempt lies outside its batch')
        actual = runtime_backend(row['backend'])
        folder = output / row['task_id'] / actual
        report_path, ledger_path = folder / 'report.json', folder / 'gateway-requests.jsonl'
        report = json.loads(report_path.read_text())
        if report.get('status') != 'cli_error' or not report.get('cli', {}).get('returncode'):
            continue
        requests = [r for line in ledger_path.read_text().splitlines() for r in [json.loads(line)]
                    if r.get('event') == 'finished' and r.get('upstream_attempted') is True
                    and r.get('route') == '/anthropic/v1/messages']
        last = requests[-1] if requests else {}
        status = last.get('http_status')
        if type(status) is int and 500 <= status < 600 and last.get('outcome') == 'upstream_rejected':
            eligible[key(row)] = dict(benchmark=row['benchmark'], task_id=row['task_id'], backend=row['backend'],
                original_run=str(output), http_status=status, report_sha256=digest(report_path),
                ledger_sha256=digest(ledger_path), policy='one explicitly authorized upstream-5xx recovery')
    return eligible


def solver_command(args, benchmark, task, backend, output, *, execute=False):
    condition=backend
    backend=runtime_backend(condition)
    if condition == "native" and benchmark != "kramabench":
        raise ValueError("The Native study is currently scoped to KramaBench")
    command = [sys.executable, "-m", "scripts." + benchmark + ".run", "--upstream", str(args.root / benchmark / "upstream"),
               "--backend", backend, "--task-id", task.id, "--image", args.image, "--output", str(output),
               "--credentials", str(args.credentials), "--timeout", str(default_timeout(benchmark)),
               "--offline-proof", str(args.proofs / backend / "proof.json")]
    if condition == "native":
        command += ["--subagents-prompt", "native"]
    command += ["--effort", getattr(args, "effort", runtime.DEFAULT_EFFORT)]
    if backend == "claude-code-subagents" and getattr(args, "organization_prompt", None):
        command += ["--organization-prompt", str(args.organization_prompt)]
    if benchmark == "kramabench":
        if hasattr(args,'output'):command+=['--asset-cache',str(args.output/'asset-digests.sqlite')]
        command += ["--concurrency", "1", "--replay-timeout", "180", "--judge-limit", "0"]
        command += ['--cpus', str(getattr(args,'cpus',runtime.DEFAULT_CPUS))]
        if getattr(args, 'record_resources', False):
            command += ['--record-resources']
        command += ['--compute-threads', str(getattr(args,'compute_threads',runtime.DEFAULT_COMPUTE_THREADS))]
        for module in runtime.capability_modules(getattr(args, 'require_module', [])):
            command += ['--require-module', module]
        for probe in runtime.capability_probes(getattr(args, 'capability_probe', [])):
            command += ['--capability-probe', probe['path']]
        if execute:
            command.append("--from-plan")
            command.append('--matrix-balance-managed')
    else:
        command += ['--asset-cache',str(args.output/'asset-digests.sqlite')] if hasattr(args,'output') else []
        command += ['--from-plan'] if execute else ['--preflight']
        command += ['--cpus',str(getattr(args,'cpus',runtime.DEFAULT_CPUS)),
                    '--compute-threads',str(getattr(args,'compute_threads',runtime.DEFAULT_COMPUTE_THREADS))]
        for module in runtime.capability_modules(getattr(args,'require_module',[])):
            command += ['--require-module',module]
        for probe in runtime.capability_probes(getattr(args,'capability_probe',[])):
            command += ['--capability-probe',probe['path']]
        if getattr(args,'record_resources',False):
            command += ['--record-resources']
        data = args.root / ("dataclawbench/upstream/assets/database" if benchmark == "dataclawbench" else "hybriddeepresearch/data")
        command += ["--data", str(data), "--authorized-attempts", "1"]
        if getattr(task, "web", benchmark == "hybriddeepresearch"):
            command += ["--web-search", "deepseek", "--max-web-requests", str(getattr(args,'max_web_requests',web_policy.DEFAULT_WEB_LIMIT))]
        if benchmark == "hybriddeepresearch":
            command += ["--tasks", str(args.root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"),
                        ]
        if benchmark == "fdabench":
            command[command.index("--data") + 1] = str(args.root / "fdabench/data")
            command += ["--tasks", str(args.root / "fdabench/release")]
    if execute:
        command.append("--execute")
    return command


def protocol_settings(args):
    backends = getattr(args, "backends", BACKENDS)
    override = organization_override(getattr(args, "organization_prompt", None), "claude-code-subagents")
    prompts = {k: NATIVE_SUBAGENTS_PROMPT if k == "native" else backend_instructions(k) for k in backends}
    if override and "claude-code-subagents" in prompts:
        prompts["claude-code-subagents"] = override["text"]
    settings = dict(effort=args.effort,
                inference_policy=runtime.inference_configuration(args.effort),
                deterministic_environment=dict(runtime.REPRODUCIBLE_ENV),
                web_policy=web_policy.configuration(getattr(args,'max_web_requests',web_policy.DEFAULT_WEB_LIMIT)),
                organization_sha256={k: hashlib.sha256(text.encode()).hexdigest() for k, text in prompts.items()},
                timeout_seconds_by_benchmark={b: default_timeout(b) for b in (
                    SUPPORTED_BENCHMARKS if 'fdabench' in getattr(args, 'benchmarks', ()) else BENCHMARKS)},
                solver_concurrency=args.concurrency, judge_concurrency=args.judge_concurrency)
    settings.update(cpu_per_attempt=getattr(args,'cpus',runtime.DEFAULT_CPUS),
                    compute_threads=getattr(args,'compute_threads',runtime.DEFAULT_COMPUTE_THREADS),
                    record_resources=getattr(args,'record_resources',False))
    if getattr(args, 'require_module', []):
        settings['required_modules'] = runtime.capability_modules(args.require_module)
    if getattr(args, 'capability_probe', []):
        settings['capability_probes'] = runtime.capability_probes(args.capability_probe)
    return settings


def sql_evaluator_preflight(root):
    script = root / 'hybriddeepresearch/upstream/evaluation/s2sql_eval.py'
    try:
        subprocess.run([sys.executable, str(script), '--help'], check=True,
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('HDR SQL evaluator preflight failed; use the documented evaluation Python') from error
    return dict(python=sys.executable, script=str(script), cli_imports_verified=True, paid_calls=0)


def runtime_preflight(args):
    """Check every condition before creating a run namespace or dispatching children."""
    evaluator = sql_evaluator_preflight(args.root) if getattr(args, 'sql_grading_required', False) else None
    available=None
    host_cpus=os.cpu_count()
    if host_cpus and getattr(args,'concurrency',8)*getattr(args,'cpus',runtime.DEFAULT_CPUS)>host_cpus:
        raise ValueError('Configured solver CPU reservations exceed host capacity')
    if Path('/proc/meminfo').exists():
        memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        available=int(memory['MemAvailable'].split()[0])*1024
        if getattr(args,'concurrency',8)*8*1024**3 > available*.9:
            raise ValueError('Configured solver concurrency exceeds conservative available-memory admission')
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.image],
                                              text=True, timeout=30))[0]['Id']
    binary = digest(runtime.CLAUDE)
    proofs = {}
    for condition in args.backends:
        path = args.proofs / runtime_backend(condition) / 'proof.json'
        raw = path.read_bytes()
        proof = json.loads(raw)
        validate_runtime(proof, runtime_backend(condition), image_id=image, binary_sha256=binary)
        validate_effort(proof, args.effort)
        proofs[condition] = dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                                 requested_effort=args.effort, request_effort_verified=True)
    proxy=None
    if getattr(args,'web_required',False):
        from harness.runtime_support.web_fetch import check_ready
        proxy=check_ready()
    return dict(image_id=image, binary_sha256=binary, proofs=proofs, paid_calls=0,web_readiness=proxy,
                sql_evaluator=evaluator,
                capacity=dict(host_cpus=os.cpu_count(),available_memory_bytes=available,
                              memory_per_solver_bytes=8*1024**3),
                scope='Image/binary/effort/tool proofs only; task/container preflights still required')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument('--benchmarks', nargs='+', choices=SUPPORTED_BENCHMARKS, default=BENCHMARKS,
                        help='Explicit benchmark scope; defaults to all three benchmarks')
    parser.add_argument("--credentials", type=Path, default=Path("/home/zhoujunye/mas/.env"))
    parser.add_argument("--concurrency", type=int, default=8, choices=range(1, 257))
    parser.add_argument('--cpus', type=int, choices=range(1, 129), default=runtime.DEFAULT_CPUS)
    parser.add_argument('--record-resources', action='store_true')
    parser.add_argument('--max-web-requests',type=int,choices=range(1,101),default=web_policy.DEFAULT_WEB_LIMIT)
    parser.add_argument('--compute-threads', type=int, choices=range(1, 129), default=runtime.DEFAULT_COMPUTE_THREADS)
    parser.add_argument('--require-module', action='append', default=[])
    parser.add_argument('--capability-probe', action='append', default=[])
    parser.add_argument("--effort", choices=runtime.EFFORTS, default=runtime.DEFAULT_EFFORT,
                        help="none disables thinking and fixes temperature=0; high/max explicitly enable thinking")
    parser.add_argument("--organization-prompt", type=Path)
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=BACKENDS,
                        help="Explicit conditions to run; defaults to the matched Single/Subagents pair")
    parser.add_argument('--conditions', nargs='+', choices=CONDITIONS,
                        help='Explicit Single/Structured and opt-in Krama Native study conditions')
    parser.add_argument('--retain-started-from',type=Path,help='Never rerun started attempts; dispatch only previously not_started slots')
    parser.add_argument('--recover-upstream-from', type=Path,
                        help='Explicitly authorized one-time recovery of terminal upstream-5xx failures')
    parser.add_argument('--recover-judge-5xx',action='store_true',
                        help='With continuation and explicit judge authorization, replace confirmed judge 5xx once')
    parser.add_argument("--tasks-per-benchmark", type=int, default=2)
    parser.add_argument('--all-tasks',action='store_true',help='Use every task in a frozen full manifest')
    parser.add_argument('--estimated-cost',help='Explicit estimated remaining total solver+grading cost; required for execution')
    parser.add_argument('--budget-currency',choices=('CNY','USD'),default='CNY')
    parser.add_argument('--budget-safety-factor',default='1.5')
    parser.add_argument('--balance-reserve',default='1')
    parser.add_argument("--sample-seed", type=int, default=42)
    parser.add_argument("--task-manifest", type=Path, help="Frozen public ID/hash manifest, never questions or gold")
    parser.add_argument("--protocol-settings", type=Path, help="Explicit settings for an authorized rerun of the unchanged frozen tasks")
    parser.add_argument("--task-offset", type=int, default=0)
    parser.add_argument("--judge-concurrency", type=int, default=2, choices=range(1, 65))
    parser.add_argument("--authorized-attempts", type=int)
    parser.add_argument("--authorized-judges", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument('--check-runtime', action='store_true',
                        help='Verify image, CLI and all condition proofs during planning; never dispatch paid calls')
    args = parser.parse_args(argv)
    if args.recover_judge_5xx and not args.retain_started_from:
        raise ValueError('Judge recovery requires continuation and explicit judge authorization at execution')
    if args.tasks_per_benchmark<1:
        raise ValueError('Task count must be positive')
    args.require_module = runtime.capability_modules(args.require_module)
    if len(set(args.benchmarks)) != len(args.benchmarks):
        raise ValueError('Select unique benchmarks')
    if args.recover_upstream_from and (args.retain_started_from or not args.task_manifest):
        raise ValueError('Upstream recovery requires a frozen manifest and cannot retain/resume attempts')
    if args.recover_upstream_from:
        args.recover_upstream_from = args.recover_upstream_from.resolve()
    if args.compute_threads > args.cpus:
        raise ValueError('Compute threads cannot exceed the container CPU quota')
    if args.conditions:
        if args.organization_prompt or args.backends != BACKENDS:
            raise ValueError('Explicit conditions cannot be combined with backend or prompt overrides')
        args.backends = args.conditions
    if "native" in args.backends and args.benchmarks != ["kramabench"]:
        raise ValueError("The Native study is currently scoped to KramaBench")
    args.root, args.output, args.proofs = args.root.resolve(), args.output.resolve(), args.proofs.resolve()
    if args.retain_started_from:
        args.retain_started_from=args.retain_started_from.resolve()
        if args.output.is_relative_to(args.retain_started_from) or args.retain_started_from.is_relative_to(args.output):
            raise ValueError('Continuation output must not overlap original evidence')
    if args.recover_upstream_from and (args.output.is_relative_to(args.recover_upstream_from)
            or args.recover_upstream_from.is_relative_to(args.output)):
        raise ValueError('Recovery output must not overlap original evidence')
    manifest = json.loads(args.task_manifest.read_text()) if args.task_manifest else None
    if manifest and set(args.benchmarks)-set(manifest.get('benchmarks',{})):
        raise ValueError('Selected benchmark absent from frozen manifest')
    if args.all_tasks and (not manifest or manifest.get('kind')!='benchmark-full-v1' or args.task_offset):
        raise ValueError('--all-tasks requires a frozen full manifest and zero offset')
    explicit_protocol = json.loads(args.protocol_settings.read_text()) if args.protocol_settings else None
    if len(set(args.backends)) != len(args.backends):
        raise ValueError("Select unique backends")
    if args.organization_prompt and "claude-code-subagents" not in args.backends:
        raise ValueError("Organization overrides require the Subagents condition")
    if args.protocol_settings and manifest is None:
        raise ValueError("Explicit protocol settings require a frozen task manifest")
    observed_settings = protocol_settings(args)
    if args.protocol_settings and explicit_protocol != observed_settings:
        raise ValueError("Runtime settings differ from the explicit protocol settings")
    if args.task_offset and manifest is None:
        raise ValueError("A task offset requires a frozen task manifest")
    selected = (manifest_selections(args.root, manifest, args.task_offset, None if args.all_tasks else args.tasks_per_benchmark)
                if manifest else selections(args.root, args.tasks_per_benchmark, args.sample_seed, args.benchmarks))
    selected = [(bench, task) for bench, task in selected if bench in args.benchmarks]
    args.web_required=any(getattr(t,'web',b=='hybriddeepresearch') for b,t in selected)
    args.sql_grading_required=any(b=='hybriddeepresearch' and t.category=='search_to_sql' for b,t in selected)
    jobs = [(bench, task, backend, args.output / "solvers" / bench / task.id / backend)
            for bench, task in selected for backend in args.backends]
    recovery = upstream_recovery(args.recover_upstream_from, jobs, observed_settings,
                                 digest(args.task_manifest) if args.task_manifest else None)
    if args.recover_upstream_from:
        jobs = [(b, t, k, out) for b, t, k, out in jobs if (b, t.id, k) in recovery]
    retained=retained_attempts(args.retain_started_from,jobs,observed_settings,digest(args.task_manifest) if args.task_manifest else None,
                               allow_grading_recovery=args.recover_judge_5xx)
    if args.recover_judge_5xx and len(retained)!=len(jobs):
        raise ValueError('Judge-only recovery cannot dispatch new solvers')
    jobs=[(b,t,k,Path(retained[(b,t.id,k)]['run']) if (b,t.id,k) in retained else out) for b,t,k,out in jobs]
    frozen_source=runtime.source_manifest()
    judge_recoveries={}
    if args.recover_judge_5xx:
        for b,t,k,out in jobs:
            entry=prior_grade(args.retain_started_from,(b,t.id,k))
            candidate=judge_recovery_evidence(entry) if entry else None
            if candidate:
                if entry['binding']!=grade_binding(b,t,k,out,frozen_source):
                    raise ValueError('Retained grade artifact or evaluator binding changed')
                judge_recoveries[(b,t.id,k)]=dict(benchmark=b,task_id=t.id,backend=k,**candidate)
    maximum_judges = sum(1 for b, t, _, _ in jobs
                         if (b != 'fdabench' or t.category == 'report')
                         and (b != "hybriddeepresearch" or t.category != "search_to_sql"))
    if args.recover_judge_5xx:
        maximum_judges=len(judge_recoveries)
    authorization = dict(attempts=len(jobs), maximum_judge_calls=maximum_judges, retries=0, effort=args.effort,
        recover_judge_5xx=args.recover_judge_5xx,
        judge_recovery=list(judge_recoveries.values()),
        benchmarks=list(args.benchmarks),
        upstream_recovery_from=str(args.recover_upstream_from) if args.recover_upstream_from else None,
        upstream_recovery=list(recovery.values()),
        retained_started_attempts=len(retained),new_solver_attempts=len(jobs)-len(retained),
        retained_from=str(args.retain_started_from) if args.retain_started_from else None,
        tasks_per_benchmark=args.tasks_per_benchmark, sample_seed=args.sample_seed,
        selection_policy="authorized-upstream-5xx-recovery" if args.recover_upstream_from else "frozen-validation-manifest" if manifest else "seeded-public-strata-round-robin",
        task_offset=args.task_offset,
        order_policy='manifest-order-unchanged' if manifest else 'seeded-public-strata-round-robin',
        source_manifest=frozen_source,
        memory_per_attempt='8g',
        budget_policy=dict(estimated_cost=args.estimated_cost,currency=args.budget_currency,
                           safety_factor=args.budget_safety_factor,reserve=args.balance_reserve),
        task_manifest_sha256=digest(args.task_manifest) if args.task_manifest else None,
        protocol_settings=observed_settings,
        protocol_settings_source="explicit-protocol" if args.protocol_settings else "frozen-manifest" if manifest else "current-runtime",
        protocol_settings_sha256=digest(args.protocol_settings) if args.protocol_settings else None,
        organization_override=organization_override(args.organization_prompt, "claude-code-subagents"),
        timeout_seconds_by_benchmark=observed_settings['timeout_seconds_by_benchmark'],
        timeout_policy_by_benchmark={b: timeout_policy(b) for b in observed_settings['timeout_seconds_by_benchmark']},
        solver_concurrency=args.concurrency, judge_concurrency=args.judge_concurrency,
        monetary_cap=None, selections=[dict(benchmark=b, task_id=t.id, backend=k) for b, t, k, _ in jobs])
    if args.execute:
        expected_attempts = len(jobs) if args.recover_upstream_from or args.all_tasks else len(args.benchmarks) * len(args.backends) * args.tasks_per_benchmark
        required_solvers=0 if args.recover_judge_5xx else len(jobs)
        judge_counts=(maximum_judges,) if args.recover_judge_5xx else (0,maximum_judges)
        if not jobs or len(jobs) != expected_attempts or args.authorized_attempts != required_solvers or args.authorized_judges not in judge_counts:
            raise ValueError(f"Require exactly {required_solvers} authorized solvers and judge count in {judge_counts}")
        if manifest:
            expected = explicit_protocol if args.protocol_settings else manifest['baseline_settings']
            if expected != observed_settings or (args.organization_prompt and not args.protocol_settings):
                raise ValueError('Baseline settings differ from the frozen validation study')
        if args.estimated_cost is None or amount(args.estimated_cost)<=0:
            raise ValueError('Execution requires an explicit positive --estimated-cost for the remaining scope')
    if amount(args.budget_safety_factor)<1:
        raise ValueError('Budget safety factor must be >= 1')
    amount(args.balance_reserve)
    readiness = runtime_preflight(args) if args.execute or args.check_runtime else None
    if readiness is not None:
        authorization['runtime_preflight'] = readiness
    if not args.execute:
        print(json.dumps(authorization, indent=2))
        return 0
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    ownership=exclusive(args.output/'controller.lock')
    ownership.__enter__()
    journal=Journal(args.output/'journal.sqlite')
    write_json(args.output / "authorization.json", {**authorization, "authorized_judges": args.authorized_judges})
    if manifest:
        write_json(args.output / "task-manifest.json", manifest)
    if args.protocol_settings:
        write_json(args.output / "protocol-settings.json", explicit_protocol)
    if authorization["organization_override"]:
        # Pin the validated text so every child reads the same lead instructions.
        args.organization_prompt = args.output / "organization-prompt.txt"
        args.organization_prompt.write_text(authorization["organization_override"]["text"], encoding="utf-8")
    args.image = readiness['image_id']
    active, lock, stop = set(), threading.RLock(), threading.Event()
    paused=threading.Event()
    operator_stop=threading.Event()
    monitor_done=threading.Event()
    budget_watch=None

    def pause_budget(error):
        with lock:
            if not paused.is_set():
                paused.set()
                write_json(args.output/'balance-paused.json',dict(reason=str(error),observed_at=runtime.now()))

    def command_run(command, log):
        paid='--execute' in command or '--execute-judges' in command
        free_grade=not paid and any(value.endswith('.score') for value in command)
        if operator_stop.is_set() or (stop.is_set() and not free_grade) or (paid and paused.is_set()):
            return None
        if paid and budget_watch is not None:
            try:
                budget_watch.check()
            except ValueError as error:
                pause_budget(error)
                return None
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.with_suffix(".stdout.log").open("x") as stdout, log.with_suffix(".stderr.log").open("x") as stderr:
            # Never inherit credential-like host variables into CLI subprocesses.
            env = {name: os.environ[name] for name in ("PATH", "HOME", "LANG") if name in os.environ}
            with lock:
                if operator_stop.is_set() or (stop.is_set() and not free_grade) or (paid and paused.is_set()):
                    return None
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env)
                active.add(process)
            try:
                timed_out=False
                timeout = (float(command[command.index('--timeout')+1]) if '--timeout' in command else 3600)
                deadline = time.monotonic() + timeout + 600
                while True:
                    try:
                        return process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        if not operator_stop.is_set() and (not stop.is_set() or free_grade) and time.monotonic() < deadline:
                            continue
                        if not stop.is_set():
                            timed_out=True
                            pause_budget('Child deadline exceeded; pause new dispatch, preserve other in-flight work')
                        process.terminate()
                        try:
                            return process.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            return process.wait(timeout=10)
            finally:
                with lock:
                    active.discard(process)
                if timed_out and '--output' in command:
                    cleanup_owned_containers(Path(command[command.index('--output')+1]))

    def interrupt(signum, frame):
        if signum is not None:
            operator_stop.set()
        stop.set()
        with lock:
            for process in active:
                process.terminate()

    previous = {s: signal.signal(s, interrupt) for s in (signal.SIGTERM, signal.SIGINT)}
    def checked(function, *values):
        try:
            return function(*values)
        except BaseException:
            interrupt(None, None)
            raise
    rows = []
    before = after = None
    def provider_watch():
        observed={}
        ledgers=[out/t.id/runtime_backend(k)/'gateway-requests.jsonl' for b,t,k,out in jobs
                 if (b,t.id,k) not in retained]
        while not monitor_done.wait(1):
            try:
                if budget_watch is not None and not paused.is_set():
                    try:
                        budget_watch.check()
                    except ValueError as error:
                        pause_budget(error)
                for path in ledgers:
                    try:
                        stat=path.stat()
                    except FileNotFoundError:
                        continue
                    version=(stat.st_mtime_ns,stat.st_size)
                    if observed.get(path)==version:
                        continue
                    observed[path]=version
                    fatal=fatal_provider_record(path)
                    if fatal:
                        write_json(args.output/'fatal-provider-error.json',fatal)
                        interrupt(None,None)
                        return
                    if unavailable_web_proxy(path):
                        pause_budget('Local Clash web tunnel unavailable; no new paid dispatch')
            except Exception as error:
                write_json(args.output/'monitor-error.json',dict(error_type=type(error).__name__))
                pause_budget('Provider monitor failed; preserve in-flight work')
    watcher=threading.Thread(target=provider_watch,daemon=True)
    watcher.start()
    try:
        # All offline preflights must pass before any paid attempt starts.
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(checked, command_run, solver_command(args, b, t, k, out),
                                   args.output / "logs" / (b + "-" + t.id + "-" + k + "-preflight")) for b, t, k, out in jobs if (b,t.id,k) not in retained]
            if any(f.result() != 0 for f in futures):
                raise RuntimeError("Matrix preflight failed; no paid attempts dispatched")
        if args.recover_upstream_from:
            claim = Path(str(args.recover_upstream_from) + '.upstream-recovery-claim.json')
            with claim.open('x', encoding='utf-8') as stream:
                json.dump(dict(output=str(args.output), attempts=list(recovery.values()),
                               claimed_at=runtime.now()), stream, indent=2)
        key = runtime.credential(args.credentials)
        before = runtime.safe_balance(key, args.output, "balance-before")
        if before is None or not before.get("response", {}).get("is_available"):
            raise RuntimeError("Balance preflight failed; no paid attempts dispatched")
        admission=admit_balance(before,args.budget_currency,args.estimated_cost,
                                args.budget_safety_factor,args.balance_reserve)
        write_json(args.output/'balance-admission.json',admission)
        budget_watch=BalanceWatch(lambda:runtime.safe_balance(key,args.output,'balance-current'),
                                 args.budget_currency,args.balance_reserve,initial=before)
        if args.retain_started_from:
            with exclusive(args.retain_started_from/'controller.lock'):
                assert_quiescent(args.retain_started_from)
                with (args.retain_started_from/'continuation-claim.json').open('x') as stream:
                    json.dump(dict(output=str(args.output),claimed_at=runtime.now()),stream)
                    stream.flush();os.fsync(stream.fileno())

        for index,(b,t,k,out) in enumerate(jobs):
            identity=(b,t.id,k)
            if identity not in retained or not finalization.needed(b,t,runtime_backend(k),out):
                continue
            if prior_grade(args.retain_started_from,identity):
                raise ValueError('Unfinalized solver already has a grading claim; refuse automatic replay')
            target=args.output/'solvers'/b/t.id/k
            record=finalization.recover(b,t,runtime_backend(k),out,target,root=args.root,
                image=args.image)
            retained[identity]=dict(retained[identity],run=str(target),status=record['status'],
                                    offline_finalization_from=str(out))
            jobs[index]=(b,t,k,target)

        def solve(job):
            b, t, k, out = job
            if (b,t.id,k) in retained:
                row=dict(retained[(b,t.id,k)],retained_without_rerun=True)
                journal.claim('solver',(b,t.id,k),'retained',row)
                journal.finish('solver',(b,t.id,k),'retained',row)
                return row
            if stop.is_set() or paused.is_set():
                return dict(benchmark=b,task_id=t.id,backend=k,run=str(out),status='not_started')
            binding=fingerprint(dict(task=task_fingerprint(b,t),settings=observed_settings,source=authorization['source_manifest']))
            initial=dict(benchmark=b,task_id=t.id,backend=k,run=str(out),status='dispatch_unknown')
            journal.claim('solver',(b,t.id,k),binding,initial)
            code = command_run(solver_command(args, b, t, k, out, execute=True),
                               args.output / "logs" / (b + "-" + t.id + "-" + k + "-solver"))
            actual_backend=runtime_backend(k)
            report = out / t.id / actual_backend / "report.json"
            row = dict(benchmark=b, task_id=t.id, backend=k, runtime_backend=actual_backend,
                       returncode=code, run=str(out), status="not_started")
            if report.exists():
                record = json.loads(report.read_text())
                row["status"] = record["status"]
                if record.get("fatal_provider_error"):
                    stop.set()
                row['status']=reconcile_solver_status(row['status'],report.parent)
            elif code is not None:
                row['status']=solver_dispatch_status(report.parent)
            journal.finish('solver',(b,t.id,k),binding,row)
            return row

        def score_attempt(job):
            b, t, k, out = job
            if operator_stop.is_set():
                return dict(benchmark=b,task_id=t.id,backend=k,judge_calls=0,status='not_started')
            solver_row=next(r for r in rows if (r['benchmark'],r['task_id'],r['backend'])==(b,t.id,k))
            if solver_row['status'] in {'not_started','dispatch_unknown'}:
                return dict(benchmark=b,task_id=t.id,backend=k,judge_calls=None,status='solver_outcome_unknown')
            actual_backend=runtime_backend(k)
            grades_root=args.output/'grades'
            if k == 'native':
                grades_root=grades_root/k
            binding=grade_binding(b,t,k,out,authorization['source_manifest'])
            identity=(b,t.id,k)
            paid_grade=needs_judge(b,t,out,bool(args.authorized_judges))
            previous_grade=None
            judge_recovery=None
            if args.retain_started_from:
                previous_grade=prior_grade(args.retain_started_from,identity)
            if previous_grade:
                if previous_grade['binding']!=binding:
                    raise ValueError('Retained grade artifact or evaluator binding changed')
                if (previous_grade['body'].get('paid_grade') is False
                        and previous_grade['body'].get('status') in {'grading_failed','grading_outcome_unknown'}):
                    previous_grade=None  # Deterministic work has no paid side effect to replay.
                elif args.recover_judge_5xx:
                    planned=judge_recoveries.get(identity)
                    judge_recovery=judge_recovery_evidence(previous_grade) if planned else None
                    if judge_recovery:
                        if dict(benchmark=b,task_id=t.id,backend=k,**judge_recovery)!=planned:
                            raise ValueError('Judge recovery evidence changed after planning')
                        previous_grade=None
            if previous_grade:
                result=(dict(previous_grade['body'],reused_without_dispatch=True,judge_calls=0,
                             original_judge_calls=previous_grade['body'].get('original_judge_calls',previous_grade['body'].get('judge_calls')))
                        if previous_grade['state']=='complete' else
                        dict(benchmark=b,task_id=t.id,backend=k,judge_calls=None,status='grading_outcome_unknown'))
                journal.claim('grade',identity,binding,result)
                journal.finish('grade',identity,binding,result)
                return result
            if paid_grade and args.recover_judge_5xx and identity not in judge_recoveries:
                return dict(benchmark=b,task_id=t.id,backend=k,judge_calls=0,status='not_started')
            if paid_grade and (paused.is_set() or stop.is_set()):
                return dict(benchmark=b,task_id=t.id,backend=k,judge_calls=0,status='not_started')
            if paid_grade:
                try:
                    budget_watch.check()
                except ValueError as error:
                    pause_budget(error)
                    return dict(benchmark=b,task_id=t.id,backend=k,judge_calls=0,status='not_started')
            journal.claim('grade',identity,binding,dict(benchmark=b,task_id=t.id,backend=k,
                paid_grade=paid_grade,judge_recovery=judge_recovery,status='grading_outcome_unknown'))
            result=grade_attempt(b, t, actual_backend, out, data_root=args.root, grades_root=grades_root,
                credentials=args.credentials, judge_enabled=bool(args.authorized_judges), key=key,
                command_run=command_run, log=args.output / "logs" / (b + "-" + t.id + "-" + k + "-grade"))
            result.update(backend=k, runtime_backend=actual_backend)
            if result.get('fatal_provider_error'):
                stop.set()
            result['grading_artifact']=str(grades_root/b/t.id/actual_backend)
            result['paid_grade']=paid_grade
            if judge_recovery:
                result['judge_recovery']=judge_recovery
            journal.finish('grade',identity,binding,result)
            return result

        def score(job):
            b,t,k,_=job
            try:
                return score_attempt(job)
            except Exception as error:
                entry=journal.get('grade',(b,t.id,k))
                result=dict(benchmark=b,task_id=t.id,backend=k,status='grading_failed',
                    judge_calls=None,error_type=type(error).__name__,
                    paid_grade=entry['body'].get('paid_grade',True) if entry else False)
                if entry and not result['paid_grade']:
                    journal.finish('grade',(b,t.id,k),entry['binding'],result)
                # An interrupted paid phase keeps its durable unknown claim; no replay.
                write_json(args.output/'grading-errors'/b/t.id/(k+'.json'),result)
                return result

        grades = []
        # Separate bounded pools overlap independent grading with solver work.
        with ThreadPoolExecutor(max_workers=args.judge_concurrency) as graders, ThreadPoolExecutor(max_workers=args.concurrency) as solvers:
            solving={solvers.submit(checked,solve,job):job for job in jobs}
            grading=set()
            while solving or grading:
                finished,_=wait(set(solving)|grading,return_when=FIRST_COMPLETED)
                for future in finished:
                    if future in solving:
                        job=solving.pop(future)
                        rows.append(future.result())
                        write_json(args.output/'progress.json',dict(stage='solvers',rows=rows))
                        print(json.dumps(rows[-1]),flush=True)
                        grading.add(graders.submit(score,job))
                    else:
                        grading.remove(future)
                        grades.append(future.result())
                        write_json(args.output/'grading-progress.json',dict(rows=grades))
        after = runtime.safe_balance(key, args.output, "balance-after")
        write_json(args.output / "summary.json", dict(rows=rows, grades=grades, authorization=authorization,
            account_delta=runtime.observed_balance_deltas(before, after),
            accounting_scope="Whole shared-account interval, not attributable per-condition charges",
            interrupted=stop.is_set() or paused.is_set() or any(r['status']=='not_started' for r in rows)
                or any(g['status']=='grading_failed' for g in grades), finished_at=runtime.now()))
        grades_ok = all(g["status"] not in {"missing_summary", "missing_predictions", "grading_failed", "judge_error", "not_started",'solver_outcome_unknown','grading_outcome_unknown','judge_outcome_unknown'} for g in grades)
        return 0 if len(rows) == len(jobs) and all(r["status"] == "cli_exited" for r in rows) and grades_ok and not stop.is_set() and not paused.is_set() else 1
    except BaseException as error:
        interrupt(None, None)
        write_json(args.output / "failure.json", dict(error_type=type(error).__name__,
            completed_solver_receipts=len(rows), balance_preflight_passed=before is not None,
            interrupted=stop.is_set(), observed_at=runtime.now()))
        raise
    finally:
        monitor_done.set()
        watcher.join()
        if stop.is_set():
            cleanup_owned_containers(args.output/'solvers')
        for s, handler in previous.items():
            signal.signal(s, handler)
        ownership.__exit__(None,None,None)


if __name__ == "__main__":
    raise SystemExit(main())
