"""Versioned study prompts, separate from CLI transport and benchmark questions."""

from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1] / "docs/prompts/subagents-evidence-judge-v1.md"


def evidence_judge(*, web=False, data_path="/data", pipeline=True):
    text = PROMPT.read_text(encoding="utf-8")
    restriction = (f"Use only {data_path} and targeted web search/fetch when permitted by the task; no installations."
                   if web else f"Use only {data_path}, no network or installations.")
    text = text.replace("Use only /data, no network or installations.", restriction)
    if not pipeline:
        text = text.replace("final runnable pipeline", "final answer and supporting computations")
        text = text.replace("run the final pipeline, and write the required submission",
                            "check the final answer, and write the required submission")
        text = text.replace("use the common incomplete-submission convention", "report the missing input explicitly")
    return text
