"""Durable offline preparation pipeline, suitable for a user systemd service."""

import argparse
import json
import os
import signal
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from harness.runtime_support.runtime import now
from scripts.fdabench.prepare import HF_ENDPOINT


class PreparationInterrupted(Exception):
    pass


def interrupted(signum, frame):
    raise PreparationInterrupted(signum)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Fresh host-only preparation receipt directory")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--hf-endpoint", choices=(HF_ENDPOINT, "https://huggingface.co"), default=HF_ENDPOINT)
    parser.add_argument("--cdn-proxy-socket", type=Path, help="Explicit per-run CDN-only Mac tunnel; mirror requests remain direct")
    parser.add_argument("--hf-credentials", type=Path, help="Host-only HF_TOKEN credential file; never passed as a token argument")
    args = parser.parse_args(argv)
    root, output = args.root.resolve(), args.output.resolve()
    if not args.execute:
        print(json.dumps(dict(status="planned", root=str(root), endpoint=args.hf_endpoint, paid_calls=0)))
        return 0
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=False)
    state = dict(status="running", started_at=now(), root=str(root), workers=args.workers,
                 paid_calls=0, cloud_databases=False, stages=[], endpoint=args.hf_endpoint,
                 transport="mirror-direct-cdn-mac-clash" if args.cdn_proxy_socket else "server-direct-https",
                 cdn_proxy_socket=str(args.cdn_proxy_socket) if args.cdn_proxy_socket else None)
    write_json(output / "status.json", state)
    commands = [
        ("download", ["scripts.fdabench.prepare", "--root", str(root), "--assets", "release", "databases", "corpus",
                      "--workers", str(args.workers), "--hf-endpoint", args.hf_endpoint, "--execute"]),
        ("index", ["scripts.fdabench.index_corpus", "--data", str(root / "data"), "--execute"]),
        ("catalog", ["scripts.fdabench.catalog", "--upstream", str(root / "upstream"),
                     "--tasks", str(root / "release"), "--data", str(root / "data"),
                     "--output", str(output / "catalog.json")]),
    ]
    if args.hf_credentials:
        commands[0][1].extend(['--hf-credentials', str(args.hf_credentials.resolve())])
    if args.cdn_proxy_socket:
        commands[0][1].extend(['--cdn-proxy-socket', str(args.cdn_proxy_socket)])
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        for name, command in commands:
            state["stage"] = name
            write_json(output / "status.json", state)
            with (output / (name + ".log")).open("x") as log:
                result = subprocess.run([sys.executable, "-m", *command],
                    cwd=Path(__file__).resolve().parents[2], stdout=log, stderr=subprocess.STDOUT)
            state["stages"].append(dict(name=name, returncode=result.returncode))
            if result.returncode:
                state.update(status="failed", finished_at=now())
                write_json(output / "status.json", state)
                return 1
        catalog = json.loads((output / "catalog.json").read_text())
        state.update(status="prepared" if not catalog["readiness_counts"].get("missing_inputs") else "partial",
                     finished_at=now(), readiness_counts=catalog["readiness_counts"])
    except PreparationInterrupted as error:
        state.update(status="interrupted", signal=error.args[0], finished_at=now())
        write_json(output / "status.json", state)
        return 128 + error.args[0]
    except BaseException as error:
        state.update(status="failed", error_type=type(error).__name__, finished_at=now())
        write_json(output / "status.json", state)
        raise
    finally:
        signal.signal(signal.SIGTERM, previous)
    write_json(output / "status.json", state)
    print(json.dumps(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
