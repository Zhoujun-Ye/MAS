"""τ²-bench agents for conditions C0-C4, run by τ²'s own orchestrator and evaluator.

C0 is one agent with the domain tools. C1-C4 split it into a front desk (talks
with the user, holds the policy, has no database tools) and an operator (the
database tools and the policy; never talks with the user). The operator's
tool calls are emitted as this agent's calls, so τ² executes and scores them
exactly as in C0. One budget counts the environment calls of all agents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel
from tau2.agent.base_agent import HalfDuplexAgent
from tau2.data_model.message import (
    AssistantMessage,
    MultiToolMessage,
    ToolCall,
    UserMessage,
)

from .. import relay
from ..agent import BUDGET_EXHAUSTED, Agent, Budget, Observation, tool_message
from ..llm import ChatClient, Completion
from ..relay import CONDITIONS, ArtifactStore
from ..trace import Trace
from . import prompts

NOT_EXECUTED = "Not executed: no tool calls were allowed in this reply."


class TeamState(BaseModel):
    """τ² passes a state object around; the contexts live on the agent itself."""


@dataclass
class TeamContext:
    condition: str
    client: ChatClient
    trace: Trace
    tool_calls: int
    max_turns: int
    max_delegations: int


# Run id -> context. τ² builds agents by registered name, so the factory
# receives the run id through ``llm_args`` and looks its context up here.
CONTEXTS: dict[str, TeamContext] = {}


def create_team_agent(tools, domain_policy, **kwargs):
    return TeamAgent(tools, domain_policy, CONTEXTS[kwargs["llm_args"]["mas_run"]])


class TeamAgent(HalfDuplexAgent[TeamState]):
    def __init__(self, tools, domain_policy: str, ctx: TeamContext):
        super().__init__(tools=tools, domain_policy=domain_policy)
        structure, self.relay = CONDITIONS[ctx.condition]
        if structure not in ("single", "team"):
            raise ValueError(f"{ctx.condition} is not defined for τ²-bench")
        self.ctx = ctx
        self.trace = ctx.trace
        self.budget = Budget(ctx.tool_calls)
        self.env_tools = {tool.name for tool in tools}
        env_schemas = [tool.openai_schema for tool in tools]
        self.store = ArtifactStore(self.trace) if self.relay == "reference" else None

        def agent(name, role, **kwargs) -> Agent:
            system = prompts.system_prompt(role, self.relay, domain_policy)
            return Agent(
                name, ctx.client, self.trace, system, budget=self.budget, max_turns=ctx.max_turns, **kwargs
            )

        if structure == "single":
            self.front = agent("single", "single", external=env_schemas)
            self.operator = None
        else:
            front_tools = [self.store.read_tool()] if self.store else []
            operator_tools = [self.store.write_tool(), self.store.read_tool()] if self.store else []
            self.front = agent("frontdesk", "front", tools=front_tools, external=[prompts.DELEGATE])
            self.operator = agent("operator", "operator", tools=operator_tools, external=env_schemas)
        self.queue: list[dict] = []  # front-desk calls still to answer
        self.delegation: dict | None = None  # the open delegate call
        self.waiting: tuple | None = None  # (agent, calls, answered) awaiting τ² results
        self.front_turns = 0
        self.delegations = 0

    # τ² protocol ---------------------------------------------------------

    def get_init_state(self, message_history=None) -> TeamState:
        for message in message_history or []:  # τ²'s scripted greeting
            if not isinstance(message, (AssistantMessage, UserMessage)) or message.is_tool_call():
                raise ValueError("Seeded histories with tool calls are not supported")
            if isinstance(message, AssistantMessage):
                # Scripted text has no reasoning; an empty field keeps passback valid.
                entry = {"role": "assistant", "content": message.content or "", "reasoning_content": ""}
            else:
                entry = {"role": "user", "content": message.content or ""}
            self.front.append(entry)
        return TeamState()

    def set_seed(self, seed: int) -> None:
        self.trace.emit("seed", seed=seed)  # DeepSeek has no seed; recorded only

    def generate_next_message(self, message, state: TeamState):
        if isinstance(message, UserMessage):
            self.front_turns = 0
            self.front.append({"role": "user", "content": message.content or ""})
            return self._advance_front(), state
        results = message.tool_messages if isinstance(message, MultiToolMessage) else [message]
        if self._receive(results) is self.operator:
            reply = self._advance_operator()
            if reply is not None:
                return reply, state
        return self._advance_front(), state

    # Front desk ----------------------------------------------------------

    def _advance_front(self) -> AssistantMessage:
        """Run the front desk until it messages the user or waits on the environment."""
        while True:
            while self.queue:
                call = self.queue.pop(0)
                if call["function"]["name"] == "delegate":
                    reply = self._delegate(call)
                    if reply is not None:
                        return reply
                else:
                    obs = self.front.run_tool(call)
                    self.front.append(tool_message(call, obs), obs.ref)
            if self.front_turns >= self.ctx.max_turns:
                self.front.append({"role": "user", "content": prompts.TURN_LIMIT_USER})
                return self._to_user(self.front.call(tool_choice="none"))
            completion = self.front.call()
            self.front_turns += 1
            calls = completion.message.get("tool_calls") or []
            if not calls:
                return self._to_user(completion)
            if self.operator is None:
                reply = self._send(self.front, calls)
                if reply is not None:
                    return reply
            else:
                self.queue = list(calls)

    def _to_user(self, completion: Completion) -> AssistantMessage:
        self._refuse(self.front, completion)
        return AssistantMessage(role="assistant", content=completion.message.get("content") or "")

    def _refuse(self, agent: Agent, completion: Completion) -> None:
        """Answer calls made despite tool_choice="none", keeping the history valid."""
        for call in completion.message.get("tool_calls") or []:
            obs = agent.log_tool(call, None, Observation(NOT_EXECUTED, {"error": True}))
            agent.append(tool_message(call, obs), obs.ref)

    def _dialogue(self) -> str:
        """The conversation with the user so far (C3 downward 'original task')."""
        lines = []
        for message in self.front.messages[1:]:
            content = message.get("content") or ""
            if message["role"] == "user" and not content.startswith("[System notice]"):
                lines.append(f"User: {content}")
            elif message["role"] == "assistant" and not message.get("tool_calls") and content:
                lines.append(f"Front desk: {content}")
        return "\n".join(lines)

    def _delegate(self, call: dict) -> AssistantMessage | None:
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
            request = str(args.get("request") or "").strip()
        except (json.JSONDecodeError, AttributeError):
            args, request = None, ""
        if not request or self.delegations >= self.ctx.max_delegations:
            text = (
                "delegate needs a non-empty request."
                if not request
                else f"Delegation limit of {self.ctx.max_delegations} reached; continue without the operator."
            )
            obs = self.front.log_tool(call, args, Observation(text, {"error": True}))
            self.front.append(tool_message(call, obs), obs.ref)
            return None
        self.delegations += 1
        notes = relay.working_notes(self.front.messages) if self.relay == "full" else None
        content = relay.brief(self.relay, request, original=self._dialogue(), notes=notes)
        down = self.trace.emit(
            "boundary_msg",
            edge="frontdesk->operator",
            direction="down",
            relay=self.relay,
            content=content,
            task=request,
        )
        self.delegation = {
            "call": call,
            "down": down,
            "start": len(self.operator.messages),
            "artifacts": self.store.count() if self.store else 0,
            "turns": 0,
        }
        self.operator.append({"role": "user", "content": content}, down)
        return self._advance_operator()

    # Operator ------------------------------------------------------------

    def _advance_operator(self) -> AssistantMessage | None:
        """Run the operator until it emits environment calls (returned) or reports (None)."""
        delegation = self.delegation
        while True:
            if delegation["turns"] >= self.ctx.max_turns:
                self.operator.append({"role": "user", "content": prompts.TURN_LIMIT_REPORT})
                completion = self.operator.call(tool_choice="none")
                self._refuse(self.operator, completion)
                status = "turn_limit"
                break
            completion = self.operator.call()
            delegation["turns"] += 1
            calls = completion.message.get("tool_calls") or []
            if not calls:
                status = "done"
                break
            reply = self._send(self.operator, calls)
            if reply is not None:
                return reply
        report = completion.message.get("content") or ""
        attachment = None
        start = delegation["start"]
        if self.relay == "full":
            attachment = relay.tool_log(self.operator.messages[start:], self.operator.refs[start:])
        elif self.relay == "reference":
            attachment = self.store.index(self.operator.name, after=delegation["artifacts"])
        extra = {}
        if self.relay == "structured":
            extra["schema_valid"] = relay.parse_structured(report) is not None
        delivered = relay.deliver(self.relay, report, attachment)
        up = self.trace.emit(
            "boundary_msg",
            edge="operator->frontdesk",
            direction="up",
            relay=self.relay,
            content=delivered,
            report=report,
            attachment=attachment,
            status=status,
            reply_to=f"m{delegation['down']}",
            **extra,
        )
        self.front.append({"role": "tool", "tool_call_id": delegation["call"]["id"], "content": delivered}, up)
        self.delegation = None
        return None

    # Environment calls ---------------------------------------------------

    def _send(self, agent: Agent, calls: list[dict]) -> AssistantMessage | None:
        """Answer internal calls now; hand environment calls to τ² and wait for results."""
        answered: dict[str, Observation] = {}
        outgoing: list[ToolCall] = []
        for call in calls:
            name = call["function"]["name"]
            if name not in self.env_tools:
                answered[call["id"]] = agent.run_tool(call)
                continue
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError as error:
                args, problem = None, f"Invalid JSON arguments: {error}"
            else:
                problem = None if isinstance(args, dict) else "Arguments must be a JSON object."
            if problem is None and not self.budget.take():
                problem = BUDGET_EXHAUSTED
            if problem is not None:
                meta = {"budget_exhausted": True} if problem == BUDGET_EXHAUSTED else {"error": True}
                answered[call["id"]] = agent.log_tool(call, args, Observation(problem, meta))
                continue
            outgoing.append(ToolCall(id=call["id"], name=name, arguments=args, requestor="assistant"))
        if not outgoing:
            self._append_results(agent, calls, answered)
            return None
        self.waiting = (agent, calls, answered)
        return AssistantMessage(role="assistant", tool_calls=outgoing)

    def _receive(self, results) -> Agent:
        agent, calls, answered = self.waiting
        self.waiting = None
        by_id = {result.id: result for result in results}
        for call in calls:
            if call["id"] in answered:
                continue
            result = by_id[call["id"]]
            args = json.loads(call["function"].get("arguments") or "{}")
            text, meta = result.content or "", {"error": result.error}
            if self.store is not None and agent is self.operator:
                label = json.dumps(args, ensure_ascii=False, sort_keys=True)
                artifact_id = self.store.put(agent.name, call["function"]["name"], label, text)
                text, meta = f"[artifact {artifact_id}]\n{text}", {**meta, "artifact_id": artifact_id}
            answered[call["id"]] = agent.log_tool(call, args, Observation(text, meta))
        self._append_results(agent, calls, answered)
        return agent

    @staticmethod
    def _append_results(agent: Agent, calls: list[dict], answered: dict[str, Observation]) -> None:
        for call in calls:
            obs = answered[call["id"]]
            agent.append(tool_message(call, obs), obs.ref)
