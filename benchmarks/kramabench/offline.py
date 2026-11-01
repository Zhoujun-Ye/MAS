"""Scripted adapter smoke, with synthetic data and no Docker/model/judge access."""

import csv
import json
from pathlib import Path
import shlex
import subprocess
import sys

from harness.agent import Observation
from harness.data_tools import INSPECT_SCRIPT
from harness.execution import ContainerWorkspace
from harness.llm import Completion, ModelConfig, normalize_usage
from harness.catalog import fingerprint
from harness.runner import write_json
from harness.subagents import resolve_mode
from .adapter import run_task
from .tasks import Task

PIPELINE = "import csv\nwith open('/data/values.csv') as f:\n    values = [float(r['value']) for r in csv.DictReader(f)]\nprint(sum(values) / len(values))\n"
FIXTURE_TASK = Task("fixture-average", "archeology", "Return the average value. LEADER_ONLY_SENTINEL")


class FixtureWorkspace(ContainerWorkspace):
    """Only fixed fixture operations run on the host; never arbitrary commands."""
    def __init__(self, root):
        self.root = Path(root)
        self.data = self.root / "data"
        self.work = self.root / "work"
        self.data.mkdir(parents=True)
        self.work.mkdir()
        (self.data / "values.csv").write_text("value\n2\n4\n6\n")
        super().__init__("fixture-not-a-container", archive_dir=self.root / "retained")

    def execute(self, command, stdin=None, **options):
        if command != "python3 -I -c " + shlex.quote(INSPECT_SCRIPT):
            raise AssertionError("Fixture refuses arbitrary execution")
        payload = json.loads(stdin)
        payload["root"] = str({"/data": self.data, "/workspace": self.work}[payload["root"]])
        result = subprocess.run([sys.executable, "-I", "-c", INSPECT_SCRIPT], input=json.dumps(payload),
                                text=True, capture_output=True, timeout=5)
        return dict(exit_code=result.returncode, output=result.stdout + result.stderr, truncated=False,
                    execution_error=False, error_kind=None)

    def tools(self):
        tools = super().tools()
        for tool in tools:
            if tool.name == "terminal":
                tool.run = self.calculate
            elif tool.name == "read_file":
                tool.run = self.read_artifact
            elif tool.name in {"write_file", "read_output"}:
                tool.run = lambda args, agent: Observation("Not used in this fixture", {"error": True})
        return tools

    def calculate(self, args, agent):
        if args != {"command": "fixture_average"}:
            raise ValueError("Only fixture_average is supported; no shell is executed")
        with (self.data / "values.csv").open() as stream:
            values = [float(row["value"]) for row in csv.DictReader(stream)]
        answer = sum(values) / len(values)
        (self.work / "answer.json").write_text(json.dumps({"answer": answer}))
        (self.work / "pipeline.py").write_text(PIPELINE)
        return Observation(json.dumps({"answer": answer, "rows": len(values)}))

    def read_artifact(self, args, agent):
        if args["path"] != "/workspace/answer.json":
            raise ValueError("Fixture permits only answer.json")
        return Observation((self.work / "answer.json").read_text())

    def audit_snapshot(self, *, timeout=None):
        from harness.catalog import fingerprint
        return {"fixture_only": True, "files": {
            str(p.relative_to(self.work)): fingerprint(p.read_text())
            for p in sorted(self.work.rglob("*")) if p.is_file()}}


