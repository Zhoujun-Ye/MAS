"""One BrowseComp-Plus question under one condition (guide §3.2-3.3).

C0: one agent with search and get_document.
C1-C4: a lead researcher without retrieval tools plus up to five search agents,
    differing only in the relay form of their boundary messages.
C5: one agent that works through C1's sub-tasks in order within one context.
"""

from __future__ import annotations

import re
import threading

from .. import relay
from ..agent import Agent, Budget, Observation, Tool
from ..llm import ChatClient
from ..relay import CONDITIONS, ArtifactStore
from ..trace import Trace, read_trace
from . import prompts
from .tools import artifact_label

EXACT_ANSWER = re.compile(r"Exact Answer:\s*(.+)", re.IGNORECASE)


def exact_answer(response: str) -> str | None:
    match = EXACT_ANSWER.search(response or "")
    return match.group(1).strip() if match else None


class Team:
    """Lead researcher plus search agents for conditions C1-C4."""

    def __init__(self, relay_name, client, trace, budget, search_tools, settings, question):
        self.relay = relay_name
        self.client = client
        self.trace = trace
        self.budget = budget
        self.search_tools = search_tools
        self.settings = settings
        self.question = question
        self.store = ArtifactStore(trace) if relay_name == "reference" else None
        self.workers: dict[str, Agent] = {}
        self.locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        lead_tools = [self._dispatch_tool()]
        if self.store:
            lead_tools.append(self.store.read_tool())
        self.lead = Agent(
            "lead",
            client,
            trace,
            prompts.system_prompt("lead", relay_name, settings),
            tools=lead_tools,
            budget=budget,
            max_turns=settings["max_turns"],
        )

    def _worker_tools(self) -> list[Tool]:
        if self.store is None:
            return list(self.search_tools)
        stored = [self.store.saving(tool, artifact_label(tool.name)) for tool in self.search_tools]
        return stored + [self.store.write_tool(), self.store.read_tool()]

    def _dispatch_tool(self) -> Tool:
        return Tool(
            "dispatch",
            "Give a research task to a search agent and wait for its report.",
            {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task for the search agent."},
                    "agent": {
                        "type": "string",
                        "description": "Id of an existing search agent (e.g. search_2) to continue; "
                        "omit to start a new search agent.",
                    },
                },
                "required": ["task"],
            },
            self._dispatch,
            concurrent=True,
        )

    def _dispatch(self, args: dict, lead: Agent) -> Observation:
        task = str(args.get("task") or "").strip()
        if not task:
            return Observation("dispatch needs a non-empty task.", {"error": True})
        limit = self.settings["max_workers"]
        with self._lock:
            name = str(args.get("agent") or "").strip()
            if name:
                if name not in self.workers:
                    existing = ", ".join(sorted(self.workers)) or "none"
                    return Observation(f"Unknown search agent {name}; existing: {existing}.", {"error": True})
            elif len(self.workers) >= limit:
                return Observation(
                    f"All {limit} search agents exist; pass agent=<id> to give one of them another task.",
                    {"error": True},
                )
            else:
                name = f"search_{len(self.workers) + 1}"
                self.workers[name] = Agent(
                    name,
                    self.client,
                    self.trace,
                    prompts.system_prompt("worker", self.relay, self.settings),
                    tools=self._worker_tools(),
                    budget=self.budget,
                    max_turns=self.settings["max_turns"],
                )
                self.locks[name] = threading.Lock()
        with self.locks[name]:
            return self._assign(self.workers[name], task, lead)

    def _assign(self, worker: Agent, task: str, lead: Agent) -> Observation:
        notes = relay.working_notes(lead.messages) if self.relay == "full" else None
        content = relay.brief(self.relay, task, original=self.question, notes=notes)
        down = self.trace.emit(
            "boundary_msg",
            edge=f"lead->{worker.name}",
            direction="down",
            relay=self.relay,
            content=content,
            task=task,
        )
        start = len(worker.messages)
        before = self.store.count() if self.store else 0
        outcome = worker.run(content, prompts.FINAL_REPORT, prompt_ref=down)
        attachment = None
        if self.relay == "full":
            attachment = relay.tool_log(worker.messages[start:], worker.refs[start:])
        elif self.relay == "reference":
            attachment = self.store.index(worker.name, after=before)
        extra = {}
        if self.relay == "structured":
            extra["schema_valid"] = relay.parse_structured(outcome.text) is not None
        delivered = relay.deliver(self.relay, outcome.text, attachment)
        up = self.trace.emit(
            "boundary_msg",
            edge=f"{worker.name}->lead",
            direction="up",
            relay=self.relay,
            content=delivered,
            report=outcome.text,
            attachment=attachment,
            status=outcome.status,
            reply_to=f"m{down}",
            **extra,
        )
        return Observation(delivered, ref=up)


def solve(
    task: dict,
    condition: str,
    *,
    client: ChatClient,
    search_tools: list[Tool],
    trace: Trace,
    settings: dict,
    subtasks: list[str] | None = None,
) -> dict:
    """Run one question; returns the decider's response and how it ended."""
    structure, relay_name = CONDITIONS[condition]
    budget = Budget(settings["tool_calls"])
    question = task["query"]
    if structure == "team":
        team = Team(relay_name, client, trace, budget, search_tools, settings, question)
        decider = team.lead
        outcome = decider.run(prompts.QUESTION.format(question=question), prompts.FINAL_ANSWER)
    else:
        decider = Agent(
            "single",
            client,
            trace,
            prompts.system_prompt(structure, None, settings),
            tools=search_tools,
            budget=budget,
            max_turns=settings["max_turns"],
        )
        if structure == "single":
            outcome = decider.run(prompts.QUESTION.format(question=question), prompts.FINAL_ANSWER)
        else:
            n = len(subtasks)
            for i, subtask in enumerate(subtasks, start=1):
                text = (
                    prompts.SUBTASK_FIRST.format(question=question, n=n, task=subtask)
                    if i == 1
                    else prompts.SUBTASK.format(i=i, n=n, task=subtask)
                )
                decider.run(text, prompts.FINAL_REPORT)
            outcome = decider.run(prompts.SUBTASKS_DONE, prompts.FINAL_ANSWER)
    trace.emit(
        "final",
        agent=decider.name,
        answer=exact_answer(outcome.text),
        response=outcome.text,
        status=outcome.status,
        context_tokens=decider.last_prompt_tokens,
    )
    retrieved = {
        docid
        for event in read_trace(trace.path)
        if event["type"] == "tool_call" and event["tool"] == "search"
        for docid in event.get("docids", [])
    }
    complete = outcome.status != "length" and bool(outcome.text.strip())
    return {
        # Fields of the official run format, so its evaluator can read these files too.
        "query_id": task["query_id"],
        "status": "completed" if complete else "incomplete",
        "retrieved_docids": sorted(retrieved),
        "result": [{"type": "output_text", "output": outcome.text}],
        "final_status": outcome.status,
        "decider": decider.name,
        "answer": exact_answer(outcome.text),
        "tool_budget_used": budget.used,
    }
