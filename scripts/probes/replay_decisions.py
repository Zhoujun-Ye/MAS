"""Read-only parser/consistency replay; never executes code or selects using gold."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.evidence_mas.decision import extract_answers, answer_key
from harness.evidence_mas.measurements import extract_measurements
from benchmarks.kramabench.evaluation import numeric_success


def replay(summaries):
    counts = defaultdict(Counter)
    seen = set()
    input_hashes = []
    artifact_hashes = []
    for summary in summaries:
        raw = summary.read_bytes()
        input_hashes.append(hashlib.sha256(raw).hexdigest())
        for row in json.loads(raw)['rows']:
            folder = Path(row['run']) / row['task_id'] / row.get('runtime_backend', row['backend'])
            folder = folder.resolve()
            if folder in seen:
                continue
            seen.add(folder)
            bucket = counts[row['benchmark'] + '/' + row['backend'] + '@' + summary.parent.name]
            bucket['runs'] += 1
            events = folder / 'native-profile/observer/events.jsonl'
            report_path = folder / 'report.json'
            if not events.is_file() or not report_path.is_file():
                bucket['missing_artifacts'] += 1
                continue
            values = set()
            explicit, possible = defaultdict(set), defaultdict(set)
            raw_answers, raw_explicit, raw_possible, numeric_occurrences = [], [], [], []
            malformed = 0
            artifact_hashes.append(hashlib.sha256(events.read_bytes()).hexdigest())
            for line in events.open():
                try:
                    event = json.loads(line)
                    if event.get('hook_event_name') == 'PostToolUse' and event.get('tool_name') == 'Bash' and not event.get('truncated'):
                        values.update(answer_key(v) for v in extract_answers(event.get('tool_response')))
                        raw_answers.extend(extract_answers(event.get('tool_response')))
                        for measurement in extract_measurements(event.get('tool_response')):
                            if measurement['confidence']=='explicit' and measurement['answer_target']:
                                values.add(answer_key(measurement['value']))
                                raw_answers.append(measurement['value'])
                            groups = explicit if measurement['confidence']=='explicit' else possible
                            groups[measurement['group']].add(answer_key(measurement['value']))
                            (raw_explicit if measurement['confidence']=='explicit' else raw_possible).append(measurement['value'])
                        if row['benchmark']=='kramabench':
                            from harness.evidence_mas.measurements import payload
                            text = payload(event.get('tool_response'))
                            if isinstance(text,str):
                                numeric_occurrences.extend(m.group().replace(',','') for m in re.finditer(
                                    r'(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])', text))
                except (ValueError, TypeError):
                    malformed += 1
            report = json.loads(report_path.read_text())
            artifact_hashes.append(hashlib.sha256(report_path.read_bytes()).hexdigest())
            submission_path = folder / 'workspace/submission.json'
            if not submission_path.is_file():
                bucket['missing_submission'] += 1
                continue
            submission = json.loads(submission_path.read_text())
            artifact_hashes.append(hashlib.sha256(submission_path.read_bytes()).hexdigest())
            prediction = submission.get('answer', submission.get('final_answer'))
            correct = report.get('grade', {}).get('score')
            label = 'correct' if correct == 1 else 'incorrect' if correct == 0 else 'ungraded_or_partial'
            bucket[label + '_runs'] += 1
            bucket['malformed_events'] += malformed
            bucket['covered_runs'] += bool(values)
            bucket['conflict_runs'] += len(values) > 1
            bucket[label + '_conflicts'] += len(values) > 1
            bucket[label + '_submitted_value_absent'] += answer_key(prediction) not in values
            explicit_values = set().union(*explicit.values()) if explicit else set()
            possible_values = set().union(*possible.values()) if possible else set()
            explicit_conflict = any(len(v)>1 for v in explicit.values())
            advisory_conflict = any(len(v)>1 for v in possible.values())
            bucket['explicit_intermediate_runs'] += bool(explicit_values)
            bucket['possible_intermediate_runs'] += bool(possible_values)
            bucket[label+'_explicit_intermediate_conflicts'] += explicit_conflict
            bucket[label+'_advisory_conflicts'] += advisory_conflict
            # Gold is read only AFTER parser output is frozen, for evaluation counts only.
            grade = report.get('grade', {})
            if row['benchmark'] == 'kramabench' and 'target' in grade:
                bucket[label + '_gold_covered'] += answer_key(grade['target']) in values
                gold = answer_key(grade['target'])
                bucket[label+'_gold_in_explicit_intermediate'] += gold in explicit_values
                bucket[label+'_gold_in_possible_intermediate'] += gold in possible_values
                bucket[label+'_gold_new_intermediate_only'] += gold not in values and gold in explicit_values | possible_values
                policy = grade.get('scoring_contract',{}).get('numeric_success_policy',{}).get('name')
                if grade.get('answer_type','').startswith('numeric') and policy:
                    def matches(items):
                        return any(numeric_success(v,grade['target'],numeric_policy=policy) for v in items)
                    final_hit, explicit_hit, possible_hit = matches(raw_answers), matches(raw_explicit), matches(raw_possible)
                    bucket[label+'_numeric_evaluable_runs'] += 1
                    bucket[label+'_gold_final_official_tolerance'] += final_hit
                    bucket[label+'_gold_explicit_official_tolerance'] += explicit_hit
                    bucket[label+'_gold_possible_official_tolerance'] += possible_hit
                    bucket[label+'_gold_intermediate_only_official_tolerance'] += (not final_hit and (explicit_hit or possible_hit))
                    bucket[label+'_gold_numeric_occurrence_upper_bound'] += matches(numeric_occurrences)
            bucket['uncovered_runs'] += not bool(values)
    return dict(aggregates={k: dict(v) for k, v in sorted(counts.items())}, input_summary_sha256=input_hashes,
                input_artifacts_sha256=hashlib.sha256(json.dumps(artifact_hashes).encode()).hexdigest(),
                implementation_sha256={Path(m.__file__).name:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
                    for m in (sys.modules[extract_answers.__module__], sys.modules[extract_measurements.__module__])},
                grouping_false_positive_rate=None,
                grouping_false_positive_status='Unknown: historical logs have no independently annotated same-estimand pairs. Correct-run alerts measure review load, not grouping errors.',
                numeric_coverage_policy='Recorded benchmark tolerance used only after extraction. Broad numeric occurrence is a diagnostic upper bound, not a candidate or verified computation.',
                paid_calls=0, tools_executed=False, original_artifacts_modified=False,
                interpretation='Conflicts are review triggers, not wrong answers. No historical decision receipts exist; '
                'this measures extraction and potential review load, not corrected accuracy or actual gate false-positive rate.',
                matcher='All declared final answers compete across targets; other explicit intermediates retain six-dimension groups. Labeled numeric/JSON-path hints are detail-only. No gold-assisted grouping, fuzzy merging or unit conversion.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='planned', paid_calls=0)))
        return
    output = args.output.resolve()
    if any(output.is_relative_to(p.resolve().parent) for p in args.summary):
        raise ValueError('Output must not overlap original runs')
    result = replay(args.summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
