"""Probe the installed interactive CLI in a network-disabled disposable container."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import ClaudeCodeAgentTeamCLI
from benchmarks.kramabench._io import write_json
from scripts.kramabench.cli_runtime import CLAUDE, container, options, stop_container


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--image", default="mas-information/kramabench:20261101-v1")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    work, profile = root / "workspace", root / "native-profile"
    work.mkdir()
    profile.mkdir()
    (profile / "home").mkdir()
    subprocess.run(["git", "init", "--quiet", str(work)], check=True)
    identity = container(work, profile, args.upstream.resolve() / "data", args.image,
                         network="none", backend="claude-code-agent-team")
    try:
        result = ClaudeCodeAgentTeamCLI(str(CLAUDE)).run("", workspace=work, output=root / "cli",
            timeout=args.timeout, execute=True, startup_only=True,
            command_prefix=("docker", "exec", "-it", "--workdir", "/workspace", identity),
            version_prefix=("docker", "exec", "-i", identity), observer_dir=profile / "observer",
            observer_target="/native/observer", hook_script="/adapter-hooks.py", cli_workspace="/workspace",
            native_profile=profile / "claude", **options("claude-code-agent-team"))
        result.update(network="none", real_provider_credentials=False, paid_calls=0)
        write_json(root / "preflight.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        stop_container(identity)
        subprocess.run(["docker", "rm", identity], check=True, capture_output=True)


if __name__ == "__main__":
    main()
