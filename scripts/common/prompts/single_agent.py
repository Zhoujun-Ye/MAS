"""Strict Single Agent condition prompt; native policy enforces delegation denial."""

PROMPT = ("This is the strict SINGLE-AGENT condition. Complete all work yourself. Native delegation "
          "is disabled by policy. Do not call task, spawn any subagent, or launch other model/agent "
          "processes through shell, Python, HTTP, or any other route. No external model calls.")
