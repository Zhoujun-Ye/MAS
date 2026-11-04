"""Plan an external CLI invocation; --execute is an explicit paid-run action."""

import argparse
import json
from pathlib import Path

from . import (ClaudeCodeSubagentsCLI, ClaudeCodeSingleAgentCLI,
              CodexSingleAgentCLI, CodexSubagentsCLI)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=("claude-code-subagents", "claude-code-single-agent",
                                            "codex-single-agent", "codex-subagents"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--executable")
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--allowed-tool", action="append", default=[])
    parser.add_argument("--max-budget-usd", type=float)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    args = parser.parse_args(argv)
    kind = {"claude-code-subagents": ClaudeCodeSubagentsCLI,
            "claude-code-single-agent": ClaudeCodeSingleAgentCLI,
            "codex-single-agent": CodexSingleAgentCLI,
            "codex-subagents": CodexSubagentsCLI}[args.backend]
    codex = args.backend.startswith("codex-")
    adapter = kind(args.executable or ("codex" if codex else "claude"))
    options = dict(allowed_tools=tuple(args.allowed_tool), max_budget_usd=args.max_budget_usd)
    if codex:
        if args.allowed_tool or args.max_budget_usd is not None:
            parser.error("Codex does not support the Claude tool allowlist or dollar-budget options")
        options = dict(base_url=args.base_url)
    result = adapter.run(args.prompt_file.read_text(encoding="utf-8"), model=args.model,
                         workspace=args.workspace, output=args.output, timeout=args.timeout,
                         execute=args.execute, **options)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"planned", "cli_exited"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
