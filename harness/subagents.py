"""Bounded parallel delegation with persistent, capability-limited children."""

from dataclasses import asdict, dataclass
import json
import threading
import inspect
from jsonschema import Draft202012Validator

from .agent import Agent, Budget, Observation, Outcome, SessionBudget, SessionLimit, Tool, parse_tool_arguments
from .llm import ProviderError


DELEGATION_POLICY = (
    " Delegate concrete work packages: exploration, implementation, calculation, repair, or independent checks. "
    "Children can own substantive task work, not just review work you have already completed. "
    "Before doing the main implementation yourself, identify useful bounded deliverables and their dependencies. "
    "When delegation is useful, assign ownership early, after only the orientation needed to write a local brief; "
    "do not first solve the whole task and then delegate its repetition. Small or tightly coupled work may be "
    "faster directly; do not create work merely to fill a role roster. "
    "Use existing reports and artifacts to identify what is already known before assigning more work; "
    "do not commission another broad discovery pass when usable source locations and evidence already exist. "
    "Each local brief should state the objective, known evidence with paths/versions and checked scope, "
    "assumptions still unverified, acceptance criteria, exclusions, dependencies, deliverable and write ownership. "
    "Assign one owner per deliverable, either yourself or a child. Choose templates by required capability, "
    "not by a mandatory role sequence. Dispatch independent ready work packages together; wait for prerequisites "
    "before assigning dependent work. This foreground runtime waits for the batch; you cannot do concurrent "
    "leader work while it runs. Give parallel children distinct deliverables or source partitions and disjoint "
    "write locations. Integrate their artifacts rather than reimplementing completed work. "
    "Execution owners should validate their own work. Add a separate reviewer only for a concrete risk, "
    "uncertainty or requested assurance; successful work does not automatically require another full rerun. "
    "Separate the implementation owner from reviewers; when overlap is intentional, name its verification purpose. "
    "For an independent check, provide raw source locations and necessary task constraints, but withhold the "
    "candidate answer and distinguish required constraints from the author's chosen method. "
    "Re-reading raw evidence and recomputing are allowed when needed for that check; avoiding duplication "
    "must not mean trusting an unsupported report. "
    "Integrate by comparing claims and evidence. Recompute or revise when evidence is missing, conflicting, "
    "stale, or a change needs validation, rather than automatically replaying every child workflow. "
    "Resume the same child for a follow-up on its scope, supplying only the new question and changed evidence. "
    "Request a concise summary of the assigned work, not a full work log. "
    "Inspect referenced details selectively when needed to resolve a question, rather than requesting full dumps by default. "
    "Choose direct work or delegation as useful; no mandatory sequence or number of children."
)
CHILD_SCOPE_POLICY = (
    "Own the local objective and declared deliverable. For execution work, implement, run and validate the "
    "assigned result with your granted tools; do not stop at advice or a review when an artifact is requested. "
    "Respect assigned write ownership and report missing prerequisites rather than duplicating another owner's work. "
    "Reuse provided source locations and existing "
    "artifacts as starting points, not as proof of correctness. Do not restart broad exploration unless "
    "sources are missing, inadequate, conflicting or stale; report why expansion is needed. "
    "If assigned an independent check, read the raw evidence and recompute what that check requires. "
    "On resume, retain prior checked results and focus on the new question or changed evidence. "
    "Distinguish independently checked facts from supplied assumptions and unverified claims."
)
CHILD_REPORT_POLICY = (
    "Your final reply is the summary returned to the leader. Give a concise natural-language summary "
    "that answers the assigned question. Include relevant evidence references and disclose material "
    "uncertainty, failures or unfinished work. Choose the format and length appropriate to the task. "
    "Do not paste full tables, logs, scripts or a chronological work diary. "
    "During work, save detailed data and reproducible artifacts to the assigned location only when "
    "your granted tools permit writing. Do not defer saving until a tools-disabled final call. "
    "If writing is unavailable, cite existing accessible sources and report any unsaved detail; "
    "never invent an artifact path or claim a file was saved. "
    "On resume, summarize what changed plus the current conclusion and remaining blockers, "
    "rather than repeating the previous report. No separate summarization call is needed."
)


@dataclass(frozen=True)
class SubagentTemplate:
    name: str
    description: str
    system: str
    tools: tuple[str, ...] = ()
    max_turns: int = 20
    tool_budget: int = 40

    def __post_init__(self):
        object.__setattr__(self, "tools", tuple(self.tools))
        if not self.name or self.max_turns < 1 or self.tool_budget < 0:
            raise ValueError("Invalid subagent template or limits")


