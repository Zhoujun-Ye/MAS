"""Grade one retained attempt; callers own authorization and process lifetime."""

import sys

from benchmarks._external import jsonl
from common.io import read_json
from benchmarks.kramabench.semantic_judge import judge_once


def grade_attempt(benchmark, task, backend, run, *, data_root, grades_root,
                  credentials, judge_enabled, key, command_run, log):
    target = grades_root / benchmark / task.id / backend
    result = dict(benchmark=benchmark, task_id=task.id, backend=backend, judge_calls=0)
    if benchmark == "kramabench":
        summary = run / "summary.json"
        if not summary.exists():
            return {**result, "status": "missing_summary"}
        record = read_json(summary)["rows"][0]
        result.update(status=record.get("grade", {}).get("status"), grade=record.get("grade"),
                      pipeline_exit_code=record.get("pipeline_exit_code"),
                      pipeline_answer_matches_submission=record.get("pipeline_answer_matches_submission"))
        # Lifecycle evidence and answer eligibility are separate. judge_once
        # validates the retained submission before any authorized dispatch.
        if record.get("status") in {"cli_exited","native_condition_unverified"} and result["status"] == "pending_judge" and judge_enabled:
            judged = judge_once(upstream=data_root / benchmark / "upstream", task_id=task.id, backend=backend,
                submission_path=run / task.id / backend / "submission.json", question=task.query,
                key=key, output=target)
            result.update(status=judged["status"], grade=judged.get("grade"), judge_calls=judged["attempted_calls"])
            if judged.get('fatal'):
                result['fatal_provider_error'] = True
        if 'decision_gate' in record:
            raw = (result.get('grade') or {}).get('score')
            accepted = record['decision_gate']['accepted']
            result['accuracy'] = dict(raw_score=raw, compliant_score=raw if accepted else 0,
                                      protocol_accepted=accepted, grading_calls_shared=True)
        return result
    predictions = run / "predictions.jsonl"
    if not predictions.exists():
        return {**result, "status": "missing_predictions"}
    predicted = jsonl(predictions)
    text_judge = benchmark == "dataclawbench" or task.category != "search_to_sql"
    calls = sum(bool(p["final_answer"].strip()) for p in predicted) if text_judge and judge_enabled else 0
    command = [sys.executable, "-m", "scripts." + benchmark + ".score", "--run", str(run),
               "--upstream", str(data_root / benchmark / "upstream"), "--output", str(target)]
    if benchmark == "hybriddeepresearch":
        command += ["--tasks", str(data_root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"),
                    "--db-root", str(data_root / "hybriddeepresearch/data")]
        if not text_judge:
            command.append("--execute-sql")
    if calls:
        command += ["--execute-judges", "--judge-limit", str(calls), "--judge-model", "deepseek-flash",
                    "--credentials", str(credentials), "--judge-base-url", "https://api.deepseek.com"]
    code = command_run(command, log)
    receipt = read_json(target / "receipt.json", {})
    return {**result, "status": "completed" if code == 0 else "grading_failed", "returncode": code,
            "judge_calls": receipt.get("judge_calls"), "output": str(target),
            "fatal_provider_error": bool(receipt.get('fatal_provider_error'))}