class FixtureClient:
    cfg = ModelConfig(model="scripted", retries=0)

    def complete(self, messages, tools=None, tool_choice=None, effort=None, *, response_format=None):
        names = {tool["function"]["name"] for tool in tools or []}
        calls, content = [], ""
        if "delegate" in names:
            reports = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            if not reports:
                calls = [("delegate", {"template": "data_scout", "task": "Inspect values.csv columns."}),
                         ("delegate", {"template": "data_scout", "task": "Check available files."})]
            elif len(reports) == 2:
                calls = [("delegate", {"template": "pipeline_analyst", "task": "Compute average of value in values.csv; save answer.json and pipeline.py in your exclusively assigned /workspace directory. No other writer runs in this fixture."})]
            elif len(reports) == 3:
                calls = [("delegate", {"template": "result_reviewer", "task": "Read answer.json; inspect calculation evidence."})]
            elif len(reports) == 4:
                calls = [("delegate", {"template": "result_reviewer", "resume_id": reports[-1]["agent_id"],
                                       "task": "Recheck that the saved answer is 4."})]
            else:
                calls = [("submit", {"answer": 4.0, "pipeline_code": PIPELINE,
                    "evidence": "Synthetic fixture: 3 values, average 4; scripted verification only.", "unfinished": []})]
        elif messages[-1]["role"] == "user":
            if "terminal" in names:
                calls = [("terminal", {"command": "fixture_average"})]
            elif "You review" in messages[0]["content"]:
                calls = [("read_file", {"path": "/workspace/answer.json"})]
            else:
                calls = [("inspect_file", {"area": "data", "path": "values.csv"})]
        else:
            content = messages[-1]["content"]
        message = {"role": "assistant", "content": content, "reasoning_content": "scripted fixture"}
        if calls:
            message["tool_calls"] = [{"id": f"call-{len(messages)}-{i}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}} for i, (name, args) in enumerate(calls)]
        return Completion(message, "tool_calls" if calls else "stop", normalize_usage({}), 0.0, "scripted")


class SingleFixtureClient:
    cfg = ModelConfig(model="scripted", retries=0)

    def complete(self, messages, tools=None, tool_choice=None, effort=None, *, response_format=None):
        assert "delegate" not in {tool["function"]["name"] for tool in tools or []}
        assert "LEADER_ONLY_SENTINEL" in messages[1]["content"]
        observations = [m for m in messages if m["role"] == "tool"]
        actions = [("inspect_file", {"area": "data", "path": "values.csv"}),
                   ("terminal", {"command": "fixture_average"}),
                   ("read_file", {"path": "/workspace/answer.json"})]
        message = {"role": "assistant", "reasoning_content": "scripted fixture", "content": ""}
        if len(observations) < len(actions):
            name, args = actions[len(observations)]
            message["tool_calls"] = [{"id": f"single-{len(observations)}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}]
        else:
            args = {"answer": json.loads(observations[-1]["content"])["answer"],
                    "pipeline_code": PIPELINE, "evidence": "Synthetic CSV inspection and fixed fixture computation.",
                    "unfinished": []}
            message["tool_calls"] = [{"id": "single-submit", "type": "function",
                "function": {"name": "submit", "arguments": json.dumps(args)}}]
        return Completion(message, "tool_calls" if "tool_calls" in message else "stop",
                          normalize_usage({}), 0.0, "scripted")


def smoke(output, *, mode="mas"):
    mode = resolve_mode(mode=mode)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    workspace = FixtureWorkspace(output / "fixture")
    client = SingleFixtureClient() if mode == "single" else FixtureClient()
    return run_task(FIXTURE_TASK, client=client, workspace=workspace, output=output / "attempt",
                    dataset=workspace.data, mode=mode)


def comparison_smoke(output):
    """Two independent synthetic attempts. Not a paid runner or efficacy study."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    summary = {"fixture_only": True, "evaluation": "not_run", "order": ["single", "mas"], "arms": {}}
    write_json(output / "comparison.json", summary)
    contracts = []
    try:
        for mode in summary["order"]:
            response = smoke(output / mode, mode=mode)
            attempt = output / mode / "attempt"
            manifest = json.loads((attempt / "manifest.json").read_text())
            report = json.loads((attempt / "report.json").read_text())
            outcome = json.loads((attempt / "outcome.json").read_text())
            dataset = output / mode / "fixture" / "data"
            contract = {key: manifest[key] for key in ("task", "model", "source_digest", "pricing", "domain_tools", "output_contract")}
            contract.update(shared_limits=manifest["limits"]["shared"],
                            root_turns=manifest["limits"]["leader_turns"],
                            root_tools=manifest["limits"]["leader_tools"],
                            catalog_sha256=manifest["catalog"]["sha256"],
                            data={str(p.relative_to(dataset)): fingerprint(p.read_bytes().hex())
                                  for p in sorted(dataset.rglob("*")) if p.is_file()})
            contracts.append(contract)
            summary["arms"][mode] = {"status": outcome["status"], "infra_affected": outcome["infra_affected"],
                "usage": report["usage"], "cache": report["cache"], "budget": outcome["budget"],
                "runtime": report["runtime"], "cost_usd_actual": report["cost_usd_actual"],
                "integrity_errors": report["integrity_errors"], "response": response}
            write_json(output / "comparison.json", summary)
        if contracts[0] != contracts[1]:
            raise ValueError("Fixture comparison settings or input contents differ")
        summary.update(matched_contract=contracts[0], contract_sha256=fingerprint(contracts[0]), status="completed")
    except Exception as error:
        summary.update(status="error", error_type=type(error).__name__, error=str(error))
        write_json(output / "comparison.json", summary)
        raise
    write_json(output / "comparison.json", summary)
    return summary
