"""One isolated LLM context with a tool loop.

An agent's history is append-only: its system prompt, its inputs, its own
replies (reasoning included) and tool results. Nothing is trimmed or shared;
information reaches another agent only through an explicit boundary message.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from .llm import ChatClient, Completion, ProviderError
from .trace import Trace

BUDGET_EXHAUSTED = (
    "Tool budget exhausted: no further calls of this tool are available. "
    "Finish with the information you already have."
)
LENGTH_TRUNCATED = "Not executed: your reply was cut off at the output length limit."
NOT_EXECUTED = "Not executed: no tool calls were allowed in this reply."
# Model-visible reasons for a forced final reply; each precedes the role's final prompt.
TURN_LIMIT_NOTICE = "You have reached the turn limit."
LENGTH_NOTICE = "Your previous reply reached the output length limit before it was finished."
# A reply cut off at the output limit usually spent it all on reasoning; the one
# recovery reply asks for the answer with low effort so it does not run away again.
SALVAGE_EFFORT = "low"


class Budget:
    """Tool-call allowance of one run; every agent draws from the same pool."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.used >= self.limit:
                return False
            self.used += 1
            return True


@dataclass
class Observation:
    text: str
    meta: dict = field(default_factory=dict)
    ref: int | None = None  # trace event that already holds ``text``


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict, "Agent"], Observation]
    budgeted: bool = False  # draws from the run's shared budget
    concurrent: bool = False  # several calls in one reply may run in parallel

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class Outcome:
    text: str
    status: str  # done | turn_limit | length
    turns: int


def tool_message(call: dict, obs: Observation) -> dict:
    return {"role": "tool", "tool_call_id": call["id"], "content": obs.text}


