"""Shared evidence, audit and budget ownership for Single and Team."""

from dataclasses import asdict, dataclass, field
import inspect

from .agent import Outcome, SessionBudget


@dataclass
class SessionOutcome(Outcome):
    leader_status: str
    member_statuses: dict
    reports: list
    errors: list
    tool_events: list
    infra_affected: bool
    budget: dict
    team_state: dict = field(default_factory=dict)


class Session:
    def __init__(self, client, trace, tools, *, session_model_calls=40,
                 session_tool_calls=80, session_seconds=900, audit_seconds=120,
                 workspace_audit=None):
        tools = tuple(tools)
        self.tools = {t.name: t for t in tools}
        if len(self.tools) != len(tools):
            raise ValueError("Duplicate tool name")
        if getattr(client.cfg, "retries", 0) and client.cfg.model != "scripted":
            raise ValueError("Use retries=0; paid retries require separate authorization")
        self.client, self.trace = client, trace
        self.session_budget = SessionBudget(session_model_calls, session_tool_calls, session_seconds, audit_seconds)
        self.workspace_audit = workspace_audit
        self.frozen_snapshot = None
        self.frozen_files = {}
        self.infra_affected = False
        self.started = False
        self.members = {}
        self.templates = {}
        self.errors = []
        self.reports = []
        try:
            self.audit_accepts_timeout = workspace_audit is not None and "timeout" in inspect.signature(workspace_audit).parameters
        except (TypeError, ValueError):
            self.audit_accepts_timeout = False

    def audit(self, phase, agent="leader", activation=0):
        prefix = "session_" if agent == "leader" else ""
        try:
            budget = self.session_budget
            remaining = budget.remaining_audit_seconds()
            if self.workspace_audit is not None and (remaining <= 0 or budget.remaining_seconds() <= 0):
                reason = "audit_time_limit" if remaining <= 0 else "session_time_limit"
                self.trace.emit(prefix + "workspace_audit_skipped", phase=phase, agent=agent, activation=activation, reason=reason)
                self.infra_affected |= remaining <= 0
                return
            if self.workspace_audit:
                with budget.activity("audit"):
                    snapshot = self.workspace_audit(**({"timeout": remaining} if self.audit_accepts_timeout else {}))
                self.infra_affected |= budget.remaining_audit_seconds() <= 0
            else:
                snapshot = None
            self.trace.emit(prefix + "workspace_snapshot", phase=phase, agent=agent, activation=activation,
                            attribution="shared_interval_not_exclusive", snapshot=snapshot,
                            enabled=self.workspace_audit is not None)
            return snapshot
        except Exception as error:
            self.infra_affected = True
            self.trace.emit(prefix + "workspace_audit_error", phase=phase, agent=agent,
                            activation=activation, error=str(error))

    def freeze_workspace(self):
        self.frozen_snapshot = self.audit("freeze")
        self.frozen_files = {p: dict(record, submission_status="hash_recorded" if record.get("kind") == "file" else "not_regular")
                             for p, record in (self.frozen_snapshot or {}).get("files", {}).items()}
        self.trace.emit("workspace_frozen_files", files=self.frozen_files)

    def result(self, leader, *, statuses=None, state=None):
        agents = [self.leader, *(m.agent for m in self.members.values())]
        events = [dict(e) for agent in agents for e in agent.tool_events]
        errors = [*self.errors, *(e for e in events if e.get("error"))]
        infra = self.infra_affected or any(e["error_kind"] == "execution_transport" for e in events)
        result = SessionOutcome(leader.text, "done" if leader.status == "done" else "incomplete", leader.turns,
                                leader.status, statuses or {}, list(self.reports), errors, events, infra,
                                self.session_budget.snapshot(), state or {})
        self.trace.emit("session_end", **asdict(result))
        return result


def resolve_mode(*, mode=None, delegated=None):
    if delegated is not None:
        raise ValueError("delegated is retired; choose explicit mode='single' or 'team'")
    if mode is not None and mode not in {"single", "team"}:
        raise ValueError("mode must be single or team; foreground mas is archived at f9c9a4a")
    return mode or "team"


def comparison_session(client, trace, templates, tools, *, mode=None, domain_tools, **kwargs):
    mode = resolve_mode(mode=mode)
    if mode == "single":
        from .single_agent import SingleAgent
        return SingleAgent(client, trace, tools, domain_tools=domain_tools, **kwargs)
    from .team import AgentTeam
    return AgentTeam(client, trace, templates, tools, domain_tools=domain_tools, **kwargs)
