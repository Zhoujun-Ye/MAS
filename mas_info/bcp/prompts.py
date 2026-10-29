"""Frozen BrowseComp-Plus prompts (guide §3.4).

Every agent of every condition shares BASE. Role and relay texts were fixed
before any run and must not be tuned per condition; changing any text here
changes the frozen digest, so an existing output directory refuses it.
"""

from __future__ import annotations

from ..relay import CONDITIONS, STRUCTURED_SCHEMA

BASE = """You are part of a deep-research system that answers a question by searching a fixed corpus of about 100,000 web documents. The corpus is reachable only through two tools:
- search(query): returns the top {k} documents for the query, each with docid, score and a snippet of at most {snippet_tokens} tokens.
- get_document(docid): returns the full text of one document.
All search and get_document calls made for the question, by anyone working on it, come from one shared budget of {budget} calls. When the budget is used up, these tools stop returning documents.
Reason step by step and interleave your reasoning with tool calls. Refer to documents by their docid in square brackets, e.g. [20]."""

# Official BrowseComp-Plus response format.
ANSWER_FORMAT = """Your final response should be in the following format:
Explanation: {your explanation for your final answer. For this explanation section only, you should cite your evidence documents inline by enclosing their docids in square brackets [] at the end of sentences. For example, [20].}
Exact Answer: {your succinct, final answer}
Confidence: {your confidence score between 0% and 100% for your answer}"""

SINGLE = "You work alone: search the corpus yourself with search and get_document, then write the final response."

SEQUENTIAL = (
    "You work alone, searching the corpus yourself with search and get_document. The question "
    "has been split into sub-tasks that you will receive one at a time. Complete each sub-task "
    "and summarize what you found; write the final response only when asked."
)

LEAD = """You are the lead researcher. You cannot call search or get_document yourself. Plan the research, give focused tasks to search agents with dispatch, and combine what they report into the final response.
- Up to {workers} search agents are available. dispatch(task) starts a new search agent; dispatch(task, agent="search_2") gives another task to an existing search agent, which keeps its earlier context.
- Several dispatch calls in one reply run in parallel."""

WORKER = (
    "You are a search agent working for a lead researcher on one part of the question. "
    "Complete the assigned task with search and get_document."
)

LEAD_RELAY = {
    "free_text": "A search agent sees only your task message. Each dispatch returns the search agent's free-text report.",
    "structured": "A search agent sees only your task message. Each dispatch returns the search agent's report as a JSON object with the fields conclusion, key_facts, ruled_out, open_questions and confidence.",
    "full": "A search agent sees the original question, your working notes so far and your task message. Each dispatch returns the search agent's report followed by the complete log of its tool calls and their outputs.",
    "reference": "A search agent sees only your task message. Its tool outputs and notes are saved to shared storage as artifacts. Each dispatch returns a short summary report and an index of that agent's artifacts; open any artifact with read_artifact.",
}

WORKER_RELAY = {
    "free_text": "When you are done, reply with a report for the lead researcher. The lead sees only this report.",
    "structured": "When you are done, reply with only a JSON object of the following form. The lead sees only this JSON.\n" + STRUCTURED_SCHEMA,
    "full": "When you are done, reply with a report for the lead researcher. The lead also receives the complete log of your tool calls and their outputs.",
    "reference": "Each tool output you receive is saved to shared storage as an artifact whose id is on its first line, e.g. [artifact a7]. You can save notes with write_artifact and open any artifact with read_artifact. When you are done, reply with a short summary report that cites artifact ids. The lead sees this summary and an index of your artifacts, and can open them on demand.",
}

QUESTION = "Question: {question}"
SUBTASK_FIRST = "Question: {question}\n\nSub-task 1 of {n}:\n{task}"
SUBTASK = "Sub-task {i} of {n}:\n{task}"
SUBTASKS_DONE = "All sub-tasks are done. Write the final response to the question now."
FINAL_ANSWER = "You have reached the turn limit. Write your final response now in the required format, without calling tools."
FINAL_REPORT = "You have reached the turn limit. Write your report now, without calling tools."


def system_prompt(role: str, relay: str | None, settings: dict) -> str:
    base = BASE.format(
        k=settings["k"], snippet_tokens=settings["snippet_max_tokens"], budget=settings["tool_calls"]
    )
    if role == "single":
        parts = [base, SINGLE, ANSWER_FORMAT]
    elif role == "sequential":
        parts = [base, SEQUENTIAL, ANSWER_FORMAT]
    elif role == "lead":
        parts = [base, LEAD.format(workers=settings["max_workers"]), LEAD_RELAY[relay], ANSWER_FORMAT]
    elif role == "worker":
        parts = [base, WORKER, WORKER_RELAY[relay]]
    else:
        raise ValueError(f"Unknown role: {role}")
    return "\n\n".join(parts)


def frozen_prompts(settings: dict) -> dict:
    """System prompt of every role in every condition, for the manifest (guide §3.4)."""
    prompts = {}
    for condition, (structure, relay) in CONDITIONS.items():
        roles = {"single": ["single"], "sequential": ["sequential"], "team": ["lead", "worker"]}
        prompts[condition] = {role: system_prompt(role, relay, settings) for role in roles[structure]}
    return prompts