@dataclass
class SessionOutcome(Outcome):
    leader_status: str
    child_statuses: dict[str, str]
    delegations: list[dict]
    errors: list[dict]
    tool_events: list[dict]
    infra_affected: bool
    budget: dict


class LeaderSubagent:
    """One leader, bounded parallel children, no implicit transcript sharing.

    Tool implementations are trusted application code. Allowlisting tools is not
    a filesystem sandbox: a permitted shell can read anything its OS user can.
    """

    def __init__(self, client, trace, templates, tools=(), *, leader_tools=(),
                 allowed_tools=None, project_context="", leader_system=None,
                 max_turns=40, tool_budget=80, max_subagents=8, max_delegations=16,
                 max_parallel=4, session_model_calls=40, session_tool_calls=80,
                 workspace_audit=None, session_seconds=900, audit_seconds=120,
                 leader_response_format=None, leader_final_prompt=None, submission_tool=None):
        templates = tuple(templates)
        tools = tuple(tools)
        leader_tools = tuple(leader_tools)
        self.templates = {t.name: t for t in templates}
        self.mode = "mas" if templates else "single"
        self.context_mode = "brief_only" if templates else "full_task_and_own_history"
        self.tools = {t.name: t for t in tools}
        if len(self.templates) != len(templates) or len(self.tools) != len(tools):
            raise ValueError("Duplicate template or tool name")
        if "delegate" in self.tools:
            raise ValueError("delegate is reserved for the runtime")
        if submission_tool is not None and (submission_tool.name in self.tools or submission_tool.name == "delegate"
                                            or submission_tool.budgeted or submission_tool.concurrent):
            raise ValueError("Submission must be a distinct unbudgeted, serial root tool")
        allowed = set(self.tools if allowed_tools is None else allowed_tools)
        requested = set(leader_tools) | {name for t in templates for name in t.tools}
        if not requested <= allowed or not allowed <= self.tools.keys():
            raise ValueError("Tool grants must be registered and permitted by the session")
        if min(max_turns, max_subagents, max_delegations, max_parallel) < 1 or tool_budget < 0:
            raise ValueError("Invalid session limits")
        if getattr(client.cfg, "retries", 0) and client.cfg.model != "scripted":
            raise ValueError("Use retries=0; paid retries require separate authorization")
        self.client, self.trace = client, trace
        self.project_context = project_context
        self.max_subagents, self.max_delegations = max_subagents, max_delegations
        self.children = {}
        self.child_templates = {}
        self.child_status = {}
        self.reports = []
        self.delegations = 0
        self.fatal_error = None
        self.provider_errors = []
        self.started = False
        self.lock = threading.Lock()
        self.infra_affected = False
        self.max_parallel = max_parallel
        self.session_budget = SessionBudget(session_model_calls, session_tool_calls, session_seconds, audit_seconds)
        self.next_child_id = 1
        self.preassigned = {}
        self.workspace_audit = workspace_audit
        self.leader_final_prompt = leader_final_prompt or "Return the final answer and identify any unverified or incomplete work."
        try:
            self.audit_accepts_timeout = workspace_audit is not None and "timeout" in inspect.signature(workspace_audit).parameters
        except (TypeError, ValueError):
            self.audit_accepts_timeout = False
        catalog = "\n".join(
            f"- {t.name}: {t.description}; tools={list(t.tools)}; "
            f"max_turns={t.max_turns}; lifetime_tool_budget={t.tool_budget}"
            for t in templates)
        system = leader_system or (
            "You are the leader. Solve the user's task using authorized tools. "
            "Return the final answer with evidence, changes and unverified or incomplete work. "
            "Tool errors are observations, not correctness verdicts."
        )
        if templates:
            system += DELEGATION_POLICY
            system += "\nSubagents:\n" + catalog
        limits = (f"\nSession model-call limit: {session_model_calls}; session budgeted-tool limit: {session_tool_calls}. "
                  f"Session execution time limit: {session_seconds} seconds (audit-only time excluded). "
                  "One model call is reserved for the leader's final report. Each accepted delegation reserves "
                  "one report call within the same shared limit. Limits do not reset on resume.")
        if templates:
            limits += (f" Maximum children: {max_subagents}; maximum delegations including resumes: {max_delegations}; "
                       f"maximum parallel children: {max_parallel}. Multiple delegate calls in one reply run concurrently; "
                       "shared files can change during execution. Avoid overlapping writes.")
        self.session_limits_prompt = (f"\nSession model-call limit: {session_model_calls}; "
                                      f"session budgeted-tool limit: {session_tool_calls}. "
                                      f"Session execution time limit: {session_seconds} seconds (audit-only time excluded). "
                                      "One model call is reserved for the leader and one for this invocation's report. "
                                      "When unreserved calls run out, use your reserved call to report without tools. "
                                      "Shared limits do not reset on resume.")
        schema = {"type": "object", "properties": {
            "template": {"type": "string", "enum": list(self.templates)},
            "task": {"type": "string", "minLength": 1},
            "context": {"type": "string"},
            "resume_id": {"type": "string", "pattern": "^subagent-[1-9][0-9]*$"},
        }, "required": ["template", "task"], "additionalProperties": False}
        delegate = Tool("delegate", "Run a subtask and return its report; optionally resume its agent_id.",
                        schema, self._delegate, concurrent=True)
        self.leader = Agent("leader", client, trace,
                            system + limits + "\n\n" + project_context,
                            tools=[self.tools[n] for n in leader_tools] + ([delegate] if templates else [])
                                  + ([submission_tool] if submission_tool else []),
                            budget=Budget(tool_budget), max_turns=max_turns,
                            usage_role="leader" if templates else "single",
                            session_budget=self.session_budget, max_concurrent_tools=max_parallel,
                            response_format=leader_response_format,
                            submission_tool=submission_tool.name if submission_tool else None)
        self.leader.before_tools = self._prepare_calls

    def _prepare_calls(self, calls):
        """Allocate identities in provider call order, before worker scheduling."""
        assigned = {}
        validator = Draft202012Validator(self.leader.tools["delegate"].parameters) if "delegate" in self.leader.tools else None
        with self.lock:
            for call in calls:
                if call["function"]["name"] != "delegate" or validator is None:
                    continue
                try:
                    args = parse_tool_arguments(call["function"].get("arguments"))
                except (ValueError, TypeError):
                    continue
                if validator.is_valid(args) and "resume_id" not in args:
                    assigned[call["id"]] = f"subagent-{self.next_child_id}"
                    self.next_child_id += 1
            self.preassigned = assigned

    def _reserve(self, args, assigned_id=None):
        if self.fatal_error is not None:
            return Observation("Delegation stopped after a fatal provider error.", {"error": True, "error_kind": "session_stopped"})
        if self.delegations >= self.max_delegations:
            return Observation("Session delegation limit reached.", {"error": True, "error_kind": "delegation_limit"})
        template = self.templates[args["template"]]
        child_id = args.get("resume_id")
        if "resume_id" in args:
            if self.child_templates.get(child_id) != template.name:
                return Observation("Unknown child or mismatched template.", {"error": True, "error_kind": "invalid_resume"})
            if self.child_status[child_id] == "running":
                return Observation("This child is already running; wait for its report before resuming.",
                                   {"error": True, "error_kind": "child_busy"})
            if self.child_status[child_id] in {"provider_error", "context_length", "execution_error", "stopped_after_fatal", "session_time_limit"}:
                return Observation("Failed child cannot be resumed in this session.", {"error": True, "error_kind": "failed_child"})
            child = self.children[child_id]
            if not self.session_budget.reserve_report(child_id):
                return Observation("Delegation rejected: no model call remains to reserve its report.",
                                   {"error": True, "error_kind": "report_reservation_unavailable"})
        else:
            if len(self.children) >= self.max_subagents:
                return Observation("Session subagent limit reached.", {"error": True, "error_kind": "subagent_limit"})
            child_id = assigned_id
            if child_id is None:
                child_id = f"subagent-{self.next_child_id}"
                self.next_child_id += 1
            if not self.session_budget.reserve_report(child_id):
                return Observation("Delegation rejected: no model call remains to reserve its report.",
                                   {"error": True, "error_kind": "report_reservation_unavailable"})
            child = Agent(child_id, self.client, self.trace,
                          template.system + "\nYou receive only the delegated local task, not the parent's conversation or original task. "
                          "The leader sees your final report, not your complete tool transcript. "
                          "You cannot delegate or expand tool permissions. Shared files may change concurrently."
                          + self.session_limits_prompt + "\n\n" + self.project_context + "\n" + CHILD_SCOPE_POLICY
                          + "\n" + CHILD_REPORT_POLICY,
                          tools=[self.tools[n] for n in template.tools],
                          budget=Budget(template.tool_budget), max_turns=template.max_turns,
                          usage_role=template.name, session_budget=self.session_budget)
            self.children[child_id] = child
            self.child_templates[child_id] = template.name
        self.delegations += 1
        self.child_status[child_id] = "running"
        return child_id, child, template

    def _audit(self, phase, child_id, invocation, *, scope="delegation"):
        prefix = "session_" if scope == "session" else ""
        try:
            remaining = self.session_budget.remaining_seconds()
            if self.workspace_audit is not None and remaining <= 0:
                self.trace.emit(prefix + "workspace_audit_skipped", phase=phase, agent=child_id,
                                invocation=invocation, reason="session_time_limit")
                return
            audit_remaining = self.session_budget.remaining_audit_seconds()
            if self.workspace_audit is not None and audit_remaining <= 0:
                self.infra_affected = True
                self.trace.emit(prefix + "workspace_audit_skipped", phase=phase, agent=child_id,
                                invocation=invocation, reason="audit_time_limit")
                return
            options = {"timeout": audit_remaining} if self.audit_accepts_timeout else {}
            if self.workspace_audit:
                with self.session_budget.activity("audit"):
                    snapshot = self.workspace_audit(**options)
                if self.session_budget.remaining_audit_seconds() <= 0:
                    self.infra_affected = True
            else:
                snapshot = None
            self.trace.emit(prefix + "workspace_snapshot", phase=phase, agent=child_id, invocation=invocation,
                            attribution="shared_interval_not_exclusive", snapshot=snapshot,
                            enabled=self.workspace_audit is not None)
        except Exception as error:
            self.infra_affected = True
            self.trace.emit(prefix + "workspace_audit_error", phase=phase, agent=child_id,
                            invocation=invocation, error=str(error))

    def _delegate(self, args, leader):
        call_id = leader.active_tool_call_id if leader is not None else None
        with self.lock:
            reserved = self._reserve(args, self.preassigned.get(call_id))
            invocation = self.delegations
        if isinstance(reserved, Observation):
            reserved.text = json.dumps(dict(status="rejected", report=reserved.text,
                                           error_kind=reserved.meta.get("error_kind"), usage=self._usage()), ensure_ascii=False)
            return reserved
        child_id, child, template = reserved
        before_calls, before_tools, before_budget = child.model_calls, child.tool_calls, child.budget.used
        prompt = json.dumps({"task": args["task"], "context": args.get("context", "")}, ensure_ascii=False)
        self.trace.emit("delegation_start", agent=child_id, template=template.name,
                        resume=bool(args.get("resume_id")), prompt=prompt, invocation=invocation, call_id=call_id)
        pending_error = None
        try:
            self._audit("before", child_id, invocation)
            outcome = child.run(prompt, CHILD_REPORT_POLICY)
            status = ("completed" if outcome.status == "done" else outcome.status
                      if outcome.status in {"stopped_after_fatal", "session_time_limit"} else "partial")
            report = dict(agent_id=child_id, status=status, outcome=outcome.status, report=outcome.text)
        except SessionLimit as error:
            status = str(error)
            report = dict(agent_id=child_id, status=status, outcome=status, report="Session stopped before this invocation completed.")
        except ProviderError as error:
            self.provider_errors.append(error)
            if error.kind != "context_length":
                self.infra_affected = True
            status = "context_length" if error.kind == "context_length" else "provider_error"
            report = dict(agent_id=child_id, status=status, error_kind=error.kind, report=str(error))
            if error.fatal:
                self.fatal_error = error
                self.session_budget.stop(error)
                pending_error = error
        except Exception as error:
            self.infra_affected = True
            status = "execution_error"
            report = dict(agent_id=child_id, status="execution_error", error_kind="execution_error", report=str(error))
        finally:
            self.session_budget.release_report(child_id)
            self._audit("after", child_id, invocation)
        report.update(invocation=invocation, call_id=call_id,
                      usage=self._usage(child.model_calls-before_calls, child.tool_calls-before_tools,
                                        child.budget.used-before_budget))
        with self.lock:
            self.trace.emit("delegation_end", **report)
            self.reports.append(report)
            self.child_status[child_id] = status
        if pending_error is not None:
            raise pending_error
        return Observation(json.dumps(report, ensure_ascii=False), {"child_status": status})

    def _usage(self, model_calls=0, tool_calls=0, budgeted_tool_calls=0):
        shared = self.session_budget.snapshot()
        return dict(model_calls=model_calls, tool_calls=tool_calls, budgeted_tool_calls=budgeted_tool_calls,
                    session_model_calls_remaining=shared["model_calls_remaining"],
                    session_model_calls_unreserved=shared["model_calls_unreserved"],
                    session_tool_calls_remaining=shared["tool_calls_remaining"],
                    reserved_report_calls=shared["leader_reserved_calls"] + shared["child_reserved_calls"],
                    scope="invocation; shared counts are a concurrent snapshot, not an allocation")

    def run(self, task):
        if self.started:
            raise ValueError("A session can only be run once")
        self.started = True
        self.session_budget.start()
        self.trace.emit("session_config", templates=[asdict(t) for t in self.templates.values()],
                        max_subagents=self.max_subagents if self.templates else 0,
                        max_delegations=self.max_delegations if self.templates else 0,
                        max_parallel=self.max_parallel if self.templates else 0,
                        budget=self.session_budget.snapshot(),
                        mode=self.mode, context_mode=self.context_mode, fork=False,
                        leader_response_format=self.leader.response_format,
                        submission_tool=self.leader.submission_tool,
                        leader_final_prompt=self.leader_final_prompt)
        try:
            self._audit("before", "leader", 0, scope="session")
            try:
                leader = self.leader.run(task, self.leader_final_prompt)
            finally:
                self.session_budget.release_report("leader")
                self._audit("after", "leader", 0, scope="session")
        except ProviderError as error:
            if error.kind != "context_length":
                self.infra_affected = True
            turns = sum(message["role"] == "assistant" for message in self.leader.messages)
            from_child = any(error is source for source in self.provider_errors)
            result = self._result(Outcome("", "aborted" if from_child else error.kind, turns))
            if not from_child:
                result.errors.append(dict(agent_id="leader", status="context_length" if error.kind == "context_length" else "provider_error",
                                          error_kind=error.kind, report=str(error)))
            self.trace.emit("session_end", **asdict(result))
            error.session_outcome = result
            raise
        result = self._result(leader)
        self.trace.emit("session_end", **asdict(result))
        return result

    def _result(self, leader):
        reports = [dict(report) for report in self.reports]
        tool_events = [dict(event) for agent in [self.leader, *self.children.values()]
                       for event in agent.tool_events]
        rejected = [dict(event, status="rejected") for event in self.leader.tool_events
                    if event["tool"] == "delegate" and event["error"]]
        reports.extend(rejected)
        errors = [report for report in reports if "error_kind" in report]
        errors.extend(event for event in tool_events if event["error"]
                      and not (event["agent_id"] == "leader" and event["tool"] == "delegate"))
        complete = leader.status == "done"
        infra = self.infra_affected or any(event["error_kind"] == "execution_transport"
                                         for event in tool_events)
        return SessionOutcome(leader.text, "done" if complete else "incomplete", leader.turns,
                              leader.status, dict(self.child_status), reports, errors, tool_events,
                              infra, self.session_budget.snapshot())


