"""Absolute-path entrypoint for isolated Python hook/MCP subprocesses."""

from pathlib import Path
import sys


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    if len(sys.argv) < 2 or sys.argv[1] not in ('hook', 'mcp'):
        raise SystemExit('Expected hook or mcp')
    mode = sys.argv.pop(1)
    if mode == 'hook':
        from harness.evidence_mas.hook import main as run
    else:
        from harness.evidence_mas.mcp import main as run
    run()


if __name__ == '__main__':
    main()
