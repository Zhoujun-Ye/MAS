"""Native CLI mode and real-data mount probes with network=none and dummy keys."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis.native_evidence import native_single_agent, native_subagents
from common.io import write_json
from benchmarks.dataclawbench.tasks import load_tasks as dataclaw_tasks
from benchmarks.hybriddeepresearch.tasks import load_tasks as hybrid_tasks
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from harness._claude_cli import hook_settings
from harness.runtime_support import runtime
from harness.runtime_support.inference import proof_requests
from scripts.common.run import mounts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument('--effort', choices=runtime.EFFORTS, default=runtime.DEFAULT_EFFORT)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status="planned", mode_probes=4, budget_probes=2, paid_calls=0)))
        return
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    image_id = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    args.image = image_id
    with runtime.CLAUDE.open("rb") as binary:
        binary_sha256 = hashlib.file_digest(binary, "sha256").hexdigest()
    binding = dict(image_id=image_id, binary_sha256=binary_sha256)
    code = Path(__file__).resolve().parents[2]
    dc_root = args.root / "dataclawbench/upstream"
    hdr_tasks = args.root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"
    dc = next(t for t in dataclaw_tasks(dc_root) if not t.web)
    hdr = next(t for t in hybrid_tasks(hdr_tasks) if t.category == "search_to_sql")
    results = []
    for task, budget in [(dc, False), (hdr, False), (dc, True)]:
        modes = ["single-agent", "subagents"]
        for mode in modes:
            backend = "claude-code-" + mode
            folder = args.output / (task.benchmark + ("-budget" if budget else "")) / backend
            work, profile = folder / "workspace", folder / "native-profile"
            work.mkdir(parents=True)
            (profile / "home").mkdir(parents=True)
            data = dc_root / "assets/database" if task.benchmark == "dataclawbench" else args.root / "hybriddeepresearch/data"
            inputs = mounts(task, argparse.Namespace(upstream=dc_root, data=data, data_variant="database"))
            script = code / 'scripts/probes/native_transport.py'
            inputs += [(script, "/probe.py", True), (code / "harness/runtime_support/tools.py", "/benchmark-tools.py", True)]
            identity = runtime.container(work, profile, data, args.image, network="none", backend=backend,
                                         dataset_mounts=inputs, effort=args.effort)
            try:
                if task.benchmark == "hybriddeepresearch":
                    check = ["python3", "/benchmark-tools.py", "sql", "--db", f"/data/{task.db}/{task.db}_template.sqlite",
                             "--query", "SELECT count(*) AS tables FROM sqlite_master WHERE type='table'"]
                else:
                    check = ["python3", "-c", "import pathlib,pandas as pd,json; fs=sorted(pathlib.Path('/data').rglob('*.csv')); assert fs; print(json.dumps({'csv_files':len(fs),'readable':all(len(pd.read_csv(p,nrows=1).columns)>0 for p in fs)}))"]
                checked = subprocess.check_output(["docker", "exec", identity, *check], text=True, timeout=120)
                write_json(folder / "data-check.json", json.loads(checked))
                adapter = (ClaudeCodeSingleAgentCLI if mode == "single-agent" else ClaudeCodeSubagentsCLI)(str(runtime.CLAUDE))
                options = runtime.options(backend)
                options["settings"] = dict(hooks=hook_settings("/native/observer", "/adapter-hooks.py", single_agent=mode == "single-agent"))
                if budget:
                    options["max_budget_usd"] = 0.01
                command = adapter.command(**options)
                probe_args = ['--mode', mode, "--argv-json", json.dumps(command), "--output", "/native/probe"]
                if budget:
                    probe_args += ["--fake-input-tokens", "1000000"]
                result = subprocess.run(["docker", "exec", "-i", "--workdir", "/workspace", identity,
                                         "python3", "/probe.py", *probe_args], capture_output=True, text=True, timeout=180)
                (folder / "probe-stdout.log").write_text(result.stdout)
                (folder / "probe-stderr.log").write_text(result.stderr)
            finally:
                runtime.stop_container(identity)
                subprocess.run(["docker", "rm", identity], check=True, capture_output=True)
            (folder / "cli").mkdir()
            shutil.copyfile(profile / "probe/stdout.log", folder / "cli/stdout.log")
            proof = json.loads((profile / "probe/transport.json").read_text())
            proof.update(backend=backend, task_id=task.id, benchmark=task.benchmark)
            requests = json.loads((profile / 'probe/fake-provider-requests.json').read_text())
            proof.update(proof_requests(requests, args.effort))
            if budget:
                events = [json.loads(line) for line in (folder / "cli/stdout.log").read_text().splitlines() if line.startswith("{")]
                native = next((e for e in reversed(events) if e.get("type") == "result"), {})
                proof.update(native_result=native, passed=native.get("subtype") == "error_max_budget_usd")
            else:
                name = "native_single_agent" if mode == "single-agent" else "native_subagents"
                proof[name] = (native_single_agent if mode == "single-agent" else native_subagents)(folder)
                proof["passed"] = result.returncode == 0 and proof[name]["passed"]
                if mode == "single-agent":
                    proof["passed"] = proof["passed"] and proof.get("delegation_rejections_observed", 0) >= 2
            with runtime.CLAUDE.open("rb") as binary:
                unchanged = hashlib.file_digest(binary, "sha256").hexdigest() == binary_sha256
            proof['passed'] = bool(proof['passed'] and proof['request_effort_verified'])
            if proof["passed"] and unchanged:
                proof["runtime_binding"] = binding
            elif not unchanged:
                proof.update(passed=False, runtime_binding_error="CLI binary changed during offline probes")
            write_json(folder / "proof.json", proof)
            results.append(dict(benchmark=task.benchmark, backend=backend, budget_probe=budget, passed=proof["passed"], proof=str(folder / "proof.json")))
            print(json.dumps(results[-1]), flush=True)
    write_json(args.output / "summary.json", dict(results=results, paid_calls=0, network="none", passed=all(r["passed"] for r in results)))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
