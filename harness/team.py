"""Leader-led, bounded asynchronous execution with persistent peer mailboxes."""

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
import json
from pathlib import PurePosixPath
import threading
import time

from .agent import Agent, Budget, ModelDeferred, Observation, Outcome, SessionLimit, Tool
from .llm import ProviderError
from .messaging import Mailboxes
from .session import Session


LEADER_POLICY = """
You lead an asynchronous team. Choose fixed capability templates and assign local
tasks with spawn_worker or assign_task; these return handles, not completed results.
Prioritize organizing collaboration, resolving conflicting evidence, integrating
results and delivering the overall task. Arrange checks and repairs before closure.
For delegated verification, assign a Worker to run the saved file and compare its
observed output with the requirements; collect that report before finish_team.
Actively look for a meaningful multi-member decomposition before assigning work.
Prefer complementary specialists with distinct deliverables and explicit interfaces
or dependencies. Run independent work concurrently and have collaborators exchange
needed information directly. Do not default to a single end-to-end owner. Use one
member only when no useful split fits the task and available capacity, and record
that reason in your brief. Do not create duplicate work merely to fill roles.
Only you can assign, accept, reopen or cancel tasks. Use current task revisions for
updates. Only a Worker's explicit completed claim on a normally returned assignment
unblocks dependencies; accept is optional and is not a correctness verdict.
Plain final text is an unclaimed handoff, not task completion. Workers can message each other directly.
Use wait_event to wait for mail without occupying an execution slot. All messages
wake idle recipients with their existing template permissions, subject to shared
admission limits. Risks, milestones, blockers and handoffs notify you automatically.
Call finish_team alone before submitting. This stops new work, drains admitted
operations and freezes the workspace. The closing state lists frozen file paths,
hashes and submission availability. Select a path from that inventory to submit.
The runtime reads only that selected file and checks its frozen hash; do not copy
code into the submission. A repeated indefinite wait with no possible progress
source after a stall notice triggers draining so final submission remains possible.
After closure only team-state/message reads and final submission are permitted.
"""

WORKER_POLICY = """
You are a persistent team member. Execute your assigned local task using your
template's tools. Only the Leader changes assignments; do not spawn members or
change permissions. get_team_state lists members and tasks. send_message addresses
another member directly, including an idle member. needs_reply tracks a requested
response; reply_to links an answer. Both info and requests wake idle recipients.
Risk/milestone messages also reach the Leader. report_status reports progress or
blocks and yields; wait_event yields until mail or a requested timeout. Your final
reply becomes a handoff to the Leader, but does not claim task completion. End an
assignment with finish_task(status, summary), choosing completed, partial, blocked
or failed. completed is your claim, not verified correctness. report_status(blocked)
waits for help; finish_task(blocked) returns the assignment with an unresolved blocker.
During message activations, reply normally; they cannot complete a pending assignment.
Messages can activate you even while your assignment waits on dependencies, with
unchanged permissions. This does not start or release that pending assignment.
Your context contains shared project instructions, local assignments, your own
history and explicit messages, not the Leader's history. Domain tools, model calls
and communication have shared ceilings. Messaging does not consume domain calls.
"""

REPORT_POLICY = "Return your result and unfinished work. For an active assignment, use finish_task to declare its status when tools are available; plain text alone does not claim completion. If instructed to return a final text-only report, describe partial work without tools."


@dataclass
class Member:
    agent: Agent
    template: str
    state: str = "idle"
    task_id: str | None = None
    assignment_revision: int = 0
    activation: int = 0
    active: bool = False
    cause: str = "assignment"
    wait_until: float | None = None
    audited: bool = False
    before: tuple = (0, 0, 0)
    trigger_message_ids: tuple = ()
    pending_task_id: str | None = None
    previous_task_id: str | None = None
    declaration: dict | None = None


def schema(properties=None, required=()):
    return dict(type="object", properties=properties or {}, required=list(required), additionalProperties=False)


TEXT = {"type": "string", "minLength": 1}


