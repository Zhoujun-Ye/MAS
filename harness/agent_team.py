"""Bounded leader-led team with persistent contexts and queued peer handoffs.

Scheduling is deterministic round-robin, not simultaneous threads. Workers remain
independent and can message any selected peer; no recursive nested agent calls.
Every condition receives the same frozen team, domain permissions and budgets.
"""
from collections import deque
from copy import deepcopy
import json

from .agent import Agent, Budget, Observation, Tool
from .config import digest
from .communication import FORMS, STRUCTURED_SCHEMA, valid_record
from .llm import ProviderError
from .pool import POOL

COMMUNICATION = {"send_message", "read_evidence", "request_evidence"}


class TeamLimit(Exception):
    pass


class AgentTeam:
    def __init__(self, spec, form, client, trace, tools, permissions, *,
                 tool_budget=20, max_calls=32, max_messages=16, max_reads=8,
                 max_input_chars=200_000):
        if form not in FORMS or min(tool_budget, max_calls, max_messages, max_reads, max_input_chars) <= 0:
            raise ValueError("Invalid handoff form or limits")
        self.spec, self.form, self.client, self.trace = spec, form, client, trace
        self.domain = {t.name: t for t in tools}
        if len(self.domain) != len(tools) or self.domain.keys() & COMMUNICATION:
            raise ValueError("Duplicate or reserved domain tool name")
        names = {m.role for m in spec.members}
        if set(permissions) != names or any(not set(v) <= self.domain.keys() for v in permissions.values()):
            raise ValueError("Permissions must bind every selected role to available tools")
        self.permissions = {k: tuple(sorted(v)) for k, v in permissions.items()}
        self.budget, self.read_budget = Budget(tool_budget), Budget(max_reads)
        self.max_calls, self.max_messages = max_calls, max_messages
        self.max_input_chars = max_input_chars
        self.calls = self.sent = 0
        self.limit_reason = None
        self.agents, self.evidence, self.access = {}, {}, {n: set() for n in names}
        self.pending, self.inbox = [], {n: deque() for n in names}
        self.started = False
        self.limits = dict(tool_budget=tool_budget, max_calls=max_calls, max_messages=max_messages,
                           max_reads=max_reads, max_input_chars=max_input_chars)
        self.control = dict(team=spec.payload(), model=vars(client.cfg), limits=self.limits,
                            prompts={n: POOL[n].system for n in sorted(names)},
                            domain_permissions=self.permissions,
                            domain_schemas=[self.domain[n].schema for n in sorted(self.domain)],
                            scheduler="round-robin-v1", communication="queued-v1")
        self.control_digest = digest(self.control)

    def call(self, agent, **kwargs):
        if self.calls >= self.max_calls:
            raise TeamLimit("model_call_limit")
        self.calls += 1  # Includes handoff encoding, not only workers.
        try:
            reply = agent.call(**kwargs)
        except ProviderError as error:
            if error.kind == "context_length":
                raise TeamLimit("context_length") from error
            raise  # Provider/key/balance failures belong to runner recovery.
        if reply.finish_reason == "length":
            agent.refuse(reply.message.get("tool_calls") or [])
            raise TeamLimit("output_length")
        return reply

    def domain_tool(self, original):
        def run(args, agent):
            obs = original.run(args, agent)
            key = f"e{len(self.evidence) + 1}"
            self.evidence[key] = dict(owner=agent.name, tool=original.name, arguments=args, text=obs.text)
            self.access[agent.name].add(key)
            self.trace.emit("evidence", evidence_id=key, **self.evidence[key])
            return Observation(json.dumps({"evidence_id": key, "observation": obs.text}, ensure_ascii=False), obs.meta)
        return Tool(original.name, original.description, original.parameters, run, budgeted=True)

    def queue(self, sender, recipient, content, evidence_ids):
        if recipient not in self.inbox or recipient == sender:
            raise ValueError("Recipient must be a different selected teammate")
        if not isinstance(content, str) or not isinstance(evidence_ids, list) or not all(isinstance(k, str) for k in evidence_ids):
            raise ValueError("Invalid message or evidence list")
        if not set(evidence_ids) <= self.access[sender]:
            raise ValueError("Cannot grant evidence you have not received or produced")
        if self.sent >= self.max_messages:
            self.limit_reason = "message_limit"
            raise TeamLimit("message_limit")
        self.sent += 1
        message_id = f"m{self.sent}"
        self.trace.emit("peer_queued", message_id=message_id, sender=sender, recipient=recipient,
                        intent=content, evidence_ids=evidence_ids)
        self.pending.append((message_id, sender, recipient, content, evidence_ids))

    def communication_tools(self):
        def send(args, agent):
            self.queue(agent.name, args["recipient"], args["content"], args.get("evidence_ids", []))
            return Observation("Queued for delivery after this turn.", {"communication": True})

        def read(args, agent):
            if self.form not in ("document_retrieval", "adaptive"):
                return Observation("Original-evidence reads are disabled in this handoff condition.")
            if not self.read_budget.take():
                return Observation("Communication read limit reached.", {"communication_limit": True})
            key = args["id"]
            if key not in self.access[agent.name]:
                return Observation("Evidence not granted to this recipient.", {"error": True})
            return Observation(json.dumps(self.evidence[key], ensure_ascii=False), {"communication": True})

        def request(args, agent):
            if self.form != "adaptive":
                return Observation("Evidence search is disabled in this handoff condition.")
            if not self.read_budget.take():
                return Observation("Communication read limit reached.", {"communication_limit": True})
            query = args["query"].strip().casefold()
            if not query:
                return Observation("A non-empty exact text fragment is required.", {"error": True})
            matches = [{"id": key, **self.evidence[key]} for key in sorted(self.access[agent.name])
                       if query in self.evidence[key]["text"].casefold()]
            return Observation(json.dumps(matches, ensure_ascii=False), {"communication": True})

        return [
            Tool("send_message", "Send findings, requests or corrections directly to a selected teammate.",
                 {"type": "object", "properties": {"recipient": {"type": "string"}, "content": {"type": "string"},
                 "evidence_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["recipient", "content"]}, send),
            Tool("read_evidence", "Read a granted original observation, when enabled by the handoff condition.",
                 {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}, read),
            Tool("request_evidence", "Search granted evidence by exact text fragment, when enabled by the handoff condition.",
                 {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, request),
        ]

    def deliver(self):
        while self.pending:
            message_id, sender, recipient, intent, ids = self.pending.pop(0)
            agent = self.agents[sender]
            if self.form == "full_context":
                payload = {"intent": intent, "trajectory": deepcopy(agent.messages)}
            else:
                encoder = Agent(f"handoff_{self.sent}_{sender}_{recipient}_{self.calls}", self.client, self.trace,
                                agent.messages[0]["content"], external=deepcopy(agent.schemas),
                                usage_role="handoff", max_input_chars=self.max_input_chars)
                for message in agent.messages[1:]:
                    encoder.append(deepcopy(message))
                instruction = "Compress the sender's findings for this recipient. Preserve decision-critical facts and qualifiers."
                if self.form == "structured":
                    instruction += " Return only JSON with this schema: " + json.dumps(STRUCTURED_SCHEMA)
                elif self.form == "adaptive":
                    instruction += " Select what this recipient needs; identify missing evidence and useful follow-up questions."
                encoder.append({"role": "user", "content": json.dumps(dict(
                    handoff_instruction=instruction, recipient=recipient,
                    assignment=next(m.assignment for m in self.spec.members if m.role == recipient),
                    intent=intent, evidence_ids=ids), ensure_ascii=False)})
                reply = self.call(encoder, tool_choice="none")
                if reply.message.get("tool_calls"):
                    encoder.refuse(reply.message["tool_calls"])
                    raise TeamLimit("invalid_handoff_tool_call")
                payload = reply.message.get("content") or ""
                if self.form == "structured" and not valid_record(payload):
                    raise TeamLimit("invalid_structured_handoff")
            refs = ids if self.form in ("document_retrieval", "adaptive") else []
            packet = dict(message_id=message_id, sender=sender, recipient=recipient, form=self.form, payload=payload, evidence_ids=refs)
            self.trace.emit("peer_handoff", **packet, sender_context_len=len(agent.messages), sender_context_digest=digest(agent.messages))
            self.inbox[recipient].append(packet)
            self.access[recipient].update(refs)

    def run_task(self, request):
        if self.started:
            raise ValueError("Team instances cannot be reused for later requests")
        self.spec.validate_task(request)
        self.started = True
        self.trace.emit("team_spec", control_digest=self.control_digest, control=self.control, form=self.form)
        solo = len(self.spec.members) == 1
        final_role = self.spec.members[0].role if solo else "leader"
        order = [m.role for m in self.spec.members if m.role != final_role] + [final_role]
        ready = dict.fromkeys(order, True)
        for member in self.spec.members:
            role = member.role
            tools = [self.domain_tool(self.domain[name]) for name in self.permissions[role]]
            if not solo:
                tools += self.communication_tools()
            agent = Agent(role, self.client, self.trace, POOL[role].system, tools=tools,
                          budget=self.budget, max_input_chars=self.max_input_chars, usage_role=role)
            agent.append({"role": "user", "content": json.dumps(dict(
                request=request, assignment=member.assignment, team=self.spec.payload(),
                handoff_form=self.form), ensure_ascii=False)})
            self.agents[role] = agent
        try:
            while any(ready.values()) or any(self.inbox.values()):
                for role in order:
                    agent = self.agents[role]
                    while self.inbox[role]:
                        packet = self.inbox[role].popleft()
                        agent.append({"role": "user", "content": json.dumps({"incoming_handoff": packet}, ensure_ascii=False)})
                        ready[role] = True
                        self.trace.emit("peer_delivery", message_id=packet["message_id"], sender=packet["sender"], recipient=role,
                                        context_len=len(agent.messages))
                    if not ready[role]:
                        continue
                    reply = self.call(agent)
                    calls = reply.message.get("tool_calls") or []
                    if calls:
                        agent.answer(calls)
                        if self.limit_reason:
                            raise TeamLimit(self.limit_reason)
                    else:
                        ready[role] = False
                        content = reply.message.get("content") or ""
                        if role == final_role:
                            if any(ready.values()) or any(self.inbox.values()):
                                agent.append({"role": "user", "content": "Teammates still have pending work. Coordinate or wait for their reports before finalizing."})
                                ready[role] = True
                            else:
                                self.trace.emit("final", agent=role, content=content)
                                return dict(status="completed", final=content, control_digest=self.control_digest,
                                            calls=self.calls, tool_calls=self.budget.used)
                        elif not solo:
                            self.queue(role, final_role, content, sorted(self.access[role]))
                    self.deliver()
            return dict(status="incomplete", reason="no_final")
        except TeamLimit as error:
            return dict(status="incomplete", reason=str(error), calls=self.calls, tool_calls=self.budget.used)