class Agent:
    """One context. ``tools`` run here; ``external`` schemas are executed by the caller."""

    def __init__(
        self,
        name: str,
        client: ChatClient,
        trace: Trace,
        system: str,
        *,
        tools: list[Tool] = (),
        external: list[dict] = (),
        budget: Budget | None = None,
        max_turns: int = 60,
        notice_prefix: str = "",
        max_input_chars: int | None = None,
        usage_role: str | None = None,
    ):
        self.name = name
        self.usage_role = usage_role
        self.max_input_chars = max_input_chars
        self.notice_prefix = notice_prefix  # marks harness notices where the user role is a person
        self.client = client
        self.trace = trace
        self.tools = {tool.name: tool for tool in tools}
        # A fixed order keeps the request prefix byte-identical across calls.
        self.schemas = sorted(
            [tool.schema for tool in tools] + list(external),
            key=lambda schema: schema["function"]["name"],
        )
        self.budget = budget
        self.max_turns = max_turns
        self.messages: list[dict] = []
        self.last_prompt_tokens = 0
        trace.emit(
            "agent_start",
            agent=name,
            usage_role=usage_role,
            tools=[schema["function"]["name"] for schema in self.schemas],
            system_chars=len(system),
        )
        self.append({"role": "system", "content": system})

    def append(self, message: dict, ref: int | None = None) -> None:
        logged = message if ref is None else dict(message, content={"$ref": ref})
        self.trace.emit("message", agent=self.name, idx=len(self.messages), message=logged)
        self.messages.append(message)

    def call(self, tool_choice: str | None = None, effort: str | None = None) -> Completion:
        """One LLM call on the full history; the reply is appended verbatim."""
        if self.max_input_chars is not None and len(json.dumps([self.messages, self.schemas], ensure_ascii=False)) > self.max_input_chars:
            raise ProviderError("context_length", "Configured input character safety limit exceeded")
        completion = self.client.complete(self.messages, self.schemas or None, tool_choice, effort)
        self.last_prompt_tokens = completion.usage["prompt_tokens"]
        self.trace.emit(
            "llm_call",
            agent=self.name,
            context_len=len(self.messages),
            usage_role=self.usage_role,
            finish_reason=completion.finish_reason,
            usage=completion.usage,
            latency=round(completion.latency, 3),
            response_id=completion.response_id,
            tool_choice=tool_choice,
            effort=effort,
            model=self.client.cfg.model,
            served_model=completion.served_model,
            fingerprint=completion.fingerprint,
            raw_usage=completion.raw_usage,
        )
        self.append(completion.message)
        return completion

    def log_tool(self, call: dict, args, obs: Observation) -> Observation:
        if obs.ref is None:
            obs.ref = self.trace.emit(
                "tool_call",
                agent=self.name,
                tool=call["function"]["name"],
                call_id=call["id"],
                args=args,
                observation=obs.text,
                **obs.meta,
            )
        return obs

    def run_tool(self, call: dict) -> Observation:
        name = call["function"]["name"]
        tool = self.tools.get(name)
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
        except json.JSONDecodeError as error:
            obs = Observation(f"Invalid JSON arguments: {error}", {"error": True})
            return self.log_tool(call, None, obs)
        if tool is None:
            obs = Observation(f"Unknown tool: {name}", {"error": True})
        elif tool.budgeted and not self.budget.take():
            obs = Observation(BUDGET_EXHAUSTED, {"budget_exhausted": True})
        else:
            try:
                obs = tool.run(args, self)
            except Exception as error:  # shown to the model like any tool error
                obs = Observation(f"Error executing {name}: {error}", {"error": True})
        return self.log_tool(call, args, obs)

    def answer(self, calls: list[dict]) -> None:
        """Run internal tool calls and append their results in call order."""
        tools = [self.tools.get(call["function"]["name"]) for call in calls]
        if len(calls) > 1 and all(tool is not None and tool.concurrent for tool in tools):
            with ThreadPoolExecutor(len(calls)) as pool:
                results = list(pool.map(self.run_tool, calls))
        else:
            results = [self.run_tool(call) for call in calls]
        for call, obs in zip(calls, results):
            self.append(tool_message(call, obs), obs.ref)

    def refuse(self, calls: list[dict], text: str = NOT_EXECUTED) -> None:
        """Answer calls that must not run, keeping the history valid for later calls."""
        for call in calls:
            obs = self.log_tool(call, None, Observation(text, {"error": True}))
            self.append(tool_message(call, obs), obs.ref)

    def notice(self, reason: str, final_prompt: str) -> dict:
        """A user-role message asking for a forced final reply, with its reason."""
        return {"role": "user", "content": " ".join(filter(None, (self.notice_prefix, reason, final_prompt)))}

    def call_or_salvage(self, final_prompt: str) -> tuple[Completion, bool]:
        """One call; a reply cut off at the output limit gets one short recovery reply.

        Returns the reply to use and whether it is the recovery reply, which was
        requested with tool calls disabled.
        """
        completion = self.call()
        if completion.finish_reason != "length":
            return completion, False
        self.refuse(completion.message.get("tool_calls") or [], LENGTH_TRUNCATED)
        self.append(self.notice(LENGTH_NOTICE, final_prompt))
        return self.call(tool_choice="none", effort=SALVAGE_EFFORT), True

    def run(self, prompt: str | None, final_prompt: str, prompt_ref: int | None = None) -> Outcome:
        """Work on one input until a reply without tool calls or the turn limit."""
        if prompt is not None:
            self.append({"role": "user", "content": prompt}, prompt_ref)
        for turn in range(1, self.max_turns + 1):
            completion, salvaged = self.call_or_salvage(final_prompt)
            calls = completion.message.get("tool_calls") or []
            text = completion.message.get("content") or ""
            if salvaged or completion.finish_reason == "length":
                self.refuse(calls)
                return Outcome(text, "length" if completion.finish_reason == "length" else "salvaged", turn)
            if not calls:
                return Outcome(text, "done", turn)
            self.answer(calls)
        self.append(self.notice(TURN_LIMIT_NOTICE, final_prompt))
        completion = self.call(tool_choice="none")
        self.refuse(completion.message.get("tool_calls") or [])
        return Outcome(completion.message.get("content") or "", "turn_limit", self.max_turns + 1)
