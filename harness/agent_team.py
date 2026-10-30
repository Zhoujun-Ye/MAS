"""Bounded leader-led team with persistent contexts and verbatim peer messages.

Async execution uses one in-flight turn per member; controlled execution is
available as a fixed scheduling control. Workers remain
independent and can message any selected peer; no recursive nested agent calls.
Each run pins its team, domain permissions and budgets.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import threading
import time
from copy import deepcopy
import json

from .agent import Agent, Budget, Observation, Tool
from .config import digest
from .communication import normalize_json
from .llm import ProviderError
from .pool import POOL
from .information import InformationHarness

COMMUNICATION = {"send_message", "submit_assignment", "read_evidence",
                 "publish_artifact", "read_artifact", "list_tasks", "update_task", "wait_for_message"}


def synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapped


class TeamLimit(Exception):
    pass


class MemberLimit(TeamLimit):
    def __init__(self, role, reason):
        super().__init__(reason)
        self.role = role


class RetryTurn(Exception):
    """An incomplete response was refused; only its owner gets a recovery turn."""


class AgentTeam:
    def __init__(self, spec, form, client, trace, tools, permissions, *,
                 tool_budget=20, max_calls=32, max_messages=16, max_reads=8,
                 max_input_chars=200_000, final_validator=None, final_contract="", should_stop=None,
                 finalization_reserve=1, domain_policy=None, verifier=None, scheduler="async", member_inputs=None,
                 communication_policy=None, submission_hook=None, member_limits=None,
                 token_budget=None, time_limit_seconds=None):
        if form != "agent_team" or min(v for v in (tool_budget, max_calls, max_messages, max_reads, max_input_chars) if v is not None) <= 0:
            raise ValueError("Invalid handoff form or limits")
        if scheduler not in ("async", "controlled"):
            raise ValueError("Unknown scheduler")
        self.scheduler = scheduler
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.wakeup = threading.Event()
        self.receipts = {}
        self.awaiting_input = {m.role: [] for m in spec.members}
        self.spec, self.form, self.client, self.trace = spec, form, client, trace
        self.final_validator, self.final_contract = final_validator, final_contract
        self.verifier = verifier
        self.submission_hook = submission_hook
        self.submissions = {}
        self.submission_history = {}
        self.should_stop = should_stop or (lambda: False)
        if any(v is not None and v <= 0 for v in (token_budget, time_limit_seconds)):
            raise ValueError('Token/time allowances must be positive')
        self.token_budget, self.time_limit_seconds = token_budget, time_limit_seconds
        self.started_at = None
        self.domain = {t.name: t for t in tools}
        if len(self.domain) != len(tools) or self.domain.keys() & COMMUNICATION:
            raise ValueError("Duplicate or reserved domain tool name")
        names = {m.role for m in spec.members}
        self.templates = {m.role: m.template for m in spec.members}
        self.member_inputs = deepcopy(member_inputs or {})
        if not set(self.member_inputs) <= names or any(not isinstance(v, str) for v in self.member_inputs.values()):
            raise ValueError("Private inputs must map selected members to text")
        if set(permissions) != names or any(not set(v) <= self.domain.keys() for v in permissions.values()):
            raise ValueError("Permissions must bind every selected role to available tools")
        self.permissions = {k: tuple(sorted(v)) for k, v in permissions.items()}
        if self.permissions.get("leader"):
            raise ValueError("Leader is communication-only; domain-tool grants are forbidden")
        if type(finalization_reserve) is not int or finalization_reserve < 1 or (max_calls is not None and finalization_reserve > max_calls):
            raise ValueError("Finalization reserve must fit inside the model-call cap")
        self.finalization_reserve = finalization_reserve
        self.finalizing = False
        self.submitted = {n: False for n in names}
        self.tasks = {m.role: dict(task_id=m.role, owner=m.role, assignment=m.assignment,
                                  status="working", revision=1, verification="not_run", submission_id=None) for m in spec.members}
        self.agent_states = dict.fromkeys(names, "idle")
        self.controls = {n: deque() for n in names}
        self.ready = dict.fromkeys(names, True)
        defaults = dict(tool_budget=tool_budget, max_calls=max_calls, max_messages=max_messages, max_reads=max_reads)
        self.member_limits = {n: defaults | (member_limits or {}).get(n, {}) for n in names}
        if set(member_limits or {}) - names:
            raise ValueError("Limits must name selected members")
        for limits in self.member_limits.values():
            if (set(limits) != set(defaults) or any(v is not None and (type(v) is not int or v < 0) for v in limits.values())
                    or limits['max_calls'] == 0 or limits['tool_budget'] is None):
                raise ValueError("Invalid member limits")
        self.budgets = {n: Budget(l['tool_budget']) for n, l in self.member_limits.items()}
        self.read_budgets = {n: Budget(l['max_reads']) for n, l in self.member_limits.items()}
        self.calls_by_member = dict.fromkeys(names, 0)
        self.tokens_by_member = dict.fromkeys(names, 0)
        self.last_team_state = dict.fromkeys(names, None)
        self.output_recoveries = dict.fromkeys(names, 0)
        self.snapshot_errors = {}
        self.messages_by_member = dict.fromkeys(names, 0)
        self.halted = {}
        self.evaluation_snapshots = {}
        self.max_input_chars = max_input_chars
        self.calls = self.sent = 0
        self.information = InformationHarness(names, form, trace, communication_policy)
        self.agents, self.access = {}, self.information.access
        self.pending, self.inbox = [], {n: deque() for n in names}
        self.started = False
        self.requesters = {n: set() for n in names}
        self.limits = dict(tool_budget=tool_budget, max_calls=max_calls, max_messages=max_messages,
                           max_reads=max_reads, max_input_chars=max_input_chars,
                           finalization_reserve=finalization_reserve, token_budget=token_budget,
                           time_limit_seconds=time_limit_seconds)
        self.control = dict(team=spec.payload(), model=vars(client.cfg), limits=self.limits, member_limits=self.member_limits,
                            member_input_digests={n: digest(v) for n, v in self.member_inputs.items()},
                            communication_policy=self.information.policy.manifest,
                            submission_contract="immutable-snapshot-v1" if submission_hook else "report-only-v1",
                            isolation="private-context-explicit-grants-v1",
                            prompts={n: POOL[self.templates[n]].system for n in sorted(names)},
                            domain_permissions=self.permissions,
                            domain_schemas=[self.domain[n].schema for n in sorted(self.domain)],
                            domain_policy=deepcopy(domain_policy),
                            scheduler=scheduler + "-v1", startup="all-members-ready-v1",
                            state_delivery='on-change-v1', output_recovery='one-consecutive-retry-v1',
                            domain_read_only={n: self.domain[n].read_only for n in sorted(self.domain)},
                            communication="verbatim-mailbox-v1",
                            artifact_transport="explicit-grant-v1",
                            communication_schemas={n: [t.schema for t in self.communication_tools(n)]
                                                   for n in sorted(names)} if len(names) > 1 else {},
                            verification_enabled=verifier is not None,
                            final_contract=final_contract)
        self.control_digest = digest(self.control)

    @property
    def evidence(self):
        return self.information.evidence

    def time_expired(self):
        return (self.started_at is not None and self.time_limit_seconds is not None
                and time.monotonic() - self.started_at >= self.time_limit_seconds)

    @synchronized
    def prepare_call(self, agent):
        self.receive(agent.name)
        if self.should_stop() or self.stopping.is_set():
            raise TeamLimit("interrupted")
        if self.time_expired():
            raise TeamLimit('time_limit')
        if self.token_budget is not None and self.tokens_by_member[agent.name] >= self.token_budget:
            raise MemberLimit(agent.name, 'token_limit')
        used, cap = self.calls_by_member[agent.name], self.member_limits[agent.name]['max_calls']
        if cap is not None and used >= cap:
            raise MemberLimit(agent.name, "model_call_limit")
        if (cap is not None and not self.finalizing and agent.name == self.final_role and len(self.spec.members) > 1
                and used >= cap - min(self.finalization_reserve, cap)):
            raise MemberLimit(agent.name, "finalization_reserve")
        if agent.name in self.agents:
            # Append only operational state, never another worker's private facts.
            state = json.dumps({"team_state": dict(
                domain_budget=self.budgets[agent.name].snapshot(),
                model_calls_remaining=None if cap is None else cap - used,
                tokens_remaining=None if self.token_budget is None else max(0, self.token_budget - self.tokens_by_member[agent.name]),
                finalization_reserve=self.finalization_reserve,
                messages_remaining=(None if self.member_limits[agent.name]["max_messages"] is None else
                                    self.member_limits[agent.name]["max_messages"] - self.messages_by_member[agent.name]),
                tasks=self.task_board(),
                evidence_reads=self.read_budgets[agent.name].snapshot(),
                available_evidence_ids=self.information.visible_ids(agent.name, "e"),
                available_artifact_ids=self.information.visible_ids(agent.name, "a"))})
            if self.last_team_state[agent.name] != state:
                agent.append({"role": "user", "content": state})
                self.last_team_state[agent.name] = state
        self.set_agent_state(agent.name, "running")
        self.calls += 1
        self.calls_by_member[agent.name] += 1
        if agent.max_input_chars is not None and len(json.dumps([agent.messages, agent.schemas], ensure_ascii=False)) > agent.max_input_chars:
            raise MemberLimit(agent.name, "context_length")
        request_id = self.trace.emit("model_input", agent=agent.name, context_len=len(agent.messages),
                                     message_ids=list(self.awaiting_input[agent.name]))
        for message_id in self.awaiting_input[agent.name]:
            self.trace.emit("peer_consumed", **self.receipts[message_id], request_id=request_id)
        self.awaiting_input[agent.name].clear()
        agent.request_id = request_id

    def call(self, agent, **kwargs):
        self.prepare_call(agent)
        try:
            reply = agent.call(**kwargs)
        except ProviderError as error:
            self.set_agent_state(agent.name, "failed")
            if error.kind == "context_length":
                raise MemberLimit(agent.name, "context_length") from error
            raise  # Provider/key/balance failures belong to runner recovery.
        with self.lock:
            self.tokens_by_member[agent.name] += reply.usage['prompt_tokens'] + reply.usage['completion_tokens']
        if self.should_stop():
            agent.refuse(reply.message.get("tool_calls") or [])
            raise TeamLimit("interrupted")
        if self.time_expired():
            agent.refuse(reply.message.get('tool_calls') or [])
            raise TeamLimit('time_limit')
        if self.token_budget is not None and self.tokens_by_member[agent.name] > self.token_budget:
            agent.refuse(reply.message.get('tool_calls') or [])
            raise MemberLimit(agent.name, 'token_limit')
        if reply.finish_reason == "length":
            agent.refuse(reply.message.get("tool_calls") or [])
            if self.output_recoveries[agent.name] >= 1:
                raise MemberLimit(agent.name, 'output_length')
            self.output_recoveries[agent.name] += 1
            agent.append(dict(role='user', content='Your previous reply reached the output length limit. '
                              'No tools from that reply were executed. Continue with a shorter response or smaller tool calls.'))
            self.trace.emit('output_recovery', agent=agent.name, attempt=self.output_recoveries[agent.name])
            raise RetryTurn()
        self.output_recoveries[agent.name] = 0
        return reply

    def domain_tool(self, original):
        def preflight(args, agent):
            if self.stopping.is_set() or self.should_stop() or self.time_expired():
                return Observation("Team is stopping; tool not executed.", {"error": True, "error_kind": "interrupted"})
            if self.submitted.get(agent.name) and not original.read_only:
                return Observation("Assignment submitted. Read-only file tools remain available; reopen with update_task(status=working) before writes or terminal commands.",
                                   {"error": True, "error_kind": "submission_frozen"})
            if original.name not in self.permissions.get(agent.name, ()):
                return Observation("Domain tool access denied.", {"error": True, "error_kind": "permission_denied"})
            return original.preflight(args, agent) if original.preflight else None

        def run(args, agent):
            if (denied := preflight(args, agent)) is not None:
                return denied
            obs = original.run(args, agent)
            if obs.meta.get("error"):
                return obs  # Failed calls are diagnostics, not source evidence.
            data = dict(owner=agent.name, tool=original.name, arguments=args, text=obs.text)
            data["source_tool_call_id"] = getattr(agent, "active_tool_call_id", None)
            with self.lock:
                key = self.information.publish(agent.name, "evidence", data)["id"]
            self.trace.emit("evidence", evidence_id=key, **data)
            return Observation(f"Evidence: {key}\n" + obs.text, dict(obs.meta, evidence_id=key))
        return Tool(original.name, original.description, original.parameters, run, budgeted=True, preflight=preflight,
                    read_only=original.read_only)

    @synchronized
    def queue(self, sender, recipient, content, evidence_ids, requires_reply=False, artifact_ids=None):
        artifact_ids = [] if artifact_ids is None else artifact_ids
        message = self.information.prepare_message(sender, recipient, content, evidence_ids, artifact_ids, requires_reply)
        content = message.content
        evidence_ids, artifact_ids = list(message.evidence_ids), list(message.artifact_ids)
        if (self.member_limits[sender]['max_messages'] is not None
                and self.messages_by_member[sender] >= self.member_limits[sender]['max_messages']):
            self.trace.emit("member_budget_denial", agent=sender, budget="messages")
            raise ValueError("Your outgoing message limit is exhausted")
        self.messages_by_member[sender] += 1
        self.sent += 1
        message_id = f"m{self.sent}"
        self.trace.emit("policy_message", message_id=message_id, sender=sender, recipient=recipient,
                        policy_digest=digest(self.information.policy.manifest), content_digest=digest(message.content))
        self.trace.emit("peer_queued", message_id=message_id, sender=sender, recipient=recipient,
                        intent=content, evidence_ids=evidence_ids, artifact_ids=artifact_ids,
                        requires_reply=requires_reply)
        self.receipts[message_id] = dict(message_id=message_id, sender=sender, recipient=recipient,
            source_tool_call_ids=[self.information.authorized(sender, k)["data"].get("source_tool_call_id")
                                  for k in evidence_ids])
        self.pending.append((message_id, sender, recipient, content, evidence_ids, requires_reply, artifact_ids))
        self.deliver()

    def submit_assignment(self, agent, content, ids, artifact_ids=None, paths=None):
        artifact_ids = [] if artifact_ids is None else artifact_ids
        with self.lock:
            if self.stopping.is_set() or self.should_stop() or self.time_expired():
                raise TeamLimit("interrupted")
            if agent.name == self.final_role:
                raise ValueError("The leader submits a final answer, not a worker completion")
            if self.submitted[agent.name]:
                raise ValueError("Assignment already submitted; reopen explicitly for a new revision")
            self.information.prepare_message(agent.name, self.final_role, content, ids, artifact_ids)
            if self.submission_hook is not None and paths is None:
                raise ValueError('Explicit code submission requires selected implementation paths (an empty list is allowed)')
            revision = self.tasks[agent.name]["revision"]
        # Snapshot I/O belongs to the owning turn, not the shared-state lock.
        artifact = self.submission_hook(agent.name, revision, paths) if self.submission_hook else dict(report=content)
        artifact = json.loads(json.dumps(artifact))
        submission_id = f"{agent.name}:v{revision}"
        snapshot = dict(submission_id=submission_id, revision=revision, kind="explicit", artifact=artifact, digest=digest(artifact))
        with self.lock:
            if self.stopping.is_set() or self.should_stop() or self.time_expired():
                raise TeamLimit("interrupted")
            if self.tasks[agent.name]["revision"] != revision or self.submitted[agent.name]:
                raise ValueError("Assignment changed during snapshot capture")
            self.submission_history[submission_id] = json.dumps(snapshot)
            self.submissions[agent.name] = submission_id
            self.submitted[agent.name] = True
            self.tasks[agent.name].update(status="submitted", submission_id=submission_id, verification="not_run")
            self.ready[agent.name] = False
            self.set_agent_state(agent.name, "idle")
            self.trace.emit("submission_snapshot", agent=agent.name, **snapshot)
            # Status is independent of the report budget and contains no content.
            self.status_event("task_submitted", agent.name)
            recipients = [self.final_role] + sorted(self.requesters[agent.name] - {self.final_role})
            for recipient in recipients:
                self.queue(agent.name, recipient, content, ids, artifact_ids=artifact_ids)
            self.requesters[agent.name].clear()

    @synchronized
    def submission(self, role):
        if not self.submitted[role]:
            raise ValueError("No current submitted revision")
        return json.loads(self.submission_history[self.submissions[role]])

    @synchronized
    def record_verification(self, role, submission_id, status):
        """Trusted evaluator API; never exposed as an agent tool."""
        if not self.submitted.get(role) or self.submissions.get(role) != submission_id:
            raise ValueError("Verification must identify the current submitted revision")
        if status not in ("passed", "failed", "error"):
            raise ValueError("Invalid verification status")
        self.tasks[role].update(verification=status, status="completed" if status == "passed" else "submitted")
        self.trace.emit("task_verification", agent=role, submission_id=submission_id, status=status)

    def ready_to_finalize(self):
        workers = [r for r in self.submitted if r != self.final_role]
        return (all(self.submitted[r] and not self.ready[r] for r in workers)
                and not any(r in self.halted for r in workers)
                and not self.pending and not any(self.inbox.values()) and not any(self.controls.values())
                and not any(self.awaiting_input.values()))

    @synchronized
    def set_agent_state(self, role, state):
        if self.agent_states[role] != state:
            self.agent_states[role] = state
            self.trace.emit("agent_state", agent=role, state=state)

    def task_board(self):
        return [{key: task[key] for key in ("task_id", "owner", "status", "revision", "submission_id", "verification")}
                for task in self.tasks.values() if self.templates[task['owner']] != 'leader']

    def status_event(self, kind, role):
        event = dict(type=kind, task_id=role, owner=role,
                     status=self.tasks[role]["status"], revision=self.tasks[role]["revision"],
                     submission_id=self.tasks[role]["submission_id"])
        self.trace.emit("task_status", **{k: v for k, v in event.items() if k != "type"}, event=kind)
        if role != self.final_role:
            self.controls[self.final_role].append(event)
            self.ready[self.final_role] = True
            self.wakeup.set()

    @synchronized
    def update_task(self, role, status):
        if status not in ("working", "blocked"):
            raise ValueError("Use submit_assignment to submit; validation is evaluator-owned")
        if self.submitted[role]:
            self.tasks[role]["revision"] += 1
            self.tasks[role].update(submission_id=None, verification="not_run")
        self.tasks[role]["status"] = status
        self.ready[role] = status == "working"
        self.submitted[role] = False
        self.set_agent_state(role, "running" if self.ready[role] else "waiting")
        self.status_event("task_updated", role)

    def communication_tools(self, role=None):
        def send(args, agent):
            self.queue(agent.name, args["recipient"], args["content"], args.get("evidence_ids", []),
                       args.get("requires_reply", False), args.get("artifact_ids", []))
            return Observation("Delivered to mailbox; included at the recipient's next model input. "
                               "Evidence attachments: " + ', '.join(args.get('evidence_ids', [])) + "; artifact attachments: "
                               + (', '.join(args.get('artifact_ids', [])) or 'none')
                               + ". Mentioning an ID in text alone does not grant access.", {"communication": True})

        def finish(args, agent):
            self.submit_assignment(agent, args["report"], args.get("evidence_ids", []), args.get("artifact_ids", []), args.get("paths"))
            return Observation("Revision submitted, not verified. Report uses the same communication policy as send_message.", {"communication": True})

        def read(args, agent):
            if not self.information.raw_evidence_enabled:
                return Observation("Original-evidence reads are disabled.")
            key = args["id"]
            if key not in self.access[agent.name]:
                return Observation("Evidence not granted to this recipient; ask its owner to send_message with evidence_ids selected.",
                                   {"error": True, "error_kind": "evidence_not_granted"})
            if not key.startswith("e"):
                return Observation("Not an evidence ID.", {"error": True})
            if not self.read_budgets[agent.name].take():
                return Observation("Communication read limit reached.", {"communication_limit": True})
            record = self.information.read(agent.name, key)
            return Observation(f"Evidence: {key}\n" + record["data"]["text"], {"communication": True})

        def publish(args, agent):
            record = self.information.publish(agent.name, args["kind"],
                                              dict(title=args["title"], content=args["content"]),
                                              args.get("previous"))
            return Observation(json.dumps(record, ensure_ascii=False), {"communication": True})

        result = [
            Tool("send_message", "Send findings, requests or corrections directly to a selected teammate.",
                 {"type": "object", "properties": {"recipient": {"type": "string"}, "content": {"type": "string"},
                 "evidence_ids": {"type": "array", "items": {"type": "string"}},
                 "artifact_ids": {"type": "array", "items": {"type": "string"}},
                 "requires_reply": {"type": "boolean", "description": "True only for a concrete request requiring work; false for findings, corrections or acknowledgements."}},
                 "required": ["recipient", "content"], "additionalProperties": False}, send),
            Tool("submit_assignment", "Submit a frozen revision and route its report to the leader and requesters. This is not verified completion. Do not also send duplicate final reports.",
                 {"type": "object", "properties": {"report": {"type": "string", "minLength": 1},
                 "paths": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True,
                           "description": "Implementation files to submit; exclude tests and scratch files."},
                 "evidence_ids": {"type": "array", "items": {"type": "string"}},
                 "artifact_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["report"],
                 "additionalProperties": False}, finish),
            Tool("read_evidence", "Read an explicitly granted original observation.",
                 {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"],
                 "additionalProperties": False}, read),
        ]
        result.append(Tool("publish_artifact", "Store a private artifact. Share an immutable revision by selecting artifact_ids in a message.",
                           {"type": "object", "properties": {
                               "kind": {"type": "string", "enum": ["artifact", "memory", "state"]},
                               "title": {"type": "string", "minLength": 1, "maxLength": 200},
                               "content": {"type": "string", "maxLength": 20000},
                               "previous": {"type": "string"}},
                            "required": ["kind", "title", "content"], "additionalProperties": False}, publish))
        def read_artifact(args, agent):
            if not args["id"].startswith("a"):
                raise ValueError("Not an artifact ID")
            if args['id'] not in self.access[agent.name]:
                return Observation('Artifact not granted. Ask its owner to send_message with artifact_ids=["'
                                   + args['id'] + '"]; mentioning an ID in prose does not grant access.',
                                   dict(error=True, error_kind='artifact_not_granted'))
            if not self.read_budgets[agent.name].take():
                return Observation("Communication read limit reached.", {"communication_limit": True})
            record = self.information.read(agent.name, args["id"])
            return Observation(f"Artifact: {record['id']}; kind: {record['kind']}\n"
                               + record["data"]["title"] + "\n\n" + record["data"]["content"], {"communication": True})

        def update(args, agent):
            self.update_task(agent.name, args["status"])
            return Observation(json.dumps(self.tasks[agent.name]), {"communication": True})

        def wait(args, agent):
            self.ready[agent.name] = False
            self.set_agent_state(agent.name, "waiting")
            return Observation("Waiting for a teammate message.", {"communication": True})

        result.extend([
            Tool("read_artifact", "Read an explicitly shared artifact revision.",
                 {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"],
                  "additionalProperties": False}, read_artifact),
            Tool("list_tasks", "Read the shared assignment status board, not private conversations.",
                 {"type": "object", "properties": {}, "additionalProperties": False},
                 lambda args, agent: Observation(json.dumps(self.task_board()))),
            Tool("update_task", "Update your assignment status. Reopening invalidates the current submission; only the evaluator verifies correctness.",
                 {"type": "object", "properties": {"status": {"type": "string", "enum": ["working", "blocked"]}},
                  "required": ["status"], "additionalProperties": False}, update),
            Tool("wait_for_message", "Yield until a teammate sends a message; no acknowledgement required.",
                 {"type": "object", "properties": {}, "additionalProperties": False}, wait),
        ])
        for tool in result:
            if tool.name == "submit_assignment":
                continue  # Own locking; slow snapshot export must not block peers.
            original = tool.run
            def locked(args, agent, original=original):
                with self.lock:
                    if self.stopping.is_set() or self.should_stop() or self.time_expired():
                        return Observation("Team is stopping; tool not executed.", {"error": True, "error_kind": "interrupted"})
                    return original(args, agent)
            tool.run = locked
        return [tool for tool in result if role != "leader" or tool.name != "submit_assignment"]

    @synchronized
    def deliver(self):
        while self.pending:
            message_id, sender, recipient, intent, ids, requires_reply, artifact_ids = self.pending[0]
            agent = self.agents[sender]
            packet = dict(message_id=message_id, sender=sender, recipient=recipient, task_id=recipient,
                          payload=intent, evidence_ids=ids, artifact_ids=artifact_ids, requires_reply=requires_reply)
            self.trace.emit("peer_handoff", **packet, sender_context_len=len(agent.messages), sender_context_digest=digest(agent.messages))
            self.inbox[recipient].append(packet)
            self.wakeup.set()
            self.trace.emit("peer_mailbox", **self.receipts[message_id])
            self.information.grant(sender, recipient, ids + artifact_ids, message_id)
            self.pending.pop(0)

    @synchronized
    def receive(self, role):
        agent = self.agents[role]
        while self.controls[role]:
            agent.append({"role": "user", "content": json.dumps({"task_event": self.controls[role].popleft()})})
            self.ready[role] = True
        while self.inbox[role]:
            packet = self.inbox[role].popleft()
            header = (f"Message {packet['message_id']} from {packet['sender']} to {role}\n"
                      f"Evidence: {', '.join(packet['evidence_ids']) or 'none'}; "
                      f"Artifacts: {', '.join(packet['artifact_ids']) or 'none'}; "
                      f"Reply requested: {str(packet['requires_reply']).lower()}\n\n")
            agent.append({"role": "user", "content": header + packet["payload"]})
            self.awaiting_input[role].append(packet["message_id"])
            self.ready[role] = True
            if packet["requires_reply"]:
                self.requesters[role].add(packet["sender"])
            self.trace.emit("peer_delivery", message_id=packet["message_id"], sender=packet["sender"], recipient=role,
                            context_len=len(agent.messages), requires_reply=packet["requires_reply"])

    def worker_report(self, agent, content):
        with self.lock:
            self.ready[agent.name] = False
        self.set_agent_state(agent.name, "idle")

    def runnable(self, role):
        return role not in self.halted and bool(self.ready[role] or self.inbox[role] or self.controls[role])

    def halt_member(self, error):
        with self.lock:
            self.halted[error.role] = str(error)
            self.ready[error.role] = False
            self.set_agent_state(error.role, 'terminated')
            self.trace.emit('member_limit', agent=error.role, reason=str(error))
            self.status_event('member_halted', error.role)
        self.capture_evaluation_snapshot(error.role)

    def capture_evaluation_snapshot(self, role):
        if not self.submission_hook or role == self.final_role or role in self.evaluation_snapshots:
            return
        try:
            if self.submitted[role]:
                snapshot = self.submission(role)
            else:
                revision = self.tasks[role]['revision']
                artifact = self.submission_hook(role, revision, None)
                snapshot = dict(submission_id=f'{role}:v{revision}:terminal', revision=revision,
                                kind='terminal', artifact=artifact, digest=digest(artifact))
                self.trace.emit('terminal_snapshot', agent=role, **snapshot)
            self.evaluation_snapshots[role] = json.loads(json.dumps(snapshot))
        except Exception as error:
            self.snapshot_errors[role] = type(error).__name__
            self.trace.emit('snapshot_error', agent=role, error_type=type(error).__name__)

    def defer_final(self, agent):
        self.trace.emit('final_deferred', agent=agent.name, reason='pending_team_work')
        agent.append(dict(role='user', content='Final answer not accepted: teammates still have pending work '
                          'or messages. Coordinate or wait for their reports before finalizing.'))

    def idle_outcome(self):
        # Same quiescence recovery for both schedulers, including a deferred
        # leader whose last blocker yielded without sending another message.
        if self.ready_to_finalize() and self.final_role not in self.halted:
            self.ready[self.final_role] = True
            return None
        if self.halted.get(self.final_role) == 'finalization_reserve':
            return self.finalize_budget()
        return dict(status='incomplete', reason='member_limits' if self.halted else 'team_waiting_without_messages')

    def accept_final(self, content, termination):
        agent = self.agents[self.final_role]
        if self.final_validator:
            normalized = normalize_json(content)
            if normalized != content:
                self.trace.emit("final_format_normalized", agent=agent.name, source_idx=len(agent.messages) - 1)
            content = normalized
        if not content.strip() or (self.final_validator and not self.final_validator(content)):
            agent.append({"role": "user", "content": "Final output format not accepted. " + self.final_contract})
            self.ready[agent.name] = True
            return None
        self.trace.emit("final", agent=agent.name, content=content, termination=termination)
        verification = {"status": "not_run"}
        submission_ready = self.ready_to_finalize()
        if self.verifier is not None and submission_ready:
            try:
                verification = self.verifier({r: self.submission(r) for r in self.submissions if self.submitted[r]})
                if not isinstance(verification, dict) or verification.get("status") not in ("passed", "failed", "error"):
                    raise ValueError("Verifier must return passed, failed or error")
            except Exception as error:
                verification = dict(status="error", error=str(error))
        self.trace.emit("verification", result=verification,
                        submission_ids={r: sid for r, sid in self.submissions.items() if self.submitted[r]})
        return dict(status="completed", final=content, control_digest=self.control_digest,
                    submission_status="submitted" if submission_ready else "incomplete", verification=verification,
                    task_submissions={r: {"submission_id": sid, "digest": self.submission(r)["digest"]}
                                      for r, sid in self.submissions.items() if self.submitted[r]},
                    calls=self.calls, tool_calls=sum(b.used for b in self.budgets.values()), termination=termination,
                    unfinished_roles=[n for n, done in self.submitted.items() if n != agent.name and not done])

    def finalize_budget(self, reason="finalization_reserve"):
        # Delivery costs no model calls, including at a budget boundary.
        self.finalizing = True
        self.deliver()
        self.halted.pop(self.final_role, None)
        final_call_limit = min(self.member_limits[self.final_role]["max_calls"], self.calls_by_member[self.final_role] + self.finalization_reserve)
        self.receive(self.final_role)
        agent = self.agents[self.final_role]
        unfinished = [n for n, done in self.submitted.items() if n != agent.name and not done]
        self.trace.emit("finalization_start", reason=reason, remaining_calls=final_call_limit - self.calls_by_member[self.final_role],
                        unfinished_roles=unfinished, undelivered_messages=[p[0] for p in self.pending])
        agent.append({"role": "user", "content": "Coordination has stopped; the remaining calls are reserved for your final answer. "
                      "No further tools or coordination are allowed. Use only evidence already in your context; do not invent missing verification. "
                      "Some reports may remain undelivered. Unfinished assignments: " + json.dumps(unfinished) + ". " + self.final_contract})
        while self.calls_by_member[self.final_role] < final_call_limit:
            try:
                reply = self.call(agent, tool_choice="none")
            except RetryTurn:
                continue
            calls = reply.message.get("tool_calls") or []
            if calls:
                agent.refuse(calls)
                continue
            termination = "message_limit_finalization" if reason == "message_limit" else "budget_finalization"
            result = self.accept_final(reply.message.get("content") or "", termination)
            if result:
                return result
        return dict(status="incomplete", reason="finalization_failed", calls=self.calls, tool_calls=sum(b.used for b in self.budgets.values()))

    def run_task(self, request):
        try:
            result = self._run_task(request)
            result.setdefault('submission_status', 'incomplete')
            result.setdefault('verification', {'status': 'not_run'})
            result['failure_class'] = ('external_interruption' if result.get('reason') == 'interrupted' else
                                       'agent_failure' if result['status'] != 'completed' or result['submission_status'] != 'submitted'
                                       else None)
            result['calls'] = self.calls
            result['elapsed_seconds'] = time.monotonic() - self.started_at
            result['member_usage'] = {r: dict(model_calls=self.calls_by_member[r], tool_calls=self.budgets[r].used,
                                              messages=self.messages_by_member[r], reads=self.read_budgets[r].used,
                                              tokens=self.tokens_by_member[r])
                                      for r in self.ready}
            result['halted_members'] = dict(self.halted)
            for role in self.ready:
                self.capture_evaluation_snapshot(role)
            result['evaluation_snapshots'] = {r: {k: s[k] for k in ('submission_id', 'digest', 'kind')}
                                              for r, s in self.evaluation_snapshots.items()}
            if self.snapshot_errors:
                result['snapshot_errors'] = dict(self.snapshot_errors)
            return result
        finally:
            if self.started:
                for role in self.agent_states:
                    self.set_agent_state(role, "terminated")

    def _run_task(self, request):
        if self.started:
            raise ValueError("Team instances cannot be reused for later requests")
        self.spec.validate_task(request)
        self.started = True
        self.started_at = time.monotonic()
        self.trace.emit("team_spec", control_digest=self.control_digest, control=self.control, form=self.form)
        solo = len(self.spec.members) == 1
        final_role = self.spec.members[0].role if solo else "leader"
        self.final_role = final_role
        # Task creation is an activation event for every member, including the
        # leader. Later turns remain event-driven; no unsolicited polling loop.
        order = [m.role for m in self.spec.members if m.role != final_role] + [final_role]
        ready = self.ready
        for member in self.spec.members:
            role = member.role
            tools = [self.domain_tool(self.domain[name]) for name in self.permissions[role]]
            if not solo:
                tools += self.communication_tools(role)
            agent = Agent(role, self.client, self.trace, POOL[member.template].system + f"\nMember identity: {role}.\nCommunication policy:\n" + self.information.policy.instructions, tools=tools,
                          budget=self.budgets[role], max_input_chars=self.max_input_chars, usage_role=role)
            agent.append({"role": "user", "content": json.dumps(dict(
                member=role, team=self.spec.payload(),
                member_limits=self.member_limits[role],
                domain_policy=self.control["domain_policy"], tool_directory=self.permissions,
                evidence_access=dict(read_enabled=self.information.raw_evidence_enabled,
                                     references_are_not_reads=True)), ensure_ascii=False)
                + "\n\nPublic request:\n" + request + "\n\nAssignment:\n" + member.assignment
                + "\n\nPrivate assignment:\n" + self.member_inputs.get(role, "")})
            self.agents[role] = agent
        try:
            if self.scheduler == "async":
                return self.run_concurrent(order)
            while True:
                if not any(self.runnable(r) for r in order):
                    result = self.idle_outcome()
                    if result is not None:
                        return result
                for role in order:
                    agent = self.agents[role]
                    if role in self.halted:
                        continue
                    self.receive(role)
                    if not ready[role]:
                        continue
                    try:
                        reply = self.call(agent)
                    except RetryTurn:
                        ready[role] = True
                        continue
                    except MemberLimit as error:
                        self.halt_member(error)
                        continue
                    calls = reply.message.get("tool_calls") or []
                    if calls:
                        agent.answer(calls)
                    else:
                        ready[role] = False
                        content = reply.message.get("content") or ""
                        if role == final_role:
                            if not self.ready_to_finalize():
                                self.defer_final(agent)
                                # Wake on the next delivered report, not by polling
                                # the leader repeatedly while workers are running.
                                ready[role] = False
                            else:
                                result = self.accept_final(content, "tasks_submitted")
                                if result:
                                    return result
                        elif not solo:
                            self.worker_report(agent, content)
                    self.deliver()
        except TeamLimit as error:
            if str(error) in ("finalization_reserve", "message_limit"):
                try:
                    self.stopping.clear()
                    return self.finalize_budget(str(error))
                except TeamLimit as final_error:
                    error = final_error
            return dict(status="incomplete", reason=str(error), calls=self.calls, tool_calls=sum(b.used for b in self.budgets.values()))

    def run_concurrent(self, order):
        # Only the owner thread mutates its context. The lock protects shared
        # state, never network calls or domain execution.
        def turn(role):
            agent = self.agents[role]
            with self.lock:
                self.receive(role)
            try:
                reply = self.call(agent)
            except MemberLimit as error:
                # Snapshot in the halted owner's thread, not the coordinator:
                # peers must still be able to start later turns during export.
                self.halt_member(error)
                raise
            calls = reply.message.get("tool_calls") or []
            if calls:
                if self.stopping.is_set() or self.should_stop() or self.time_expired():
                    agent.refuse(calls)
                else:
                    agent.answer(calls)
            elif role != self.final_role:
                self.worker_report(agent, reply.message.get("content") or "")
            return reply

        active = {}
        failure = None
        with ThreadPoolExecutor(max_workers=len(order)) as pool:
            try:
                while True:
                    with self.lock:
                        self.wakeup.clear()
                        if self.should_stop():
                            raise TeamLimit("interrupted")
                        if self.time_expired():
                            raise TeamLimit('time_limit')
                        if not active and not any(self.runnable(r) for r in order):
                            result = self.idle_outcome()
                            if result is not None:
                                return result
                        busy = set(active.values())
                        for role in order:
                            if role not in busy and self.runnable(role):
                                future = pool.submit(turn, role)
                                active[future] = role
                                future.add_done_callback(lambda _: self.wakeup.set())
                        if not active:
                            return dict(status="incomplete", reason="team_waiting_without_messages")
                    if not any(f.done() for f in active):
                        self.wakeup.wait(0.1)  # Timeout only polls the external stop callback.
                    done = {f for f in active if f.done()}
                    for future in done:
                        role = active.pop(future)
                        try:
                            reply = future.result()
                        except RetryTurn:
                            with self.lock:
                                self.ready[role] = True
                            continue
                        except MemberLimit as error:
                            if error.role not in self.halted:
                                self.halt_member(error)
                            continue
                        with self.lock:
                            if reply.message.get("tool_calls"):
                                continue
                            self.ready[role] = False
                            content = reply.message.get("content") or ""
                            if role != self.final_role:
                                continue  # Owner turn already captured and reported its submission.
                            elif active or not self.ready_to_finalize():
                                self.defer_final(self.agents[role])
                                # Reports generated during this model call must
                                # enter a fresh decision, never retroactively.
                                self.ready[role] = bool(self.inbox[role] or self.controls[role])
                            else:
                                result = self.accept_final(content, "tasks_submitted")
                                if result:
                                    return result
            except BaseException as error:
                failure = error
                self.stopping.set()
            finally:
                # Join every outstanding call before finalization/trace closure.
                # Provider errors take precedence over a resource-limit result.
                for future in active:
                    try:
                        future.result()
                    except BaseException as error:
                        if failure is None or isinstance(error, ProviderError):
                            failure = error
        if failure:
            raise failure
