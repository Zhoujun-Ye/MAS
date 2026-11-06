"""Explicit Native Subagents study on the unchanged 60 Validation20 questions."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from common.io import write_json
from scripts.common.prompts.native_subagents import PROMPT
from harness.runtime_support.runtime import (now)
from scripts.studies import benchmark_matrix
from scripts.studies.matched_matrix_report import collect, timeout_zero, write_report

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs/studies/validation20-native-protocol.json"
TASK_MANIFEST = ROOT / "docs/studies/validation20-v1-manifest.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    frozen = json.loads(PROTOCOL.read_text())
    if frozen["organization_sha256"] != {
            "claude-code-subagents": hashlib.sha256(PROMPT.encode()).hexdigest()}:
        raise ValueError("Native prompt differs from the frozen study protocol")
    plan = dict(condition="Native Subagents", attempts=60, maximum_judge_calls=53,
                retries=0, protocol_settings=frozen,
                task_manifest=str(TASK_MANIFEST),
                task_manifest_sha256=benchmark_matrix.digest(TASK_MANIFEST),
                paid_calls_authorized=args.execute, output=str(output))
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    if Path.cwd().resolve() != ROOT:
        raise ValueError("Execute from the project source root so child modules use the frozen source")
    allowed = Path("/home/zhoujunye/mas/outputs")
    prompt_path = Path(str(output) + ".organization-prompt.txt")
    status_path = Path(str(output) + ".driver-status.json")
    export_path = Path(str(output) + "-export.json")
    report_path = Path(str(output) + "-report")
    if output.parent != allowed or any(p.exists() for p in (
            output, prompt_path, status_path, export_path, report_path)):
        raise ValueError("Use a fresh direct child of the project server outputs directory")
    os.umask(0o077)
    with prompt_path.open("x", encoding="utf-8") as stream:
        stream.write(PROMPT)
    command = ["--root", "/home/zhoujunye/mas-data", "--output", str(output),
               "--proofs", str(args.proofs.resolve()),
               "--image", "mas/research-benchmarks:20261103-v1",
               "--backends", "claude-code-subagents", "--organization-prompt", str(prompt_path),
               "--effort", frozen["effort"], "--concurrency", str(frozen["solver_concurrency"]),
               "--judge-concurrency", str(frozen["judge_concurrency"]),
               "--task-manifest", plan["task_manifest"], "--protocol-settings", str(PROTOCOL),
               "--tasks-per-benchmark", "20", "--task-offset", "0",
               "--authorized-attempts", "60", "--authorized-judges", "53", "--execute"]
    matrix_status = report_status = None
    try:
        matrix_status = benchmark_matrix.main(command)
        report = timeout_zero(collect(output))
        report["condition_label"] = "Native Subagents"
        write_report(report, report_path)
        write_json(export_path, report)
        report_status = 0
    finally:
        write_json(status_path, dict(matrix_exit_code=matrix_status, report_exit_code=report_status,
                                     finished_at=now(), output=str(output)))
    return 0 if matrix_status == 0 and report_status == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
