#!/usr/bin/env python3
"""Build information-level review packets without any judge/model call."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.information import decision_case
from harness.trace import read_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.report_dir.resolve().is_relative_to(args.output.resolve()):
        parser.error("Review packets must be separate from the immutable experiment")
    args.report_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    for path in sorted((args.output / "results").glob("*.json")):
        result = json.loads(path.read_text())
        trace = args.output / "traces" / f"{result['run_id']}.jsonl"
        if not trace.exists():
            rows.append(dict(run_id=result["run_id"], review_status="trace_unavailable"))
            continue
        events = read_trace(trace)
        try:
            case = decision_case(events)
        except ValueError:
            rows.append(dict(run_id=result["run_id"], review_status="no_decision_call"))
            continue
        case.update(run_id=result["run_id"], run_status=result["status"],
                    decision_kind="final" if any(e["type"] == "final" for e in events) else "last_observed_call",
                    task_grade=result.get("grade"), final_answer=result.get("final"),
                    run_incomplete_reason=result.get("reason"))
        (args.report_dir / path.name).write_text(json.dumps(case, ensure_ascii=False, indent=2))
        rows.append(dict(run_id=result["run_id"], run_status=result["status"],
                         primary_observations=len(case["primary_evidence"]),
                         messages_queued=len(case["transport"]),
                         messages_in_model_inputs=sum(e["model_input_t"] is not None for e in case["transport"]),
                         evidence_read_receipts=sum(bool(e["returned_evidence_ids"]) and e["model_input_t"] is not None for e in case["reads"]),
                         semantic_attribution="unknown", causal_attribution="not_tested"))
    (args.report_dir / "index.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
