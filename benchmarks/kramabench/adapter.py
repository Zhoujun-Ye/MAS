"""KramaBench System API bridge backed by the generic Agent Team runtime."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from jsonschema import Draft202012Validator

from analysis.cache import summarize
from harness.accounting import estimate
from harness.agent import Observation, Tool
from harness.artifacts import MAX_ARTIFACT_BYTES, workspace_relative_path
from harness.catalog import catalog_manifest, fingerprint
from harness.config import source_digest
from harness.container_contract import validate_artifact_paths, validate_data_container
from harness.data_tools import inspection_tools
from harness.execution import ContainerWorkspace
from harness.json_utils import strict_loads
from harness.runner import write_json
from harness.session import comparison_session, resolve_mode
from harness.trace import Trace, activation_summary, communication_summary, read_trace, usage_summary, validate

from .roles import (ALL_TOOLS, ANSWER_SCHEMA, CATALOG_VERSION, LEADER_SYSTEM,
                    PROJECT_CONTEXT, SUBMISSION_SCHEMA, SUBMISSION_INSTRUCTIONS, TEMPLATES)
from .tasks import Task, UPSTREAM_COMMIT


def parse_submission(text):
    result = strict_loads(text, label="submission")
    if not isinstance(result, dict) or set(result) != {"answer", "pipeline_code", "evidence", "unfinished"}:
        raise ValueError("Expected answer, pipeline_code, evidence and unfinished")
    if (not isinstance(result["pipeline_code"], str) or not isinstance(result["evidence"], str)
            or not isinstance(result["unfinished"], list)
            or any(not isinstance(item, str) for item in result["unfinished"])):
        raise ValueError("Invalid submission types")
    if not Draft202012Validator(ANSWER_SCHEMA).is_valid(result["answer"]):
        raise ValueError("answer must contain only the requested scalar or list, not a diagnostic object")
    return result


def make_session(client, trace, workspace, *, mode=None, delegated=None, **limits):
    mode = resolve_mode(mode=mode, delegated=delegated)
    tools = tuple(workspace.tools()) + tuple(inspection_tools(workspace))
    if set(ALL_TOOLS) != {tool.name for tool in tools}:
        raise ValueError("Use ContainerWorkspace with retained output (archive_dir required)")
    if set(limits) - {"max_turns", "tool_budget", "max_workers", "max_activations", "max_parallel", "message_limit", "message_bytes", "worker_quantum", "leader_mode",
                       "session_model_calls", "session_tool_calls", "session_seconds", "audit_seconds"}:
        raise ValueError("Only budget/scheduling overrides are allowed; catalog and grants are fixed")
    def submit(args, agent):
        path = args["pipeline_path"]
        unresolved = path is None and args["answer"] is None and bool(args["unfinished"])
        if path is None and not unresolved:
            return Observation("A missing pipeline requires null answer and explicit unfinished work.",
                               {"error": True, "error_kind": "artifact_binding"})
        artifact = None
        try:
            if mode == "single":
                session.freeze_workspace()
            if path is not None:
                path = workspace_relative_path(path, workspace.workdir)
                record = session.frozen_files.get(path, {})
                if record.get("kind") != "file" or record.get("submission_status") != "hash_recorded":
                    raise ValueError("pipeline_path must name a regular file in frozen_files")
                budget = session.session_budget
                remaining = min(budget.remaining_audit_seconds(), budget.remaining_seconds())
                if remaining <= 0:
                    raise ValueError("No artifact export time remains")
                with budget.activity("audit"):
                    artifact = workspace.export_artifact(path, record["sha256"], timeout=remaining)
                if budget.remaining_audit_seconds() <= 0:
                    raise RuntimeError("Artifact export exceeded the audit allowance")
                if budget.remaining_seconds() <= 0:
                    raise ValueError("Artifact export exceeded the session deadline")
                data = artifact["content"].encode("utf-8")
                if (artifact["path"] != path or artifact["sha256"] != record["sha256"] or
                        hashlib.sha256(data).hexdigest() != record["sha256"] or artifact["bytes"] != len(data)
                        or len(data) > MAX_ARTIFACT_BYTES):
                    raise ValueError("Exported artifact does not match the freeze snapshot")
        except (ValueError, RuntimeError) as error:
            infrastructure = isinstance(error, RuntimeError)
            session.infra_affected |= infrastructure
            trace.emit("submission_artifact_binding", status="rejected", pipeline_path=path, error=str(error))
            return Observation(str(error), {"error": True, "error_kind": "artifact_export_transport" if infrastructure else "artifact_binding"})
        binding = dict(pipeline_path=path, pipeline_code_sha256=artifact["sha256"] if artifact else None,
                       bytes=artifact["bytes"] if artifact else 0,
                       status="exact_match" if artifact else "declared_unfinished",
                       trusted_pipeline_reexecution=False)
        trace.emit("submission_artifact_binding", **binding)
        session.submission_binding = binding
        parsed = parse_submission(json.dumps(dict(answer=args["answer"], pipeline_code=artifact["content"] if artifact else "",
                                                   evidence=args["evidence"], unfinished=args["unfinished"])))
        return Observation(json.dumps(dict(binding, submitted=True)),
                           submission_text=json.dumps(parsed, ensure_ascii=False))
    session = comparison_session(client, trace, TEMPLATES, tools, mode=mode,
        domain_tools=ALL_TOOLS, leader_system=LEADER_SYSTEM, workspace_root=workspace.workdir,
        project_context=PROJECT_CONTEXT,
        submission_tool=Tool("submit", "Submit the final answer and self-contained pipeline; call alone.",
                             SUBMISSION_SCHEMA,
                             submit),
        leader_final_prompt=SUBMISSION_INSTRUCTIONS,
        workspace_audit=workspace.audit_snapshot, **limits)
    session.submission_binding = None
    return session, catalog_manifest(TEMPLATES, tools)


def run_task(task, *, client, workspace, output, dataset, provenance=None, pricing=None,
             mode=None, delegated=None, expected_environment=None, comparison_sha256=None, **limits):
    """One immutable attempt, no retries or automatic evaluator. Client is explicit.

    Real clients require an inspected, existing Docker container. Scripted clients
    may inject a fake workspace, but their evidence is labelled fixture_only.
    """
    mode = resolve_mode(mode=mode, delegated=delegated)
    output = Path(output)
    fixture = client.cfg.model == "scripted"
    # Reject unsafe placement before even run_start can expose the original task.
    fixture_roots = (workspace.work,) if fixture and hasattr(workspace, "work") else ()
    validate_artifact_paths(dataset, output, workspace.archive_dir, work_roots=fixture_roots)
    if not fixture and not isinstance(workspace, ContainerWorkspace):
        raise ValueError("Real execution requires ContainerWorkspace")
    environment = {"fixture_only": True} if fixture else validate_data_container(workspace, dataset, output=output)
    if expected_environment is not None and environment != expected_environment:
        changed = sorted(key for key in set(environment) | set(expected_environment)
                         if environment.get(key) != expected_environment.get(key))
        raise ValueError("Environment changed after comparison preflight: " + ", ".join(changed))
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    session = outcome = submission = response = failure = None
    run_status = "error"
    stage = "setup"
    with Trace(output / "trace.jsonl", output.name) as trace:
        trace.emit("run_start", benchmark="kramabench", task=asdict(task), fixture_only=fixture)
        try:
            session, catalog = make_session(client, trace, workspace, mode=mode, **limits)
            manifest = {"benchmark": "kramabench", "upstream_commit": UPSTREAM_COMMIT,
                "provenance": provenance, "task": asdict(task), "source_digest": source_digest(),
                "task_origin": "provided_provenance" if provenance else "unverified_custom_query",
                "model": asdict(client.cfg), "catalog_version": CATALOG_VERSION, "catalog": catalog,
                "pricing": pricing,
                "comparison_sha256": comparison_sha256,
                "condition": mode, "mode": mode, "context_mode": session.context_mode,
                "task_completion_policy": getattr(session, "task_completion_policy", None),
                "team_arm": ("full_tool_leader" if session.leader_mode == "full" else "coordinator_only") if mode == "team" else None,
                "leader_domain_tools": sorted(set(session.leader.tools) & set(ALL_TOOLS)),
                "active_templates": list(session.templates), "domain_tools": list(ALL_TOOLS),
                "fixture_only": fixture,
                "leader_system": session.leader.messages[0]["content"],
                "leader_prefix_sha256": fingerprint(session.leader.messages[0]),
                "leader_system_chars": len(session.leader.messages[0]["content"]),
                "output_contract": {"response_format": session.leader.response_format,
                                    "artifact_policy": "selected_path_frozen_hash_v3", "max_artifact_bytes": MAX_ARTIFACT_BYTES,
                                    "submission_tool": "submit", "schema": SUBMISSION_SCHEMA,
                                    "final_tool_policy": "submit_only_auto_no_forced_named_tool",
                                    "final_prompt": session.leader_final_prompt, "parser": "path_request_to_strict_json_export_v2",
                                    "model_receipt": "path_hash_status_without_code"},
                "limits": {"leader_turns": session.leader.max_turns,
                    "leader_tools": session.leader.budget.limit,
                    "max_workers": session.max_workers,
                    "max_activations": session.max_activations,
                    "max_parallel": session.max_parallel if session.templates else 0,
                    "message_limit": session.mail.limit if mode == "team" else 0,
                    "message_bytes": session.mail.max_bytes if mode == "team" else 0,
                    "shared": session.session_budget.snapshot()}, "environment": environment,
                "evaluation": "not_run"}
            write_json(output / "manifest.json", manifest)
            stage = "execution"
            outcome = session.run(task.query)
            write_json(output / "outcome.json", asdict(outcome))
            stage = "submission_validation"
            if session.leader.submission is None:
                raise ValueError("No valid submit tool call was received")
            submission = parse_submission(outcome.text)
            stage = "artifact_export"
            write_json(output / "submission.json", submission)
            response = {"explanation": {"answer": submission["answer"]},
                        "pipeline_code": submission["pipeline_code"]}
            trace.emit("final", text=outcome.text, submission_sha256=fingerprint(submission))
            run_status = "completed" if outcome.status == "done" else "incomplete"
        except Exception as error:
            failure = error
            if hasattr(error, "session_outcome"):
                outcome = error.session_outcome
                write_json(output / "outcome.json", asdict(outcome))
            write_json(output / "failure.json", {"type": type(error).__name__, "message": str(error)})
        finally:
            trace.emit("run_end", status=run_status,
                       error_type=type(failure).__name__ if failure else None,
                       error=str(failure) if failure else None)
    events = read_trace(output / "trace.jsonl")
    usage = usage_summary(events)
    report = {"status": run_status, "mode": mode, "usage": usage, "cache": summarize([(mode, events)]),
              "communication": communication_summary(events),
              "activation_usage": activation_summary(events),
              "artifact_binding": getattr(session, "submission_binding", None),
              "integrity_errors": validate(events), "evaluation": "not_run",
              "submission_sha256": fingerprint(submission) if submission is not None else None,
              "fixture_only": fixture,
              "failure": {"type": type(failure).__name__, "message": str(failure)} if failure else None,
              "failure_stage": stage if failure else None,
              "submission_status": "valid" if submission is not None else "invalid" if stage == "submission_validation" else "not_produced",
              "outcome_status": outcome.status if outcome else None,
              "termination_reason": outcome.leader_status if outcome else getattr(failure, "kind", stage),
              "infra_affected": outcome.infra_affected if outcome else bool(failure),
              "budget": session.session_budget.snapshot() if session else None,
              "usage_complete": usage["total"]["usage_complete"],
              "cost_usd_estimate": 0.0 if fixture else estimate(events, pricing) if pricing else None,
              "known_usage_cost_usd_estimate": 0.0 if fixture else estimate(events, pricing, known_only=True) if pricing else None,
              "cost_usd_actual": 0.0 if fixture else None,
              "runtime": time.monotonic() - started}
    write_json(output / "report.json", report)
    if failure is not None:
        raise failure
    # This is the shape consumed by upstream Evaluator; export only, never import it.
    native = {"task_id": task.id, "model_output": response["explanation"], "code": response["pipeline_code"],
              "subresponses": [], "runtime": report["runtime"],
              "token_usage_sut": usage["total"]["prompt_tokens"] + usage["total"]["completion_tokens"],
              "token_usage_sut_input": usage["total"]["prompt_tokens"],
              "token_usage_sut_output": usage["total"]["completion_tokens"]}
    write_json(output / "native_response.json", native)
    if report["integrity_errors"]:
        raise RuntimeError("Trace integrity failed; see report.json")
    return response


class KramaBenchSystem:
    """Duck-types upstream System without importing its paid evaluation stack.

    Factory(dataset_directory, attempt_directory) returns an existing workspace;
    it must not mount evaluator/workload/solutions or host credentials.
    """
    name = "agent_team"

    def __init__(self, *, client, workspace_factory, output, domain, mode=None, delegated=None, **limits):
        self.client, self.workspace_factory = client, workspace_factory
        self.output, self.domain = Path(output), domain
        self.mode = resolve_mode(mode=mode, delegated=delegated)
        self.limits = limits
        self.name = "single_agent" if self.mode == "single" else "agent_team"
        self.dataset_directory = None

    def process_dataset(self, dataset_directory):
        dataset = Path(dataset_directory).resolve(strict=True)
        if not dataset.is_dir():
            raise ValueError("Expected a domain input directory")
        self.dataset_directory = dataset

    def serve_query(self, query, query_id, subset_files):
        if self.dataset_directory is None:
            raise ValueError("Call process_dataset first")
        if subset_files:
            raise ValueError("Oracle subsets are not supported in the full-lake condition")
        task = Task(query_id, self.domain, query)
        output = self.output / task.id
        if output.exists():
            raise FileExistsError(output)
        workspace = self.workspace_factory(self.dataset_directory, output)
        return run_task(task, client=self.client, workspace=workspace, output=output,
                        dataset=self.dataset_directory, mode=self.mode, **self.limits)