def resolve_mode(*, mode=None, delegated=None):
    """Explicit mode with a backwards-compatible delegated boolean."""
    if mode is not None and mode not in {"single", "mas"}:
        raise ValueError("mode must be single or mas")
    if delegated is not None and type(delegated) is not bool:
        raise ValueError("delegated must be boolean")
    legacy = None if delegated is None else "mas" if delegated else "single"
    if mode is not None and legacy is not None and mode != legacy:
        raise ValueError("Conflicting mode and delegated settings")
    return mode or legacy or "mas"


def comparison_session(client, trace, templates, tools, *, delegated=None, mode=None, domain_tools, **kwargs):
    """Explicit common grants and ceilings for leader-only / delegated arms."""
    if "leader_tools" in kwargs or "allowed_tools" in kwargs:
        raise ValueError("Use domain_tools as the explicit common grant")
    mode = resolve_mode(mode=mode, delegated=delegated)
    domain_tools = tuple(domain_tools)
    calls, actions = kwargs.get("session_model_calls", 40), kwargs.get("session_tool_calls", 80)
    kwargs.setdefault("max_turns", calls)
    kwargs.setdefault("tool_budget", actions)
    if kwargs["max_turns"] < calls or kwargs["tool_budget"] < actions:
        raise ValueError("Comparison root limits must allow the full shared session budget")
    if mode == "single":
        from .single_agent import SingleAgent
        return SingleAgent(client, trace, tools, domain_tools=domain_tools, **kwargs)
    templates = tuple(templates)
    if not templates:
        raise ValueError("MAS comparison requires at least one fixed template")
    return LeaderSubagent(client, trace, templates, tools,
                          leader_tools=domain_tools, allowed_tools=domain_tools, **kwargs)
