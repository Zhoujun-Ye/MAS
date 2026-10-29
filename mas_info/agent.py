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

from .llm import ChatClient, Completion
from .trace import Trace

BUDGET_EXHAUSTED = (
    "Tool budget exhausted: no further calls of this tool are available. "
    "Finish with the information you already have."
)
LENGTH_TRUNCATED = "Not executed: your reply was cut off at the output length limit."


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
    ):
        self.name = name
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
        self.refs: list[int | None] = []
        self.last_prompt_tokens = 0
        trace.emit(
            "agent_start",
            agent=name,
            tools=[schema["function"]["name"] for schema in self.schemas],
            system_chars=len(system),
        )
        self.append({"role": "system", "content": system})

    def append(self, message: dict, ref: int | None = None) -> None:
        logged = message if ref is None else dict(message, content={"$ref": ref})
        self.trace.emit("message", agent=self.name, idx=len(self.messages), message=logged)
        self.messages.append(message)
        self.refs.append(ref)

    def call(self, tool_choice: str | None = None) -> Completion:
        """One LLM call on the full history; the reply is appended verbatim."""
        completion = self.client.complete(self.messages, self.schemas or None, tool_choice)
        self.last_prompt_tokens = completion.usage["prompt_tokens"]
        self.trace.emit(
            "llm_call",
            agent=self.name,
            context_len=len(self.messages),
            finish_reason=completion.finish_reason,
            usage=completion.usage,
            latency=round(completion.latency, 3),
            response_id=completion.response_id,
            tool_choice=tool_choice,
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

    def run(self, prompt: str | None, final_prompt: str, prompt_ref: int | None = None) -> Outcome:
        """Work on one input until a reply without tool calls or the turn limit."""
        if prompt is not None:
            self.append({"role": "user", "content": prompt}, prompt_ref)
        for turn in range(1, self.max_turns + 1):
            completion = self.call()
            calls = completion.message.get("tool_calls") or []
            text = completion.message.get("content") or ""
            if completion.finish_reason == "length":
                # Keep the history valid for a later assignment without running cut-off calls.
                for call in calls:
                    obs = self.log_tool(call, None, Observation(LENGTH_TRUNCATED, {"error": True}))
                    self.append(tool_message(call, obs), obs.ref)
                return Outcome(text, "length", turn)
            if not calls:
                return Outcome(text, "done", turn)
            self.answer(calls)
        self.append({"role": "user", "content": final_prompt})
        completion = self.call(tool_choice="none")
        return Outcome(completion.message.get("content") or "", "turn_limit", self.max_turns + 1)
