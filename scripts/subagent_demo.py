"""No-network end-to-end delegation demo; writes a fresh evidence directory."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.agent import Observation, Tool
from harness.config import source_digest
from harness.llm import Completion, ModelConfig, normalize_usage
from harness.runner import write_json
from harness.subagents import LeaderSubagent, SubagentTemplate
from harness.trace import Trace, read_trace, usage_summary, validate


class DemoClient:
    cfg = ModelConfig(model="scripted", retries=0)

    def complete(self, messages, tools=None, tool_choice=None, effort=None):
        names = {t["function"]["name"] for t in tools or []}
        message = {"role": "assistant", "reasoning_content": "scripted", "content": ""}
        if messages[-1]["role"] == "user":
            name = "delegate" if "delegate" in names else "read_document"
            args = {"template": "researcher", "task": "Find the release status."} if name == "delegate" else {}
            message["tool_calls"] = [{"id": "call-1", "type": "function",
                                      "function": {"name": name, "arguments": json.dumps(args)}}]
        else:
            message["content"] = (json.loads(messages[-1]["content"])["report"]
                                  if "delegate" in names else messages[-1]["content"])
        return Completion(message, "tool_calls" if "tool_calls" in message else "stop",
                          normalize_usage({}), 0.0, "scripted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    tool = Tool("read_document", "Read the shared release note.", {"type": "object", "additionalProperties": False},
                lambda args, agent: Observation("Release status: pending independent verification."),
                budgeted=True, read_only=True)
    template = SubagentTemplate("researcher", "Inspect release evidence", "Read evidence and report its status.",
                                ("read_document",))
    manifest = dict(mode="scripted", source_digest=source_digest(), model=asdict(DemoClient.cfg),
                    templates=[asdict(template)], task="Report the release status.")
    write_json(args.output / "manifest.json", manifest)
    with Trace(args.output / "trace.jsonl", args.output.name) as trace:
        trace.emit("run_start", **manifest)
        session = LeaderSubagent(DemoClient(), trace, [template], [tool])
        try:
            result = session.run(manifest["task"])
        except Exception as error:
            trace.emit("run_end", status="error", error=str(error))
            raise
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed" if result.status == "done" else "incomplete")
    events = read_trace(args.output / "trace.jsonl")
    report = dict(outcome=asdict(result), integrity_errors=validate(events), usage=usage_summary(events))
    write_json(args.output / "result.json", report)
    print(json.dumps(report, indent=2))
    if report["integrity_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
