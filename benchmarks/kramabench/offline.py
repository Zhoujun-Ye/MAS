"""Scripted adapter smoke, with synthetic data and no Docker/model/judge access."""

import csv
import json
from pathlib import Path
import shlex
import subprocess
import sys

from harness.agent import Observation
from harness.artifacts import ARTIFACT_READ_SCRIPT
from harness.data_tools import INSPECT_SCRIPT
from harness.execution import ContainerWorkspace
from harness.llm import Completion, ModelConfig, normalize_usage
from harness.catalog import fingerprint
from harness.runner import write_json
from harness.session import resolve_mode
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
        scripts = {"python3 -I -c " + shlex.quote(script): script for script in (INSPECT_SCRIPT, ARTIFACT_READ_SCRIPT)}
        if command not in scripts:
            raise AssertionError("Fixture refuses arbitrary execution")
        payload = json.loads(stdin)
        payload["root"] = str({"/data": self.data, "/workspace": self.work}[payload["root"]])
        result = subprocess.run([sys.executable, "-I", "-c", scripts[command]], input=json.dumps(payload),
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
        import hashlib
        return {"fixture_only": True, "files": {
            str(p.relative_to(self.work)): {"kind": "file", "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(self.work.rglob("*")) if p.is_file()}}


class FixtureClient:
    cfg = ModelConfig(model="scripted", retries=0)

    def complete(self, messages, tools=None, tool_choice=None, effort=None, *, response_format=None):
        names = {tool["function"]["name"] for tool in tools or []}
        calls, content = [], ""
        previous = [c["function"]["name"] for m in messages for c in m.get("tool_calls", [])]
        if "spawn_worker" in names or names == {"submit"}:
            if "finish_team" in previous or names == {"submit"}:
                notices = [json.loads(record["content"]) for message in messages
                    if message["role"] == "user" and message["content"].startswith("Team inbox")
                    for record in json.loads(message["content"].split("\n", 1)[1])
                    if record["sender"] == "runtime" and record["content"].startswith("{")]
                closing = next(n for n in reversed(notices) if n.get("event") == "team_closed")
                path = next(p for p, item in closing["state"]["frozen_files"].items()
                            if p.endswith(".py") and item["submission_status"] == "hash_recorded")
                calls = [("submit", {"answer": 4.0, "pipeline_path": path,
                    "evidence": "Synthetic fixture: 3 values, average 4; scripted verification only.", "unfinished": []})]
            elif not previous:
                calls = [("spawn_worker", {"template": "worker", "task": "Compute average of values.csv using fixture_average."})]
            elif previous[-1] == "get_team_state":
                state = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))
                task = state["tasks"][0]
                if task["status"] == "reported":
                    calls = [("update_task", dict(task_id=task["task_id"], expected_revision=task["revision"], action="accept", reason="Fixture checked"))]
                else:
                    calls = [("wait_event", {"timeout_seconds": 0.02})]
            elif previous[-1] == "update_task":
                calls = [("finish_team", {"reason": "Fixture completed"})]
            else:
                calls = [("get_team_state", {})]
        elif "terminal" not in previous and tool_choice != "none":
            assert "LEADER_ONLY_SENTINEL" not in json.dumps(messages)
            calls = [("terminal", {"command": "fixture_average"})]
        else:
            content = "Average 4; answer.json and pipeline.py."
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
                    "pipeline_path": "pipeline.py", "evidence": "Synthetic CSV inspection and fixed fixture computation.",
                    "unfinished": []}
            message["tool_calls"] = [{"id": "single-submit", "type": "function",
                "function": {"name": "submit", "arguments": json.dumps(args)}}]
        return Completion(message, "tool_calls" if "tool_calls" in message else "stop",
                          normalize_usage({}), 0.0, "scripted")


def smoke(output, *, mode="team", leader_mode=None):
    mode = resolve_mode(mode=mode)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    workspace = FixtureWorkspace(output / "fixture")
    client = SingleFixtureClient() if mode == "single" else FixtureClient()
    return run_task(FIXTURE_TASK, client=client, workspace=workspace, output=output / "attempt",
                    dataset=workspace.data, mode=mode, **({"leader_mode": leader_mode} if leader_mode is not None else {}))


def comparison_smoke(output, *, leader_mode="coordinator"):
    """Two independent synthetic attempts. Not a paid runner or efficacy study."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    summary = {"fixture_only": True, "evaluation": "not_run", "order": ["single", "team"], "arms": {}}
    write_json(output / "comparison.json", summary)
    contracts = []
    try:
        for mode in summary["order"]:
            response = smoke(output / mode, mode=mode, leader_mode=leader_mode if mode == "team" else "full")
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
