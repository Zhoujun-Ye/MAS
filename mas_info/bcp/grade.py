"""Answer grading with the official BrowseComp-Plus judge prompt and parsing rules.

The judge model is configurable; the official evaluation used gpt-4.1 or
Qwen3-32B. Unparseable judgements stay ungraded, never counted as wrong.
"""

from __future__ import annotations

import re

from ..llm import ChatClient

# Verbatim from BrowseComp-Plus search_agent/prompts.py (including its "\%").
GRADER_TEMPLATE = """
Judge whether the following [response] to [question] is correct or not based on the precise and unambiguous [correct_answer] below.

[question]: {question}

[response]: {response}

Your judgement must be in the format and criteria specified below:

extracted_final_answer: The final exact answer extracted from the [response]. Put the extracted answer as 'None' if there is no exact, final answer to extract from the response.

[correct_answer]: {correct_answer}

reasoning: Explain why the extracted_final_answer is correct or incorrect based on [correct_answer], focusing only on if there are meaningful differences between [correct_answer] and the extracted_final_answer. Do not comment on any background to the problem, do not attempt to solve the problem, do not argue for any answer different than [correct_answer], focus only on whether the answers match.

correct: Answer 'yes' if extracted_final_answer matches the [correct_answer] given above, or is within a small margin of error for numerical problems. Answer 'no' otherwise, i.e. if there if there is any inconsistency, ambiguity, non-equivalency, or if the extracted answer is incorrect.


confidence: The extracted confidence score between 0|\\%| and 100|\\%| from [response]. Put 100 if there is no confidence score available.
""".strip()


def _field(name: str, pattern: str, text: str) -> re.Match | None:
    """Official precedence: **name:**, then **name**:, then name:."""
    for prefix in (rf"\*\*{name}:\*\*", rf"\*\*{name}\*\*:", rf"{name}:"):
        match = re.search(prefix + pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match
    return None


def parse_judgement(text: str) -> dict:
    """Same fields and fallbacks as the official ``parse_judge_response``."""
    result = {"extracted_final_answer": None, "correct": None, "confidence": None, "parse_error": False}
    if not text:
        result["parse_error"] = True
        return result
    answer = _field("extracted_final_answer", r"\s*(.*?)(?=\n|$)", text)
    if answer:
        result["extracted_final_answer"] = answer.group(1).strip()
    correct = _field("correct", r"\s*(yes|no)", text)
    if correct:
        result["correct"] = correct.group(1).lower() == "yes"
    confidence = _field("confidence", r"\s*(\d+(?:\.\d+)?)\s*%?", text)
    if confidence:
        result["confidence"] = min(100.0, float(confidence.group(1)))
    result["parse_error"] = result["correct"] is None
    return result


def grade(client: ChatClient, question: str, response: str, correct_answer: str) -> dict:
    prompt = GRADER_TEMPLATE.format(question=question, response=response, correct_answer=correct_answer)
    completion = client.complete([{"role": "user", "content": prompt}])
    judgement = completion.message.get("content") or ""
    return {
        **parse_judgement(judgement),
        "judge_model": client.cfg.model,
        "judgement": judgement,
        "usage": completion.usage,
    }
