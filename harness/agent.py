"""One isolated LLM context with a tool loop.

An agent's history is append-only: its system prompt, its inputs, its own
replies (reasoning included) and tool results. Nothing is trimmed or shared;
other contexts receive explicit messages and may also read shared tool artifacts.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Callable
from jsonschema import Draft202012Validator

from .llm import ChatClient, Completion, ProviderError
from .trace import Trace

BUDGET_EXHAUSTED = (
    "Your context's domain-tool budget is exhausted. Switching tools cannot restore your allowance. "
    "Report existing evidence and explicitly identify missing verification."
)
LENGTH_TRUNCATED = "Not executed: your reply was cut off at the output length limit."
NOT_EXECUTED = "Not executed: no tool calls were allowed in this reply."


class Budget:
    """Thread-safe lifetime allowance for one context."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.limit is not None and self.used >= self.limit:
                return False
            self.used += 1
            return True

    def snapshot(self) -> dict:
        with self._lock:
            return dict(limit=self.limit, used=self.used, remaining=None if self.limit is None else self.limit - self.used)


class SessionLimit(RuntimeError):
    pass


class ModelDeferred(RuntimeError):
    """Drain active workers before the root's reserved final call."""


class SessionBudget:
    """Atomic shared ceilings. Already in-flight calls cannot be cancelled."""

    def __init__(self, model_calls=40, tool_calls=80, seconds=900, audit_seconds=120):
        if type(model_calls) is not int or type(tool_calls) is not int or model_calls < 1 or tool_calls < 0:
            raise ValueError("Invalid session budgets")
        self.model_limit, self.tool_limit = model_calls, tool_calls
        self.model_used = self.tool_used = 0
        self.report_reservations = {"leader"}
        self.active_workers = set()
        self.limit_events = []
        self.fatal = None
        self.lock = threading.Lock()
        if seconds <= 0 or audit_seconds <= 0:
            raise ValueError("Session seconds must be positive")
        self.seconds = seconds
        self.deadline = None
        self.audit_seconds = audit_seconds
        self.audit_active = self.execution_active = 0
        self.audit_started = self.audit_only_started = None
        self.audit_elapsed = self.audit_excluded = 0.0

    def _audit_times_locked(self, now):
        total = self.audit_elapsed + (now - self.audit_started if self.audit_started is not None else 0)
        excluded = self.audit_excluded + (now - self.audit_only_started if self.audit_only_started is not None else 0)
        return total, excluded

    def _remaining_locked(self, now):
        _, excluded = self._audit_times_locked(now)
        return self.seconds if self.deadline is None else self.deadline + excluded - now

    @contextmanager
    def activity(self, kind):
        """Exclude audit-only wall intervals, never time overlapping an executing model/tool."""
        if kind not in {"audit", "execution"}:
            raise ValueError("Unknown activity")
        with self.lock:
            now = time.monotonic()
            if kind == "audit":
                if self.audit_active == 0:
                    self.audit_started = now
                self.audit_active += 1
                if self.execution_active == 0 and self.audit_only_started is None:
                    self.audit_only_started = now
            else:
                if self.audit_only_started is not None:
                    self.audit_excluded += now - self.audit_only_started
                    self.audit_only_started = None
                self.execution_active += 1
        try:
            yield
        finally:
            with self.lock:
                now = time.monotonic()
                if kind == "audit":
                    self.audit_active -= 1
                    if self.audit_active == 0:
                        self.audit_elapsed += now - self.audit_started
                        self.audit_started = None
                        if self.audit_only_started is not None:
                            self.audit_excluded += now - self.audit_only_started
                            self.audit_only_started = None
                else:
                    self.execution_active -= 1
                    if self.execution_active == 0 and self.audit_active:
                        self.audit_only_started = now

    def remaining_audit_seconds(self):
        with self.lock:
            total, _ = self._audit_times_locked(time.monotonic())
            return max(0, self.audit_seconds - total)

    def start(self):
        with self.lock:
            if self.deadline is None:
                self.deadline = time.monotonic() + self.seconds

    def remaining_seconds(self):
        with self.lock:
            return max(0, self._remaining_locked(time.monotonic()))

    def _check_locked(self):
        if self.fatal is not None:
            raise SessionLimit("stopped_after_fatal")
        if self._remaining_locked(time.monotonic()) <= 0:
            self._limit_locked("session_time_limit")
            raise SessionLimit("session_time_limit")

    def _limit_locked(self, reason, agent=None):
        event = dict(reason=reason, agent=agent)
        if event not in self.limit_events:
            self.limit_events.append(event)

    def record_limit(self, reason, agent=None):
        with self.lock:
            self._limit_locked(reason, agent)

    def stop(self, error):
        with self.lock:
            if self.fatal is None:
                self.fatal = error

    def check(self):
        with self.lock:
            self._check_locked()

    def _report_capacity_locked(self, require_work):
        needed = 2 if require_work else 1
        available = self.model_limit - self.model_used - len(self.report_reservations)
        return dict(required_unreserved_calls=needed, available_unreserved_calls=available,
                    can_start=available >= needed)

    def report_capacity(self, *, require_work=False):
        """Advisory admission check; only reserve_report allocates capacity."""
        with self.lock:
            self._check_locked()
            return self._report_capacity_locked(require_work)

    def reserve_report(self, owner, *, require_work=False, protect_root=False):
        with self.lock:
            self._check_locked()
            if owner in self.report_reservations:
                raise ValueError("Report call already reserved")
            if not self._report_capacity_locked(require_work)["can_start"]:
                self._limit_locked("report_reservation_unavailable", owner)
                return False
            self.report_reservations.add(owner)
            if protect_root:
                self.active_workers.add(owner)
            return True

    def release_report(self, owner):
        with self.lock:
            self.report_reservations.discard(owner)
            self.active_workers.discard(owner)

    def take_model(self, owner, final=False, preflight=None):
        """Choose final mode and preflight atomically before charging a request.

        preflight(forced) must be local-only and must not re-enter this budget.
        A rejected request leaves both usage and report reservations unchanged.
        """
        with self.lock:
            self._check_locked()
            available = self.model_limit - self.model_used - len(self.report_reservations)
            reserved = owner in self.report_reservations
            forced = available <= 0
            use_reservation = reserved and (final or forced)
            if owner == "leader" and use_reservation and self.active_workers:
                raise ModelDeferred("Workers must drain before the leader final call")
            if not use_reservation and available <= 0:
                self._limit_locked("session_model_limit", owner)
                raise SessionLimit("session_model_limit")
            if preflight is not None:
                preflight(forced)
                self._check_locked()
            if use_reservation:
                self.report_reservations.remove(owner)
            self.model_used += 1
            if forced:
                self._limit_locked("session_model_limit", owner)
            return forced

    def admit_tool(self, local=None):
        """Linearization point for ALL tools, after preflight, before execution.

        Actions admitted before a stop are in flight; stopping cannot undo them.
        """
        with self.lock:
            self._check_locked()
            if local is None:
                return None
            if self.tool_used >= self.tool_limit:
                self._limit_locked("session_tool_limit")
                return "session_tool_limit"
            if not local.take():
                return "agent_tool_limit"
            self.tool_used += 1
            return None

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            audit, excluded = self._audit_times_locked(now)
            wall = 0 if self.deadline is None else now - (self.deadline - self.seconds)
            return dict(model_calls=self.model_used, model_limit=self.model_limit,
                        tool_calls=self.tool_used, tool_limit=self.tool_limit,
                        model_calls_remaining=self.model_limit-self.model_used,
                        model_calls_unreserved=self.model_limit-self.model_used-len(self.report_reservations),
                        tool_calls_remaining=self.tool_limit-self.tool_used,
                        leader_reserved_calls=int("leader" in self.report_reservations),
                        child_reserved_calls=len(self.report_reservations - {"leader"}),
                        limit_events=[dict(event) for event in self.limit_events],
                        time_limit_seconds=self.seconds,
                        audit_time_limit_seconds=self.audit_seconds, audit_wall_seconds=audit,
                        audit_excluded_seconds=excluded, wall_seconds=wall, execution_seconds=wall-excluded)


