"""Single-context control using the common Agent loop and session accounting."""

from .agent import Agent, Budget, Outcome
from .session import Session


class SingleAgent(Session):
    def __init__(self, client, trace, tools=(), *, domain_tools=None, project_context="",
                 leader_system=None, max_turns=None, tool_budget=None, leader_response_format=None,
                 leader_final_prompt=None, submission_tool=None, **kwargs):
        for key in ("max_workers", "max_activations", "max_parallel", "message_limit", "message_bytes", "workspace_root"):
            kwargs.pop(key, None)
        if kwargs.pop("leader_mode", "full") != "full":
            raise ValueError("leader_mode only selects a Team arm, not Single")
        super().__init__(client, trace, tools, **kwargs)
        grants = tuple(self.tools if domain_tools is None else domain_tools)
        if not set(grants) <= self.tools.keys():
            raise ValueError("Unregistered tool grant")
        calls, actions = self.session_budget.model_limit, self.session_budget.tool_limit
        if (max_turns is not None and max_turns < calls) or (tool_budget is not None and tool_budget < actions):
            raise ValueError("Single root must be allowed the full shared budget")
        if submission_tool and (submission_tool.name in self.tools or submission_tool.budgeted or submission_tool.concurrent):
            raise ValueError("Submission must be a distinct unbudgeted serial tool")
        self.mode, self.context_mode = "single", "full_task_and_own_history"
        self.max_workers = self.max_activations = self.max_parallel = 0
        self.leader_final_prompt = leader_final_prompt or "Return the answer with evidence and unfinished work."
        self.leader = Agent("leader", client, trace,
            (leader_system or "Solve the task using authorized tools.") + "\n" + project_context,
            tools=[self.tools[n] for n in grants] + ([submission_tool] if submission_tool else []),
            budget=Budget(tool_budget if tool_budget is not None else actions),
            max_turns=max_turns or calls, usage_role="single", session_budget=self.session_budget,
            response_format=leader_response_format, submission_tool=submission_tool.name if submission_tool else None)

    def run(self, task):
        if self.started:
            raise ValueError("A session can only be run once")
        self.started = True
        self.session_budget.start()
        self.trace.emit("session_config", mode=self.mode, context_mode=self.context_mode,
                        budget=self.session_budget.snapshot(), fork=False)
        self.audit("before")
        error = None
        try:
            outcome = self.leader.run(task, self.leader_final_prompt)
        except Exception as caught:
            error = caught
            kind = getattr(caught, "kind", "execution_error")
            self.infra_affected |= kind != "context_length"
            self.errors.append(dict(agent_id="leader", error_kind=kind, report=str(caught)))
            outcome = Outcome("", kind, self.leader.model_calls)
        finally:
            self.session_budget.release_report("leader")
            self.audit("after")
        result = self.result(outcome)
        if error:
            error.session_outcome = result
            raise error
        return result
