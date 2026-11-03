"""Plan an external CLI invocation; --execute is an explicit paid-run action."""

import argparse
import json
from pathlib import Path

from . import ClaudeCodeAgentTeamCLI, ClaudeCodeSubagentsCLI, ClaudeCodeSingleAgentCLI, DeepAgentsCLI


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=("deepagents", "claude-code-agent-team", "claude-code-subagents", "claude-code-single-agent"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--executable")
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--shell-allow-list")
    parser.add_argument("--allowed-tool", action="append", default=[])
    parser.add_argument("--max-budget-usd", type=float)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.backend == "deepagents":
        if args.allowed_tool or args.max_budget_usd is not None:
            parser.error("--allowed-tool and --max-budget-usd are Claude-only")
        adapter = DeepAgentsCLI(args.executable or "dcode")
        options = dict(shell_allow_list=args.shell_allow_list)
    else:
        if args.shell_allow_list is not None:
            parser.error("--shell-allow-list is Deep Agents-only")
        kind = {"claude-code-agent-team": ClaudeCodeAgentTeamCLI,
                "claude-code-subagents": ClaudeCodeSubagentsCLI,
                "claude-code-single-agent": ClaudeCodeSingleAgentCLI}[args.backend]
        adapter = kind(args.executable or "claude")
        options = dict(allowed_tools=tuple(args.allowed_tool), max_budget_usd=args.max_budget_usd)
    result = adapter.run(args.prompt_file.read_text(encoding="utf-8"), model=args.model,
                         workspace=args.workspace, output=args.output, timeout=args.timeout,
                         execute=args.execute, **options)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"planned", "cli_exited"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
