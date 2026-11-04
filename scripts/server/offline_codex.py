"""Parallel native Codex mode/shell probes in offline Docker; no provider calls."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis.codex_evidence import inspect as codex_evidence
from benchmarks._io import write_json
from harness import CodexSingleAgentCLI, CodexSubagentsCLI
from harness._codex_cli import VERSION
from scripts.common import runtime


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_names(tools):
    names = set()
    for tool in tools:
        if isinstance(tool, dict):
            if isinstance(tool.get("name"), str):
                names.add(tool["name"])
            names.update(tool_names(tool.get("tools", [])))
    return names


def probe(backend, output, image):
    single = backend.endswith("single-agent")
    folder = output / backend
    work, profile = folder / "workspace", folder / "native-profile"
    work.mkdir(parents=True)
    (profile / "home").mkdir(parents=True)
    (profile / "codex").mkdir()
    catalog = runtime.CODEX_CATALOG.with_name("deepseek-single-models.json") if single else runtime.CODEX_CATALOG
    proof = dict(backend=backend, passed=False, paid_calls=0, network="none", real_credentials=False,
                 shell_verified=False, tool_exposure_verified=False, native_codex={},
                 runtime_binding=dict(image_id=image, binary_sha256=digest(runtime.CODEX), catalog_sha256=digest(catalog)))
    identity = None
    try:
        script = Path(__file__).resolve().parents[1] / "probes/codex.py"
        identity = runtime.container(work, profile, work, image, network="none", backend=backend,
                                     dataset_mounts=[(script, "/probe.py", True)])
        version = subprocess.check_output(["docker", "exec", identity, str(runtime.CODEX), "--version"],
                                         text=True, timeout=30).strip()
        proof["native_version"] = version
        if version != "codex-cli " + VERSION:
            raise ValueError("Unexpected Codex version")
        adapter = (CodexSingleAgentCLI if single else CodexSubagentsCLI)(str(runtime.CODEX))
        command = adapter.command(**runtime.options(backend), docker_isolated=True)
        argv = ["docker", "exec", "-i", "--workdir", "/workspace", identity,
                "python3", "/probe.py", "--argv-json", json.dumps(command)]
        if not single:
            argv.append("--subagents")
        result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        (folder / "probe-stdout.log").write_text(result.stdout)
        (folder / "probe-stderr.log").write_text(result.stderr)
        proof["probe_returncode"] = result.returncode
        transport = json.loads(result.stdout) if result.returncode == 0 else {}
        proof["cli_returncode"] = transport.get("returncode")
        requests = json.loads((profile / "probe-requests.json").read_text())
        names = tool_names(requests[0].get("tools", [])) if requests else set()
        has_spawn = any(name.endswith("spawn_agent") for name in names)
        proof["tool_exposure_verified"] = bool(requests) and (not has_spawn if single else has_spawn)
        marker = work / "probe-result.txt"
        proof["shell_verified"] = marker.is_file() and not marker.is_symlink() and marker.read_text() == "probe-ok"
        proof["native_codex"] = codex_evidence(profile / "codex", single=single)
        proof["passed"] = bool(result.returncode == 0 and transport.get("returncode") == 0
                               and proof["tool_exposure_verified"] and proof["shell_verified"]
                               and proof["native_codex"]["passed"])
    except Exception as error:
        proof.update(passed=False, error_type=type(error).__name__)
    finally:
        if identity is not None:
            try:
                try:
                    runtime.stop_container(identity)
                finally:
                    subprocess.run(["docker", "rm", identity], capture_output=True, check=True)
                proof["container_removed"] = True
            except Exception as error:
                proof.update(passed=False, cleanup_error_type=type(error).__name__)
        write_json(folder / "proof.json", proof)
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status="planned", modes=2, concurrency=2, paid_calls=0, network="none")))
        return 0
    os.umask(0o077)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image], text=True))[0]["Id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda backend: probe(backend, args.output, image),
                             ("codex-single-agent", "codex-subagents")))
    summary = dict(passed=all(row["passed"] for row in rows), paid_calls=0, network="none", concurrency=2,
                   results=[dict(backend=row["backend"], passed=row["passed"],
                                 proof=str(args.output / row["backend"] / "proof.json")) for row in rows])
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
