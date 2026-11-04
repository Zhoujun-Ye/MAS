"""Host-side evaluation schemas and scoring contracts; never solver input."""

import math

def evaluation_rows(tasks, predicted):
    return [dict(task_id=t.id, task_prompt=t.question, response=predicted[t.id]["final_answer"],
                 answer=t.reference["answer"], guidelines=t.reference["guidelines"],
                 steps=t.reference.get("steps"), steps_num=t.reference.get("steps_num"),
                 milestone=t.reference.get("milestone"), source_sha256=t.source_sha256,
                 process_metrics_status="requires_native_trajectory_mapping_and_separate_judge_authorization")
            for t in tasks]


def outcome_rubric(answer):
    if isinstance(answer, list):
        if not answer:
            raise ValueError("Empty gold lists have no defined upstream average")
        return dict(parts=len(answer), keys=[f"part_{i}" for i in range(len(answer))],
                    rule="semantic equivalence per corresponding part; mean of binary parts; missing/unparseable parts all zero")
    return dict(parts=1, keys=["match"], rule="binary semantic equivalence")


def validate_verdict(answer, verdict):
    rubric = outcome_rubric(answer)
    scores = verdict.get("scores", {})
    if set(scores) != set(rubric["keys"]) or any(type(v) not in (int, float) or v not in (0, 1) for v in scores.values()):
        raise ValueError("Expected upstream binary per-part scores")
    score = sum(scores.values()) / rubric["parts"]
    if (type(verdict.get("total")) not in (int, float) or not math.isfinite(verdict["total"])
            or abs(verdict["total"] - score) > 1e-12):
        raise ValueError("Judge total must equal the mean of binary parts")
    return score