class AgentTeam(Session):
    def __init__(self, client, trace, templates, tools=(), *, domain_tools=None,
                 project_context="", leader_system=None, leader_final_prompt=None,
                 leader_response_format=None, submission_tool=None, max_turns=None,
                 tool_budget=None, max_workers=8, max_activations=None, max_parallel=4,
                 message_limit=128, message_bytes=8192, leader_mode="coordinator", workspace_root="/workspace", **kwargs):
        super().__init__(client, trace, tools, **kwargs)
        templates = tuple(templates)
        self.templates = {t.name: t for t in templates}
        if not templates or len(self.templates) != len(templates):
            raise ValueError("A team requires distinct fixed templates")
        grants = set(self.tools if domain_tools is None else domain_tools)
        if not grants <= self.tools.keys() or any(not set(t.tools) <= grants for t in templates):
            raise ValueError("Template tools must be within the session capability ceiling")
        if max_activations is None:
            max_activations = self.session_budget.model_limit
        if min(max_workers, max_activations, max_parallel) < 1:
            raise ValueError("Invalid team limits")
        self.mode, self.context_mode = "team", "local_briefs_and_explicit_messages"
        self.task_completion_policy = "explicit_claim_v1"
        self.max_workers, self.max_activations, self.max_parallel = max_workers, max_activations, max_parallel
        self.project_context = project_context
        if leader_mode not in {"full", "coordinator"}:
            raise ValueError("leader_mode must be full or coordinator")
        self.leader_mode = leader_mode
        self.workspace_root = workspace_root
        self.condition = threading.Condition(threading.RLock())
        self.mail = Mailboxes(trace, limit=message_limit, max_bytes=message_bytes)
        self.tasks = {}
        self.phase = "open"
        self.activations = 0
        self.ready = deque()
        self.futures = {}
        self.root_waiting = False
        self.root_deadline = None
        self.root_outcome = None
        self.pending_error = None
        self.close_reason = None
        self.undelivered = {}
        self.deadlock_notified = False
        self.leader_final_prompt = leader_final_prompt or "Return the final answer and unfinished work after team closure."
        common = self._controls(leader=False)
        self.worker_controls = common
        root_controls = self._controls(leader=True)
        reserved = {t.name for t in [*common, *root_controls]}
        if reserved & grants or "delegate" in grants:
            raise ValueError("Domain tools collide with reserved team controls")
        if submission_tool and (submission_tool.name in self.tools or submission_tool.name in reserved or
                                submission_tool.budgeted or submission_tool.concurrent):
            raise ValueError("Submission must be a distinct unbudgeted serial root tool")
        budget = self.session_budget
        if (max_turns is not None and max_turns < budget.model_limit) or (tool_budget is not None and tool_budget < budget.tool_limit):
            raise ValueError("Root limits must allow the full shared session budget")
        catalog = json.dumps([dict(name=t.name, description=t.description, tools=t.tools) for t in templates])
        leader_policy = ("You have the session's full domain tools; you may perform domain work as well as delegate it." if leader_mode == "full" else
                         "You have no domain tools. Delegate all domain work, including discovery, implementation, "
                         "integration, verification and repairs, to Workers. Do not ask for code to inspect yourself.")
        self.leader = Agent("leader", client, trace,
            (leader_system or "Coordinate completion of the user's task.") + LEADER_POLICY + "\n" + leader_policy +
            "\nFixed templates: " + catalog + "\n" + project_context,
            tools=([self.tools[n] for n in sorted(grants)] if leader_mode == "full" else []) + root_controls +
                  ([submission_tool] if submission_tool else []),
            budget=Budget(tool_budget if tool_budget is not None else budget.tool_limit), max_turns=max_turns or budget.model_limit,
            usage_role="leader", session_budget=budget, response_format=leader_response_format,
            submission_tool=submission_tool.name if submission_tool else None)
        self.leader.tool_gate = self._gate

    def _controls(self, *, leader):
        def control(name, description, properties, required, fn, sole=False):
            def invoke(args, agent):
                with self.condition:
                    denial = self._gate(agent.tools[name], args, agent)
                    if denial is not None:
                        return denial
                    result = fn(args, agent)
                    self.condition.notify_all()
                    return Observation(json.dumps(result, ensure_ascii=False))
            return Tool(name, description + (" Call alone; a mixed batch is refused." if sole else ""),
                        schema(properties, required), invoke, sole=sole)
        controls = [
            control("send_message", "Send directly to one member. Risks/milestones also notify the Leader. Queued is not read.",
                dict(to=TEXT, content=TEXT, kind={"enum": ["question", "answer", "info", "risk", "milestone"]},
                     task_id=TEXT, reply_to=TEXT, needs_reply={"type": "boolean", "description":
                         "Set true when a response is needed, including review requests. Default false. This tracks replies only; all messages wake idle members."}),
                ("to", "content"), self._send),
            control("get_team_state", "Read member IDs, task versions, dependencies and shared remaining budgets.", {}, (),
                    lambda args, agent: self.state()),
            control("read_messages", "Read a bounded page of recorded mail; Leader can inspect all, Workers only their own.",
                dict(offset={"type": "integer", "minimum": 0}, limit={"type": "integer", "minimum": 1, "maximum": 8}), (),
                lambda args, agent: self.mail.read(agent.name, args.get("offset", 0), args.get("limit", 8))),
            control("resolve_request", "Requester or Leader records why a peer question is resolved or no longer needed.",
                dict(message_id=TEXT, reason=TEXT), ("message_id", "reason"), self._resolve),
            control("wait_event", "Yield until new mail/state or timeout; call alone, not a polling loop.",
                dict(timeout_seconds={"type": "number", "minimum": 0.01, "description": "Optional timeout; omit to wait for an event within the session deadline."}), (), self._wait, sole=True),
        ]
        if not leader:
            controls.append(control("report_status", "Report meaningful progress or a blocker on your owned task; blocked yields.",
                dict(status={"enum": ["progress", "blocked"]}, summary=TEXT), ("status", "summary"), self._report_status, sole=True))
            controls.append(control("finish_task", "Return the current assignment with an explicit status claim, not a verification verdict. Unavailable during message-only work.",
                dict(status={"enum": ["completed", "partial", "blocked", "failed"]}, summary=TEXT),
                ("status", "summary"), self._finish_task, sole=True))
            return controls
        task_fields = dict(task=TEXT, context={"type": "string"}, write_scope={"type": "string", "description":
                           "Workspace directory, e.g. producer or /workspace/producer. Omit for a distinct default."},
                           depends_on={"type": "array", "items": TEXT, "uniqueItems": True})
        controls += [
            control("spawn_worker", "Create a persistent fixed-capability worker and assign local work; returns handles immediately.",
                dict(template={"enum": list(self.templates)}, **task_fields), ("template", "task"), self._spawn),
            control("assign_task", "Assign new work to an idle member, preserving history and lifetime tools.",
                dict(worker_id=TEXT, **task_fields), ("worker_id", "task"), self._assign),
            control("update_task", "Leader accepts a reported result, reopens its owner for repair, or cancels. Use current state revision.",
                dict(task_id=TEXT, expected_revision={"type": "integer", "minimum": 1},
                     action={"enum": ["accept", "reopen", "cancel"]}, reason=TEXT),
                ("task_id", "expected_revision", "action", "reason"), self._update),
            control("finish_team", "Irreversibly stop new work, drain admitted actions and collect closing evidence before submitting.",
                dict(reason=TEXT), ("reason",), self._finish, sole=True),
        ]
        return controls

    def _notice(self, content, kind="event", task_id=None):
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        self.mail.send("runtime", "leader", text, kind=kind, task_id=task_id, control=True)
        self.condition.notify_all()

    def _touch(self, task, event, actor):
        self.deadlock_notified = False
        task["revision"] += 1
        self.trace.emit("team_task", event=event, actor=actor, task=dict(task))

    def _write_scope(self, scope, fallback):
        from .artifacts import workspace_relative_path
        return workspace_relative_path(scope or fallback, self.workspace_root)

    def _new_task(self, worker_id, args):
        dependencies = args.get("depends_on", [])
        if any(d not in self.tasks for d in dependencies):
            raise ValueError("Unknown dependency task")
        task_id = f"task-{len(self.tasks) + 1}"
        scope = self._write_scope(args.get("write_scope"), worker_id + "/" + task_id)
        for other in self.tasks.values():
            owner = self.members.get(other["owner"])
            if other["status"] not in {"reported", "accepted", "cancelled", "failed"} or owner and owner.active:
                a, b = PurePosixPath(scope), PurePosixPath(other["write_scope"])
                if a == b or a in b.parents or b in a.parents:
                    raise ValueError("Write scope overlaps another outstanding assignment")
        task = dict(task_id=task_id, owner=worker_id, objective=args["task"], context=args.get("context", ""),
                    depends_on=list(dependencies), write_scope=scope, status="assigned", revision=1,
                    specification_revision=1, result_revision=0, report=None, outcome=None, completion_status=None)
        self.trace.emit("team_task", event="created", actor="leader", task=dict(task))
        self.tasks[task_id] = task
        self.deadlock_notified = False
        return task

    def _spawn(self, args, actor):
        if len(self.members) >= self.max_workers:
            raise ValueError("Worker identity limit reached")
        worker_id = f"worker-{len(self.members) + 1}"
        template = self.templates[args["template"]]
        # Validate task metadata before publishing a member or reserving calls.
        task = self._new_task(worker_id, args)
        try:
            agent = Agent(worker_id, self.client, self.trace,
                template.system + WORKER_POLICY + "\n" + self.project_context,
                tools=[self.tools[n] for n in template.tools] + self.worker_controls,
                budget=Budget(template.tool_budget if template.tool_budget is not None else self.session_budget.tool_limit),
                max_turns=template.max_turns or self.session_budget.model_limit,
                usage_role=template.name, session_budget=self.session_budget)
        except Exception:
            task["status"] = "failed"
            raise
        agent.tool_gate = self._gate
        member = Member(agent, template.name, state="assigned", task_id=task["task_id"])
        self.members[worker_id] = member
        self.trace.emit("team_member", agent=worker_id, template=template.name, state="created")
        return dict(worker_id=worker_id, task=task, status="queued", budget=self.session_budget.snapshot())

    def _assign(self, args, actor):
        member = self.members.get(args["worker_id"])
        if member is None or member.active or member.state != "idle":
            raise ValueError("New assignments require an idle live worker")
        if member.task_id and self.tasks[member.task_id]["status"] not in {"reported", "accepted", "cancelled"}:
            raise ValueError("Wait for or cancel the previous assignment before assigning new work")
        task = self._new_task(member.agent.name, args)
        member.task_id, member.state = task["task_id"], "assigned"
        return dict(worker_id=member.agent.name, task=task, status="queued")

    def _update(self, args, actor):
        task = self.tasks.get(args["task_id"])
        if task is None or task["revision"] != args["expected_revision"]:
            raise ValueError("Unknown task or stale revision; inspect get_team_state")
        member = self.members[task["owner"]]
        action = args["action"]
        if action == "accept":
            if task["status"] != "reported" or member.active:
                raise ValueError("Only a fully returned reported task can be accepted")
            task["status"] = "accepted"
        elif action == "reopen":
            if member.active or member.state != "idle" or member.task_id != task["task_id"] or task["status"] not in {"reported", "accepted"}:
                raise ValueError("Only an idle reported/accepted owner can be reopened")
            if any(task["task_id"] in t["depends_on"] and ((self.members[t["owner"]].active and
                    self.members[t["owner"]].cause == "assignment" and self.members[t["owner"]].task_id == t["task_id"]) or
                    t["result_revision"] and t["status"] != "cancelled") for t in self.tasks.values()):
                raise ValueError("Dependent work used this input; cancel and drain it before reopening")
            task.update(status="assigned", specification_revision=task["specification_revision"] + 1,
                        context=task["context"] + "\nFollow-up: " + args["reason"], completion_status=None)
            member.task_id, member.state = task["task_id"], "assigned"
        else:
            task["status"] = "cancelled"
            if not member.active and member.task_id == task["task_id"] and member.state not in {"failed", "exhausted", "closed"}:
                member.state = "idle"
        task["leader_decision"] = args["reason"]
        self._touch(task, action, actor.name)
        return dict(task=task, note="Leader acceptance is not evaluator correctness")

    def _send(self, args, actor):
        target = args["to"]
        if target == actor.name or target != "leader" and target not in self.members:
            raise ValueError("Address a different existing team member")
        if target != "leader" and self.members[target].state in {"failed", "exhausted", "closed"}:
            raise ValueError("Recipient cannot receive further work in this session")
        task_id = args.get("task_id")
        reply = self.mail.records.get(args.get("reply_to"))
        if reply and task_id is None:
            task_id = reply["task_id"]
        if task_id is not None and task_id not in self.tasks:
            raise ValueError("Unknown message task_id")
        revision = self.tasks[task_id]["specification_revision"] if task_id else None
        stale = bool(reply and task_id and reply["task_id"] == task_id and reply["specification_revision"] != revision)
        record = self.mail.send(actor.name, target, args["content"], kind=args.get("kind", "info"),
            task_id=task_id, revision=revision, stale_reply=stale,
            reply_to=args.get("reply_to"), needs_reply=args.get("needs_reply", False))
        state = self.members[target].state if target != "leader" else (
            "in_flight" if "leader" in self.futures else "waiting" if self.root_waiting else "ready")
        self.deadlock_notified = False
        return dict(message_id=record["message_id"], status="queued", recipients=record["recipients"],
                    recipient_state=state, wake_policy="on_safe_boundary_if_admitted",
                    note="All messages wake idle or dependency-waiting recipients with their existing permissions; queued is not exposed.")

    def _resolve(self, args, actor):
        self.mail.resolve(args["message_id"], actor.name, args["reason"])
        return dict(status="resolved", message_id=args["message_id"])

    def _wait(self, args, actor):
        if self.mail.pending.get(actor.name):
            return dict(status="events_ready")
        timeout = args.get("timeout_seconds")
        if (actor.name == "leader" and timeout is None and self.deadlock_notified
                and self._no_progress_source(ignore_leader=True)):
            self.trace.emit("team_stall_resolution", action="drain", reason="repeated_indefinite_wait")
            self._drain("no_runnable_work")
            return dict(status="draining", reason="no_runnable_work", note="No event source remains; closing the team before final submission")
        until = time.monotonic() + timeout if timeout is not None else None
        if actor.name == "leader":
            self.root_waiting, self.root_deadline = True, until
        else:
            member = self.members[actor.name]
            member.wait_until = until
            member.state = "waiting"
        self.trace.emit("team_wait", agent=actor.name)
        return dict(status="waiting", note="Execution slot released until an event or timeout")

    def _assignment_ready(self, member):
        return member.state == "assigned" and all(self.tasks[d]["status"] in {"reported", "accepted"}
            and self.tasks[d]["outcome"] == "done" and self.tasks[d]["completion_status"] == "completed"
            for d in self.tasks[member.task_id]["depends_on"])

    def _no_progress_source(self, *, ignore_leader=False):
        # Check actual schedulable states, not stale ready entries or undeliverable mail.
        if any(name != "leader" or not ignore_leader for name in self.futures):
            return False
        if self.mail.pending.get("leader"):
            return False
        if not ignore_leader and self.root_waiting and self.root_deadline is not None:
            return False
        for name, member in self.members.items():
            if member.active and (member.state != "waiting" or member.wait_until is not None):
                return False
            if not member.active and self._assignment_ready(member):
                return False
            if self.mail.pending.get(name) and (member.active or member.state in {"idle", "assigned"}):
                return False
        return True

    def _finish_task(self, args, actor):
        member = self.members[actor.name]
        task = self.tasks[member.task_id]
        if (not member.active or member.cause != "assignment" or member.declaration is not None or
                task["status"] not in {"running", "blocked"} or task["specification_revision"] != member.assignment_revision):
            raise ValueError("Only the current live assignment can declare a terminal task status")
        member.declaration = dict(args)
        self.trace.emit("team_task_claim", agent=actor.name, activation=member.activation,
                        task_id=member.task_id, specification_revision=member.assignment_revision, **args)
        return dict(status="recorded", completion_status=args["status"], note="Member claim only; not verified correctness")

    def _report_status(self, args, actor):
        member = self.members[actor.name]
        task = self.tasks.get(member.task_id)
        if not task or task["status"] in {"accepted", "cancelled", "failed"} or member.cause != "assignment":
            raise ValueError("No live owned assignment to report")
        self.mail.send(actor.name, "leader", args["summary"], kind=args["status"], task_id=member.task_id,
                       revision=task["specification_revision"])
        if args["status"] == "blocked":
            task["status"] = "blocked"
            member.state, member.wait_until = "waiting", None
        else:
            task["status"] = "running"
        self._touch(task, args["status"], actor.name)
        return dict(status=args["status"], task_id=member.task_id)

    def _finish(self, args, actor):
        self._drain(args["reason"])
        self.root_waiting = True
        return dict(status=self.phase, note="Wait for the closing state before final submission")

    def _gate(self, tool, args, actor):
        with self.condition:
            reason = None
            if tool.name == actor.submission_tool and self.phase != "frozen":
                reason = "Call finish_team alone and wait for closure before submitting"
            elif self.phase in {"draining", "aborted"}:
                reason = "Team is draining; no new tool actions are admitted"
            elif self.phase == "frozen" and not (actor.name == "leader" and
                    (tool.name == actor.submission_tool or tool.name in {"get_team_state", "read_messages"})):
                reason = "Team is closed; submit final evidence and unresolved work"
            elif actor.name != "leader" and tool.name in self.tools:
                member = self.members[actor.name]
                task = self.tasks.get(member.task_id)
                if member.cause != "message" and (not task or task["status"] == "cancelled" or task["specification_revision"] != member.assignment_revision):
                    reason = "Assignment is no longer live; no new domain action admitted"
            if reason:
                return Observation(reason, {"error": True, "error_kind": "team_admission_denied"})

    def state(self):
        return dict(phase=self.phase, leader_mode=self.leader_mode, members={k: dict(template=m.template, state=m.state,
                    task_id=m.task_id, activation=m.activation, active=m.active,
                    activation_cause=m.cause if m.active else None, pending_task_id=m.pending_task_id if m.active else None)
                    for k, m in self.members.items()},
                    tasks=[{k: v for k, v in t.items() if k not in {"context", "report"}} for t in self.tasks.values()],
                    requests={k: dict(v) for k, v in self.mail.requests.items() if v["state"] != "resolved"},
                    pending_mail={k: len(v) for k, v in self.mail.pending.items() if v},
                    activations=self.activations, explicit_messages=self.mail.sent,
                    frozen_files=self.frozen_files,
                    budget=self.session_budget.snapshot(), close_reason=self.close_reason)

    def _activate(self, member, cause):
        try:
            admitted = self.activations < self.max_activations and self.session_budget.reserve_report(
                member.agent.name, require_work=True, protect_root=True)
        except SessionLimit:
            admitted = False
        if not admitted:
            member.state = "exhausted"
            self._notice(dict(event="activation_rejected", worker_id=member.agent.name,
                              reason="activation_or_model_capacity", task_id=member.task_id))
            return
        self.deadlock_notified = False
        self.activations += 1
        member.activation = self.activations
        member.active, member.audited, member.cause = True, False, cause
        member.trigger_message_ids = tuple(self.mail.pending.get(member.agent.name, ())) if cause == "message" else ()
        task = self.tasks[member.task_id]
        member.pending_task_id = member.task_id if cause == "message" and task["status"] == "assigned" else None
        member.previous_task_id = member.task_id if cause == "message" and not member.pending_task_id else None
        member.declaration = None
        member.wait_until, member.state = None, "ready"
        member.before = (member.agent.model_calls, member.agent.tool_calls, member.agent.budget.used)
        if cause == "assignment":
            task = self.tasks[member.task_id]
            member.assignment_revision = task["specification_revision"]
            task["status"] = "running"
            self._touch(task, "started", member.agent.name)
            prompt = json.dumps(dict(task_id=member.task_id, task=task["objective"], context=task["context"],
                                     write_scope=task["write_scope"], depends_on=task["depends_on"],
                                     specification_revision=member.assignment_revision), ensure_ascii=False)
        else:
            prompt = "Message activation: continue on the incoming messages with your existing template permissions. Only the Leader can change task assignments. This activation cannot complete an assignment."
            if member.pending_task_id:
                prompt += "\nPending assignment (not started; dependencies still govern its execution): " + json.dumps(
                    {k: task[k] for k in ("task_id", "objective", "context", "write_scope", "depends_on", "specification_revision")}, ensure_ascii=False)
        member.agent.start(prompt, REPORT_POLICY)
        self.trace.emit("team_activation_start", agent=member.agent.name, activation=member.activation,
                        cause=cause, task_id=member.task_id if cause == "assignment" else None,
                        previous_task_id=member.previous_task_id, pending_task_id=member.pending_task_id,
                        assignment_revision=member.assignment_revision if cause == "assignment" else None,
                        write_scope=task["write_scope"],
                        trigger_message_ids=member.trigger_message_ids)
        self.ready.append(member.agent.name)

    def _drain(self, reason):
        if self.phase != "open":
            return
        self.phase, self.close_reason = "draining", reason
        self.trace.emit("team_draining", reason=reason)
        for member in self.members.values():
            if member.active:
                member.wait_until = None
                member.state = "ready"
                if member.agent.name not in self.ready:
                    self.ready.append(member.agent.name)
        self.root_waiting = True

    def _step(self, worker_id):
        actor = self.leader if worker_id == "leader" else self.members[worker_id].agent
        member = self.members.get(worker_id)
        if member is not None and not member.audited:
            self.audit("before", worker_id, member.activation)
            member.audited = True
        with self.condition:
            self.mail.deliver(actor, limit=len(self.mail.records) if self.phase == "frozen" else 8)
            final = member is not None and (self.phase in {"draining", "aborted"} or
                    member.cause == "assignment" and self.tasks[member.task_id]["status"] == "cancelled")
        try:
            result = actor.step(force_final=final, final_reason=("task_cancelled" if
                member and member.cause == "assignment" and self.tasks[member.task_id]["status"] == "cancelled" else "team_draining") if final else None)
            if result is None and member is not None and member.declaration is not None:
                result = Outcome(member.declaration["summary"], "done", actor.invocation_turns)
        except BaseException:
            if member is not None:
                self.audit("after", worker_id, member.activation)
            raise
        if result is not None and member is not None:
            self.audit("after", worker_id, member.activation)
        return result

    def _complete(self, worker_id, future):
        failed = False
        try:
            result = future.result()
        except ModelDeferred:
            self._drain("protected_leader_final")
            return
        except Exception as error:
            failed = True
            kind = getattr(error, "kind", "execution_error")
            self.infra_affected |= kind != "context_length"
            self.errors.append(dict(agent_id=worker_id, error_kind=kind, report=str(error)))
            result = Outcome(str(error), kind, (self.leader if worker_id == "leader" else self.members[worker_id].agent).invocation_turns)
            if isinstance(error, ProviderError) and error.fatal:
                self.session_budget.stop(error)
                self.pending_error = error
            elif worker_id == "leader":
                self.pending_error = error
            if self.pending_error:
                self.phase = "aborted"
        if worker_id == "leader":
            if result is not None:
                if result.status == "done" and self.phase == "open" and not self.leader.last_call_final:
                    self.leader.append(self.leader.notice("Finish the team with finish_team before the final answer.", self.leader_final_prompt))
                else:
                    self.root_outcome = result
                    if self.phase == "open":
                        self._drain("leader_ended")
            return
        member = self.members[worker_id]
        if result is None:
            if member.state != "waiting":
                member.state = "ready"
                self.ready.append(worker_id)
            return
        if result.status == "done" and member.agent.last_call_final:
            # A reserved closing report does not establish completion of its task.
            result = Outcome(result.text, "partial", result.turns)
        task = self.tasks.get(member.task_id)
        failed |= result.status in {"stopped_after_fatal", "session_time_limit", "aborted"}
        report = dict(agent_id=worker_id, activation=member.activation, cause=member.cause,
                      task_id=member.task_id if member.cause == "assignment" else None,
                      previous_task_id=member.previous_task_id, pending_task_id=member.pending_task_id,
                      trigger_message_ids=member.trigger_message_ids,
                      completion_status=(member.declaration["status"] if member.declaration else "unclaimed") if member.cause == "assignment" else None,
                      outcome=result.status, report=result.text, final_reason=member.agent.last_final_reason,
                      usage=dict(model_calls=member.agent.model_calls-member.before[0],
                                 tool_calls=member.agent.tool_calls-member.before[1],
                                 budgeted_tool_calls=member.agent.budget.used-member.before[2]))
        if task and member.cause == "assignment" and task["status"] != "cancelled":
            task.update(status="failed" if failed else "reported", report=result.text, outcome=result.status,
                        result_revision=task["result_revision"] + 1, completion_status=report["completion_status"])
            self._touch(task, "handoff", worker_id)
            report["task_revision"] = task["revision"]
        self.trace.emit("team_activation_end", **report)
        self.reports.append(report)
        self._notice(report, "result", report["task_id"])
        member.active, member.wait_until = False, None
        member.state = "failed" if failed else "assigned" if task and task["status"] == "assigned" else "idle"
        self.session_budget.release_report(worker_id)

    def _freeze(self):
        self.phase = "frozen"
        for member in self.members.values():
            if member.state not in {"failed", "exhausted"}:
                member.state = "closed"
        self.root_waiting, self.root_deadline = False, None
        # Preserve undelivered peer mail explicitly; Leader still receives closing notices.
        for recipient in list(self.mail.pending):
            if recipient == "leader":
                continue
            ids = self.mail.pending.pop(recipient)
            self.undelivered[recipient] = ids
            for message_id in ids:
                self.trace.emit("team_message_undelivered", message_id=message_id, recipient=recipient, reason="team_closed")
        self.freeze_workspace()
        closing = self.state()
        closing["undelivered_peer_mail"] = self.undelivered
        self.trace.emit("team_frozen", state=closing)
        self._notice(dict(event="team_closed", state=closing))

    def run(self, task):
        if self.started:
            raise ValueError("A session can only be run once")
        self.started = True
        self.session_budget.start()
        self.trace.emit("session_config", mode=self.mode, context_mode=self.context_mode, fork=False,
                        task_completion_policy=self.task_completion_policy,
                        templates=[asdict(t) for t in self.templates.values()], leader_mode=self.leader_mode, max_workers=self.max_workers,
                        max_parallel=self.max_parallel, max_activations=self.max_activations,
                        message_limit=self.mail.limit, message_bytes=self.mail.max_bytes,
                        budget=self.session_budget.snapshot())
        self.leader.start(task, self.leader_final_prompt)
        self.audit("before")
        with ThreadPoolExecutor(self.max_parallel + 1) as pool:
            while True:
                with self.condition:
                    for worker_id, future in list(self.futures.items()):
                        if future.done():
                            del self.futures[worker_id]
                            self._complete(worker_id, future)
                    try:
                        self.session_budget.check()
                    except SessionLimit as error:
                        self.phase = "aborted"
                        if self.root_outcome is None and "leader" not in self.futures:
                            self.root_outcome = Outcome("Team stopped with unfinished work.", str(error), self.leader.invocation_turns)
                    if self.phase == "aborted":
                        for member in self.members.values():
                            if member.agent.name not in self.futures:
                                if member.active:
                                    stopped = Future()
                                    stopped.set_result(Outcome(member.agent.last_text or "Stopped with unfinished work.", "aborted", member.agent.invocation_turns))
                                    self.audit("after", member.agent.name, member.activation)
                                    self._complete(member.agent.name, stopped)
                                elif member.state == "assigned":
                                    member.state = "closed"
                                self.session_budget.release_report(member.agent.name)
                        if not self.futures:
                            self.root_outcome = self.root_outcome or Outcome("Team aborted.", "aborted", self.leader.invocation_turns)
                            break
                        self.condition.wait(0.05)
                        continue
                    if self.phase == "open":
                        for member in self.members.values():
                            if member.active or member.agent.name in self.futures:
                                continue
                            if self._assignment_ready(member):
                                self._activate(member, "assignment")
                            elif member.state in {"idle", "assigned"} and self.mail.pending.get(member.agent.name):
                                self._activate(member, "message")
                        if self.session_budget.snapshot()["model_calls_unreserved"] <= 0 or self.leader.invocation_turns + 1 >= self.leader.max_turns:
                            self._drain("model_or_root_turn_limit")
                    now = time.monotonic()
                    for worker_id, member in self.members.items():
                        if member.active and member.state == "waiting" and (self.mail.pending.get(worker_id) or
                                member.wait_until is not None and now >= member.wait_until):
                            if not self.mail.pending.get(worker_id):
                                self.mail.send("runtime", worker_id, "Wait timed out; report unresolved dependencies or continue useful work.", control=True)
                            member.wait_until, member.state = None, "ready"
                            task = self.tasks[member.task_id]
                            if member.cause == "assignment" and task["status"] == "blocked":
                                task["status"] = "running"
                                self._touch(task, "resumed", worker_id)
                            self.deadlock_notified = False
                            self.ready.append(worker_id)
                            self.trace.emit("team_wake", agent=worker_id)
                    active = [m for m in self.members.values() if m.active]
                    if self.phase == "draining" and not active and not self.futures:
                        self._freeze()
                    if self.root_outcome is not None and not self.futures and not active:
                        break
                    if (self.phase == "open" and self.root_waiting and not self.deadlock_notified
                            and self._no_progress_source()):
                        self._notice(dict(event="no_runnable_work", state=self.state()))
                        self.deadlock_notified = True
                    if self.root_waiting and self.phase != "draining" and (self.mail.pending.get("leader") or
                            self.root_deadline is not None and now >= self.root_deadline):
                        self.root_waiting, self.root_deadline = False, None
                    if self.phase in {"open", "frozen"} and not self.root_waiting and self.root_outcome is None and "leader" not in self.futures:
                        self._dispatch(pool, "leader")
                    occupied = sum(k != "leader" for k in self.futures)
                    for _ in range(len(self.ready)):
                        worker_id = self.ready.popleft()
                        member = self.members[worker_id]
                        if not member.active or member.state != "ready" or worker_id in self.futures:
                            continue
                        if occupied >= self.max_parallel:
                            self.ready.append(worker_id)
                            continue
                        self._dispatch(pool, worker_id)
                        occupied += 1
                    deadlines = [m.wait_until for m in self.members.values() if m.active and m.wait_until]
                    if self.root_deadline:
                        deadlines.append(self.root_deadline)
                    delay = min(0.5, max(0.001, min(deadlines) - now)) if deadlines else 0.5
                    self.condition.wait(delay)
        with self.condition:
            self.undelivered.update(self.mail.close("session_ended"))
            for member in self.members.values():
                self.session_budget.release_report(member.agent.name)
            self.session_budget.release_report("leader")
            self.audit("after")
            state = self.state()
            state["undelivered_mail"] = self.undelivered
            result = self.result(self.root_outcome, statuses={k: m.state for k, m in self.members.items()}, state=state)
        if self.pending_error:
            self.pending_error.session_outcome = result
            raise self.pending_error
        return result

    def _dispatch(self, pool, worker_id):
        if worker_id != "leader":
            self.members[worker_id].state = "in_flight"
        future = pool.submit(self._step, worker_id)
        self.futures[worker_id] = future
        def wake(_):
            with self.condition:
                self.condition.notify_all()
        future.add_done_callback(wake)
