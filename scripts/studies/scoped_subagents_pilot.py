"""Select an outcome-blind 24-task pilot and compare retained paired results."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._io import write_json

SEED = "scoped-evidence-judge-v1|20261103"


def select_tasks(tasks):
    strata = defaultdict(list)
    for task in tasks:
        domain, difficulty, _ = task["id"].split("-")
        strata[(domain, difficulty)].append(task["id"])
    if len(strata) != 12 or any(len(ids) < 2 for ids in strata.values()):
        raise ValueError("Expected six domains with easy and hard strata")
    return [task_id for key in sorted(strata) for task_id in sorted(
        strata[key], key=lambda x: hashlib.sha256((SEED + "|" + x).encode()).hexdigest())[:2]]


def select(baseline, output):
    if output.exists():
        raise ValueError("Selection output already exists")
    raw = baseline.read_bytes()
    data = json.loads(raw)
    ids = select_tasks(data["plan"]["tasks"])
    # Outcomes never enter task selection. Grade metadata is used only to cap judges.
    rows = {r["task_id"]: r for r in data["rows"]}
    judge_limit = sum(rows[i]["grade"]["answer_type"] == "string_approximate" for i in ids)
    manifest = dict(seed=SEED, rule="SHA256(seed|task_id), lowest two per domain/difficulty",
        task_ids=ids, attempts=24, retries=0, judge_limit=judge_limit,
        baseline_path=str(baseline.resolve()), baseline_sha256=hashlib.sha256(raw).hexdigest(),
        selection_uses_outcomes=False, scope="Balanced pilot, not a population accuracy estimate",
        strata=[dict(domain=d, difficulty=k, selected=2, available=sum(
            t["id"].startswith(d + "-" + k + "-") for t in data["plan"]["tasks"]))
            for d, k in sorted({tuple(i.split("-")[:2]) for i in ids})])
    write_json(output, manifest)
    return manifest


def effective(row):
    return row.get("effective_grade", row.get("grade", {}))


def metrics(rows):
    grades = [effective(r) for r in rows]
    binary = [g for g in grades if g.get("score_kind") == "binary"]
    grouped = defaultdict(list)
    for g in grades:
        if g.get("score") is not None:
            grouped[(g["answer_type"], g["metric"])].append(g["score"])
    seconds = [r["cli"]["elapsed_seconds"] for r in rows if r.get("cli", {}).get("elapsed_seconds") is not None]
    roles = defaultdict(lambda: Counter())
    for row in rows:
        for role, usage in row.get("accounting", {}).get("by_role", {}).items():
            roles[role].update({k: usage[k] for k in ("input_tokens", "output_tokens", "cache_hit_tokens")})
    for usage in roles.values():
        usage["cache_hit_rate"] = usage["cache_hit_tokens"] / usage["input_tokens"] if usage["input_tokens"] else None
    estimates = [r.get("accounting", {}).get("estimated_usd_off_peak") for r in rows]
    return dict(attempts=len(rows), statuses=dict(Counter(r["status"] for r in rows)),
        binary_n=len(binary), binary_graded=sum(g.get("score") is not None for g in binary),
        binary_correct=sum(g.get("score") == 1 for g in binary),
        mean_cli_seconds=statistics.mean(seconds) if seconds else None,
        median_cli_seconds=statistics.median(seconds) if seconds else None,
        timing_coverage=len(seconds), accounting_coverage=sum("accounting" in r for r in rows),
        roles=dict(roles), estimate_usd_offpeak=sum(estimates) if all(v is not None for v in estimates) else None,
        replay_pass=sum(r.get("pipeline_answer_matches_submission") is True and r.get("pipeline_exit_code") == 0 for r in rows),
        metric_groups=[dict(answer_type=a, metric=m, n=len(v), mean=statistics.mean(v))
                       for (a, m), v in sorted(grouped.items())])


def report(selection, new_root, output):
    if output.exists():
        raise ValueError("Report output already exists")
    manifest = json.loads(selection.read_text())
    baseline_path = Path(manifest["baseline_path"])
    raw = baseline_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["baseline_sha256"]:
        raise ValueError("Frozen historical baseline changed")
    baseline = json.loads(raw)
    new_raw = (new_root / "summary.json").read_bytes()
    new = json.loads(new_raw)
    if {r["task_id"] for r in new["rows"]} != set(manifest["task_ids"]) or len(new["rows"]) != 24:
        raise ValueError("Expected all 24 attempts; do not drop failures")
    for field in ("scoring", "instructions", "inputs_sha256", "image_id", "model", "effort",
                  "concurrency", "timeout_seconds", "cpu_per_attempt", "memory_per_attempt",
                  "backend_options", "native_environment", "cli_binaries"):
        if baseline["plan"][field] != new["plan"][field]:
            raise ValueError("Unmatched setting: " + field)
    old_by_id = {r["task_id"]: r for r in baseline["rows"]}
    old_rows = [old_by_id[i] for i in manifest["task_ids"]]
    for root, rows in ((baseline_path.parent, old_rows), (new_root, new["rows"])):
        for row in rows:
            path = root / row["task_id"] / row["backend"] / "submission.json"
            expected = effective(row).get("submission_file_sha256")
            if expected is not None and (path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                raise ValueError("Submission hash mismatch: " + str(path))
    pairs = []
    for row in new["rows"]:
        old = old_by_id[row["task_id"]]
        pairs.append(dict(task_id=row["task_id"], answer_type=effective(old).get("answer_type"),
            score_kind=effective(old).get("score_kind"), old_score=effective(old).get("score"),
            new_score=effective(row).get("score"), old_answer=old.get("submission", {}).get("answer"),
            new_answer=row.get("submission", {}).get("answer"),
            old_seconds=old.get("cli", {}).get("elapsed_seconds"),
            new_seconds=row.get("cli", {}).get("elapsed_seconds")))
    result = dict(selection=manifest, old=metrics(old_rows), new=metrics(new["rows"]), pairs=pairs,
        new_summary_sha256=hashlib.sha256(new_raw).hexdigest(), new_billing=new.get("billing"),
        judge_calls=new.get("paid_judge_calls"),
        binary_transitions=dict(Counter(f"{p['old_score']}->{p['new_score']}" for p in pairs if p["score_kind"] == "binary")),
        faster=sum(p["new_seconds"] < p["old_seconds"] for p in pairs if p["new_seconds"] is not None and p["old_seconds"] is not None),
        limitation="Historical paired pilot, not randomized concurrent control. Joint prompt intervention; no isolated causal attribution. Missing usage is unknown. Cost estimates are not invoices.")
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    choice = sub.add_parser("select")
    choice.add_argument("--baseline", type=Path, required=True)
    choice.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("report")
    compare.add_argument("--selection", type=Path, required=True)
    compare.add_argument("--new-run", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = select(args.baseline, args.output) if args.action == "select" else report(args.selection, args.new_run, args.output)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