@dataclass
class Observation:
    text: str
    meta: dict = field(default_factory=dict)
    ref: int | None = None  # trace event that already holds ``text``
    submission_text: str | None = None  # Runtime export, distinct from model-visible receipt.


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict, "Agent"], Observation]
    budgeted: bool = False  # draws from the owning agent's configured budget
    concurrent: bool = False  # several calls in one reply may run in parallel
    preflight: Callable[[dict, "Agent"], Observation | None] | None = None
    read_only: bool = False  # Explicit trusted capability, never inferred from shell text.
    sole: bool = False  # Yielding controls cannot be mixed with other calls.

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
    status: str  # invocation termination, not task correctness or error history
    turns: int


def tool_message(call: dict, obs: Observation) -> dict:
    return {"role": "tool", "tool_call_id": call["id"], "content": obs.text}


def parse_tool_arguments(raw):
    def invalid_constant(value):
        raise ValueError(f"Non-JSON value: {value}")
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate argument key: {key}")
            result[key] = value
        return result
    return json.loads(raw or "{}", parse_constant=invalid_constant, object_pairs_hook=unique_keys)


class Agent:
    """One context with explicit executable tools and an optional submission tool."""

    def __init__(
        self,
        name: str,
        client: ChatClient,
        trace: Trace,
        system: str,
        *,
        tools: list[Tool] = (),
        budget: Budget | None = None,
        max_turns: int = 60,
        usage_role: str | None = None,
        session_budget: SessionBudget | None = None,
        max_concurrent_tools: int = 4,
        response_format: dict | None = None,
        submission_tool: str | None = None,
    ):
        if response_format is not None and response_format not in ({"type": "json_object"}, {"type": "text"}):
            raise ValueError("Unsupported response_format")
        self.response_format = dict(response_format) if response_format is not None else None
        self.name = name
        self.usage_role = usage_role
        self.submission_tool = submission_tool
        self.submission = None
        self.model_calls = self.tool_calls = 0
        self._counter_lock = threading.Lock()
        self.last_final_reason = None
        self.client = client
        self.session_budget = session_budget
        self.max_concurrent_tools = max_concurrent_tools
        self.tool_gate = None
        self._call_local = threading.local()
        self.last_call_final = False
        self.final_prompt = "Return the final report and identify unfinished work."
        self.trace = trace
        self.tools = {tool.name: tool for tool in tools}
        if submission_tool is not None and submission_tool not in self.tools:
            raise ValueError("Submission tool must be registered")
        # A fixed order keeps the request prefix byte-identical across calls.
        self.schemas = sorted(
            [tool.schema for tool in tools],
            key=lambda schema: schema["function"]["name"],
        )
        self.budget = budget
        self.budget_exhausted = False
        self.tool_events = []
        self.max_turns = max_turns
        self.messages: list[dict] = []
        self.invocation_turns = 0
        self.last_text = ""
        self.last_prompt_tokens = 0
        self.last_input_length = 0
        trace.emit(
            "agent_start",
            agent=name,
            usage_role=usage_role,
            tools=[schema["function"]["name"] for schema in self.schemas],
            system_chars=len(system),
            max_turns=max_turns,
            tool_budget=self.budget.limit if self.budget is not None else None,
        )
        self.append({"role": "system", "content": system})

    def append(self, message: dict, ref: int | None = None) -> None:
        logged = message if ref is None else dict(message, content={"$ref": ref})
        self.trace.emit("message", agent=self.name, idx=len(self.messages), message=logged)
        self.messages.append(message)

    @property
    def active_tool_call_id(self):
        return getattr(self._call_local, "call_id", None)

    @active_tool_call_id.setter
    def active_tool_call_id(self, value):
        self._call_local.call_id = value

    def call(self, tool_choice: str | None = None, effort: str | None = None, *, final_reason=None) -> Completion:
        """One LLM call on the full history; the reply is appended verbatim."""
        self.last_call_final = tool_choice == "none"
        self.last_final_reason = (final_reason or "turn_limit") if self.last_call_final else None

        def preflight(forced):
            nonlocal tool_choice
            if forced:
                self.last_final_reason = "session_model_limit"
            if forced and not self.last_call_final:
                self.append(self.notice("This is the reserved final session call. Finish now.", self.final_prompt))
                tool_choice = "none"
                self.last_call_final = True
            capacity = self.input_capacity()
            self.trace.emit('input_capacity', agent=self.name, context_len=len(self.messages),
                            final_reason=self.last_final_reason, **capacity)
            if capacity['remaining_tokens'] is not None and capacity['remaining_tokens'] < 0:
                raise ProviderError('context_length', 'Input plus reserved output exceeds configured context capacity; no history was removed')

        try:
            if self.session_budget is not None:
                self.session_budget.take_model(self.name, final=self.last_call_final, preflight=preflight)
            else:
                preflight(False)
        except ProviderError as error:
            if error.kind == "context_length" and self.session_budget:
                self.session_budget.record_limit("context_length", self.name)
            raise
        if self.last_call_final and self.session_budget:
            self.session_budget.record_limit(self.last_final_reason, self.name)
        schemas = self.schemas
        if self.last_call_final and self.submission_tool:
            # Do not assume forced named-tool support in a provider's thinking mode.
            schemas = [self.tools[self.submission_tool].schema]
            tool_choice = None
        input_length = len(self.messages)
        options = {}
        if self.response_format is not None:
            options["response_format"] = dict(self.response_format)
        if self.session_budget is not None and isinstance(self.client, ChatClient):
            options["timeout"] = min(self.client.cfg.timeout, max(0.001, self.session_budget.remaining_seconds()))
        attempt_id = self.trace.emit("llm_attempt", agent=self.name, usage_role=self.usage_role,
            context_len=input_length, model=self.client.cfg.model, tool_choice=tool_choice, effort=effort,
            response_format=self.response_format, available_tools=[s["function"]["name"] for s in schemas],
            final_reason=self.last_final_reason)
        self.model_calls += 1
        started = time.monotonic()
        activity = self.session_budget.activity("execution") if self.session_budget else nullcontext()
        try:
            with activity:
                completion = self.client.complete(self.messages, schemas or None, tool_choice, effort, **options)
        except Exception as error:
            self.trace.emit("llm_error", agent=self.name, usage_role=self.usage_role, attempt_id=attempt_id,
                model=self.client.cfg.model, error_kind=getattr(error, "kind", "client_exception"),
                status=getattr(error, "status", None), latency=time.monotonic()-started,
                usage=None, usage_available=False, error=str(error))
            if isinstance(error, ProviderError) and error.fatal and self.session_budget is not None:
                self.session_budget.stop(error)
            if isinstance(error, ProviderError) and error.kind == "context_length" and self.session_budget:
                self.session_budget.record_limit("context_length", self.name)
            raise
        self.last_prompt_tokens = completion.usage["prompt_tokens"]
        self.last_input_length = input_length
        self.trace.emit(
            "llm_call",
            agent=self.name,
            attempt_id=attempt_id,
            usage_available=bool(completion.raw_usage) or any(completion.usage.values()) or self.client.cfg.model == "scripted",
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

    def input_capacity(self):
        """Conservative incremental estimate, not a tokenizer or cumulative quota.

        Anchor an unchanged input prefix to its provider token receipt. Charge
        every UTF-8 byte of subsequently appended messages as a token, plus
        framing margin. Initial requests include all tool schemas. History and
        reasoning are never summarized, removed or silently clipped.
        """
        start = self.last_input_length if self.last_prompt_tokens > 0 else 0
        added = self.messages[start:]
        encoded = json.dumps(added, ensure_ascii=False).encode('utf-8')
        estimate = (self.last_prompt_tokens if start else 0) + len(encoded) + 128 * len(added)
        if not start:
            estimate += len(json.dumps(self.schemas, ensure_ascii=False).encode('utf-8'))
        cfg = self.client.cfg
        window = getattr(cfg, 'context_window', None)
        margin = getattr(cfg, 'context_margin', 8192)
        return dict(method='receipt-prefix-plus-utf8-v1', estimated_input_tokens=estimate,
                    context_window=window, reserved_output_tokens=cfg.max_tokens, margin_tokens=margin,
                    remaining_tokens=None if window is None else window - cfg.max_tokens - margin - estimate)

    def log_tool(self, call: dict, args, obs: Observation) -> Observation:
        if obs.meta.get("error") or obs.meta.get("budget_exhausted") or obs.meta.get("exit_code") not in (None, 0):
            kind = obs.meta.get("error_kind") or (
                "budget_exhausted" if obs.meta.get("budget_exhausted") else
                "execution_error" if obs.meta.get("error") else "command_exit")
            self.tool_events.append(dict(agent_id=self.name, tool=call["function"]["name"],
                                         call_id=call["id"], args=args, error_kind=kind,
                                         error=bool(obs.meta.get("error") or obs.meta.get("budget_exhausted")),
                                         report=obs.text, exit_code=obs.meta.get("exit_code")))
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
        with self._counter_lock:
            self.tool_calls += 1
        if self.session_budget is not None:
            self.session_budget.check()
        name = call["function"]["name"]
        tool = self.tools.get(name)
        try:
            args = parse_tool_arguments(call["function"].get("arguments"))
        except (ValueError, TypeError) as error:
            obs = Observation(f"Invalid JSON arguments: {error}",
                              {"error": True, "error_kind": "invalid_arguments", "budget_charged": False})
            return self.log_tool(call, None, obs)
        if tool is None:
            obs = Observation(f"Unknown tool: {name}", {"error": True, "error_kind": "permission_denied"})
        elif (error := next(Draft202012Validator(tool.parameters).iter_errors(args), None)) is not None:
            location = ".".join(str(part) for part in error.absolute_path) or "arguments"
            obs = Observation(f"Invalid {name} arguments at {location}: {error.message}. "
                              "Not executed; no domain budget consumed.",
                              {"error": True, "error_kind": "invalid_arguments", "budget_charged": False})
        elif self.tool_gate is not None and (denial := self.tool_gate(tool, args, self)) is not None:
            obs = denial
            obs.meta.setdefault("error", True)
            obs.meta.setdefault("error_kind", "permission_denied")
            obs.meta["budget_charged"] = False
        elif tool.preflight is not None and (denial := tool.preflight(args, self)) is not None:
            obs = denial
            obs.meta.setdefault('error', True)
            obs.meta.setdefault('error_kind', 'permission_denied')
            obs.meta['budget_charged'] = False
        else:
            if self.session_budget is not None:
                denial = self.session_budget.admit_tool(self.budget if tool.budgeted else None)
            else:
                denial = "agent_tool_limit" if tool.budgeted and not self.budget.take() else None
            if denial:
                if self.session_budget:
                    self.session_budget.record_limit(denial, self.name)
                self.budget_exhausted = True
                text = ("The shared session tool budget is exhausted for ALL contexts. Report existing evidence without further domain tools."
                        if denial == "session_tool_limit" else BUDGET_EXHAUSTED)
                return self.log_tool(call, args, Observation(text, {"budget_exhausted": True,
                                     "error_kind": "budget_exhausted", "budget_scope": denial, "budget_charged": False}))
            try:
                self.active_tool_call_id = call["id"]
                # Serial submission accounts for export I/O through its audit scopes.
                activity = self.session_budget.activity("execution") if self.session_budget and name != self.submission_tool else nullcontext()
                with activity:
                    obs = tool.run(args, self)
            except ProviderError as error:
                if error.fatal and self.session_budget is not None:
                    self.session_budget.stop(error)
                raise
            except SessionLimit:
                raise
            except ValueError as error:
                obs = Observation(f"Error executing {name}: {error}", {"error": True, "error_kind": "invalid_arguments"})
            except Exception as error:  # shown to the model like any tool error
                obs = Observation(f"Error executing {name}: {error}", {"error": True, "error_kind": "execution_error"})
            obs.meta["budget_charged"] = tool.budgeted
            if name == self.submission_tool and not obs.meta.get("error"):
                self.submission = obs.submission_text if obs.submission_text is not None else obs.text
        return self.log_tool(call, args, obs)

    def answer(self, calls: list[dict]) -> None:
        """Run internal tool calls and append their results in call order."""
        if len(calls) > 1 and any(c["function"]["name"] == self.submission_tool or
                                 (self.tools.get(c["function"]["name"]) and self.tools[c["function"]["name"]].sole)
                                 for c in calls):
            self.refuse(calls, "Submit/yielding control must be the only call in a reply; nothing in this batch was executed.")
            return
        # Serial tools are barriers; only contiguous explicitly concurrent tools overlap.
        start = 0
        while start < len(calls):
            end = start + 1
            tool = self.tools.get(calls[start]["function"]["name"])
            if tool is not None and tool.concurrent:
                while end < len(calls):
                    following = self.tools.get(calls[end]["function"]["name"])
                    if following is None or not following.concurrent:
                        break
                    end += 1
            group = calls[start:end]
            errors = []
            def execute(call):
                try:
                    return self.run_tool(call)
                except (SessionLimit, ProviderError) as error:
                    errors.append(error)
                    return self.log_tool(call, None, Observation(str(error),
                        {"error": True, "error_kind": getattr(error, "kind", str(error))}))
            if len(group) > 1:
                with ThreadPoolExecutor(min(len(group), self.max_concurrent_tools)) as pool:
                    results = list(pool.map(execute, group))
            else:
                results = [execute(group[0])]
            for call, obs in zip(group, results):
                self.append(tool_message(call, obs), obs.ref)
            if errors:
                self.refuse(calls[end:], "Not executed: session stopped during tool execution.")
                raise errors[0]
            start = end

    def refuse(self, calls: list[dict], text: str = NOT_EXECUTED) -> None:
        """Answer calls that must not run, keeping the history valid for later calls."""
        for call in calls:
            obs = self.log_tool(call, None, Observation(text, {"error": True, "error_kind": "action_refused"}))
            self.append(tool_message(call, obs), obs.ref)

    def notice(self, reason: str, final_prompt: str) -> dict:
        """A user-role message asking for a forced final reply, with its reason."""
        return {"role": "user", "content": " ".join(filter(None, (reason, final_prompt)))}

    def start(self, prompt: str | None, final_prompt: str, prompt_ref: int | None = None):
        """Start an invocation without resetting history or lifetime tools."""
        if prompt is not None:
            self.append({"role": "user", "content": prompt}, prompt_ref)
        self.final_prompt = final_prompt
        self.submission = None
        self.invocation_turns = 0
        self.last_text = ""

    def step(self, *, force_final=False, final_reason=None) -> Outcome | None:
        """One model response and all its tool results; None means continue."""
        turn = self.invocation_turns + 1
        final = force_final or turn >= self.max_turns
        if final:
            notice = self.notice("This is the last model call allowed for this invocation.", self.final_prompt)
            if self.messages[-1:] != [notice]:
                self.append(notice)
        try:
            completion = self.call(tool_choice="none" if final else None, final_reason=final_reason)
        except SessionLimit as error:
            return Outcome(self.last_text or "No final report was produced before the session stopped.", str(error), turn - 1)
        self.invocation_turns = turn
        calls = completion.message.get("tool_calls") or []
        text = self.last_text = completion.message.get("content") or ""
        if self.session_budget is not None:
            try:
                self.session_budget.check()
            except SessionLimit as error:
                self.refuse(calls, f"Not executed: {error}.")
                return Outcome(text or "Session stopped before a final report.", str(error), turn)
        if completion.finish_reason == "length":
            if self.session_budget:
                self.session_budget.record_limit("output_length_limit", self.name)
            self.refuse(calls, LENGTH_TRUNCATED)
            return Outcome(text, "length", turn)
        if not calls:
            if self.submission_tool:
                if self.last_call_final:
                    return Outcome(text, "submission_missing", turn)
                self.append(self.notice("No submission received. Continue working or call the submission tool.", self.final_prompt))
                return None
            return Outcome(text or "No final report was produced.", "done" if text.strip() else "empty_report", turn)
        if self.last_call_final and not (self.submission_tool and len(calls) == 1
                                         and calls[0]["function"]["name"] == self.submission_tool):
            self.refuse(calls, "Not executed: this last call was reserved for the final report.")
            return Outcome(text or "No final report was produced.", self.last_final_reason, turn)
        try:
            self.answer(calls)
        except SessionLimit as error:
            return Outcome(text or "No final report was produced before the session stopped.", str(error), turn)
        if self.submission is not None:
            return Outcome(self.submission, "done", turn)
        if self.last_call_final:
            return Outcome(text, "submission_invalid", turn)
        return None

    def run(self, prompt: str | None, final_prompt: str, prompt_ref: int | None = None) -> Outcome:
        self.start(prompt, final_prompt, prompt_ref)
        while True:
            outcome = self.step()
            if outcome is not None:
                return outcome
