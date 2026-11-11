"""Exercise all three Krama prompt conditions with a synthetic provider and offline replay."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from benchmarks.kramabench.tasks import load_tasks
from harness.runtime_support import credential_gateway
from scripts.common.prompts.conditions import condition_instructions, runtime_backend
from scripts.kramabench import cli_runtime as krama
from scripts.probes.external_workflow import WorkflowFixture
from scripts.probes.offline_gateway import Fixture as ErrorFixture


CONDITIONS = ("claude-code-single-agent", "native", "claude-code-subagents")


class KramaFixture(WorkflowFixture):
    def next(self, body):
        block = super().next(body)
        if block.get("type") == "tool_use" and block["id"].endswith("-submit"):
            code = ("from pathlib import Path; import json,subprocess; "
                    "Path('pipeline.py').write_text('import json\\nprint(json.dumps({\"answer\":2}))\\n'); "
                    "Path('submission.json').write_text(json.dumps(dict(answer=2,pipeline_path='pipeline.py',"
                    "evidence='synthetic workflow',unfinished=[]))); "
                    "subprocess.run(['python3','pipeline.py'],check=True)")
            block.update(name="Bash", input=dict(command="python3 -c " + shlex.quote(code),
                                                description="Write and run synthetic pipeline"))
        return block


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default=krama.runtime.DEFAULT_SOLVER_IMAGE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--error-status", type=int, choices=(503,),
                        help="Inject one upstream error to verify native no-retry behavior; not an admission proof")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status="planned", conditions=3, paid_calls=0)))
        return 0
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    upstream = args.root / "kramabench/upstream"
    task = load_tasks(upstream)[0][0]
    command = "python3 -c " + shlex.quote(
        "from pathlib import Path; import os,numpy; from threadpoolctl import threadpool_info; "
        f"assert all(os.environ.get(k)=={str(krama.runtime.DEFAULT_COMPUTE_THREADS)!r} for k in {list(krama.THREADS)!r}); "
        f"assert all(p['num_threads']<={krama.runtime.DEFAULT_COMPUTE_THREADS} for p in threadpool_info()); "
        "p=next(p for p in Path('/data').rglob('*') if p.is_file()); p.open('rb').read(80); print('input accessible')")
    jobs, fixtures = [], {}
    for condition in CONDITIONS:
        backend = runtime_backend(condition)
        fixture = ErrorFixture(backend, args.error_status) if args.error_status else KramaFixture(backend, command)
        key = "synthetic-" + secrets.token_hex(24)
        fixtures[key] = fixture
        options = SimpleNamespace(output=args.output / condition, upstream=upstream, image=image,
            subagents_prompt="native" if condition == "native" else "structured",
            timeout=180, replay_timeout=180, effort="max", cpus=krama.runtime.DEFAULT_CPUS,
            compute_threads=krama.runtime.DEFAULT_COMPUTE_THREADS, record_resources=True)
        jobs.append((condition, backend, fixture, key, options))

    def fake(request):
        key = request.get_header("Authorization", "").removeprefix("Bearer ")
        if key not in fixtures or not request.full_url.startswith("https://api.deepseek.com/anthropic/"):
            raise RuntimeError("Non-synthetic upstream request blocked")
        return fixtures[key].respond(request)

    def execute(job):
        condition, backend, fixture, key, options = job
        report = krama.run_attempt(task, backend, options, key, threading.Event(), set(), threading.Lock())
        folder = options.output / task.id / backend
        if not args.error_status:
            report = krama.collect_attempt(folder, report, options)
        prompt = (folder / "cli/prompt.txt").read_text()
        expected = task.query + "\n\n" + krama.INSTRUCTIONS + krama.limit_instructions(options.timeout) + "\n" + condition_instructions(options, backend)
        audit = report.get("single_agent_audit", report.get("subagents_audit", {}))
        if args.error_status:
            records = [json.loads(line) for line in (folder / 'gateway-requests.jsonl').read_text().splitlines()]
            sent = [r for r in records if r.get('event') == 'dispatched' and r.get('route') == '/anthropic/v1/messages']
            done = [r for r in records if r.get('event') == 'finished' and r.get('upstream_attempted')
                    and r.get('route') == '/anthropic/v1/messages']
            passed = (report['status'] == 'cli_error' and prompt == expected and len(fixture.requests) == 1
                      and len(sent) == len(done) == 1 and done[0].get('http_status') == args.error_status)
            return dict(condition=condition, backend=backend, passed=passed, status=report['status'],
                injected_http_status=args.error_status, model_requests=len(sent), native_retry_count=len(sent)-1,
                prompt_exact=prompt == expected, cli_timing=report.get('cli', {}).get('timing'),
                cleanup=report.get('cleanup'))
        passed = (report["status"] == "cli_exited" and audit.get("passed") is True
            and report.get("submission", {}).get("answer") == 2 and report.get("pipeline_exit_code") == 0
            and report.get("pipeline_answer_matches_submission") is True and prompt == expected and not fixture.errors
            and all((folder / "workspace" / name).read_text() == krama.INSTRUCTIONS for name in ("AGENTS.md", "CLAUDE.md")))
        return dict(condition=condition, backend=backend, passed=passed, status=report["status"],
            native_audit_passed=audit.get("passed"), subagent_starts=audit.get("subagent_starts"),
            prompt_exact=prompt == expected, fake_model_requests=len(fixture.requests),
            pipeline_exit_code=report.get("pipeline_exit_code"),
            pipeline_answer_matches_submission=report.get("pipeline_answer_matches_submission"),
            cli_timing=report.get('cli', {}).get('timing'), cleanup=report.get('cleanup'),
            resources=report.get("resources"))

    with patch.object(credential_gateway, "open_upstream", fake):
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(pool.map(execute, jobs))
    proof = dict(passed=all(r["passed"] for r in rows), paid_calls=0, real_credentials=False,
                 network="none", concurrency=3, results=rows,
                 proof_kind="native_error_injection" if args.error_status else "synthetic_benchmark_workflow",
                 scope="Synthetic mechanics, not benchmark correctness or model contribution")
    write_json(args.output / "summary.json", proof)
    print(json.dumps(proof))
    return 0 if proof["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
