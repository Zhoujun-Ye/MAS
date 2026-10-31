#!/usr/bin/env python3
"""Write an immutable, explicitly revised scoreboard without overwriting grades."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import load_submitted_patches


def receipt(path):
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def read_run(folder, grade_path):
    manifest = json.loads((folder / 'manifest.json').read_text())
    result = json.loads((folder / 'result.json').read_text())
    grade = json.loads(grade_path.read_text())
    load_submitted_patches(folder, manifest, result)
    if grade['evaluation_snapshots'] != result['evaluation_snapshots'] or grade['status'] != 'graded':
        raise ValueError('Grade must be bound to the exact submitted artifacts')
    return manifest, result, grade


def build_report(originals, replacements):
    rows = {}
    identities = set()
    for batch in originals:
        for folder in batch.iterdir():
            if not folder.is_dir() or not folder.name.isdigit():
                continue
            index = int(folder.name)
            if index in rows:
                raise ValueError('Overlapping original indices')
            manifest, result, grade = read_run(folder, folder / 'grade.json')
            identity = json.dumps(manifest['pair'], sort_keys=True)
            if identity in identities:
                raise ValueError('Duplicate original pair')
            identities.add(identity)
            rows[index] = dict(index=index, pair=manifest['pair'],
                original_correct=grade['correct'], effective_correct=grade['correct'],
                original_grade=receipt(folder / 'grade.json'), effective_grade=receipt(folder / 'grade.json'),
                protocol_completed=result['status'] == 'completed',
                profile=manifest.get('benchmark_inputs', {}).get('profile', 'official'))
    if set(rows) != set(range(100)):
        raise ValueError('Require all 100 unique original pairs')
    changed = set()
    for index, folder, path in replacements:
        index, folder, path = int(index), Path(folder), Path(path)
        if index in changed or index not in rows:
            raise ValueError('Invalid or duplicate replacement')
        manifest, result, grade = read_run(folder, path)
        if manifest['pair'] != rows[index]['pair']:
            raise ValueError('Replacement must be the same pair')
        rows[index].update(effective_correct=grade['correct'], effective_grade=receipt(path),
            protocol_completed=result['status'] == 'completed',
            profile=manifest.get('benchmark_inputs', {}).get('profile', 'official'))
        changed.add(index)
    passed = sum(r['effective_correct'] is True for r in rows.values())
    return dict(label='user-authorized-revised-mixed-profile-scoreboard',
        passed=passed, failed=len(rows) - passed,
        original_passed=sum(r['original_correct'] is True for r in rows.values()),
        effective_passed=passed,
        total=len(rows), protocol_completed=sum(r['protocol_completed'] for r in rows.values()),
        replaced_indices=sorted(changed), rows=[rows[i] for i in sorted(rows)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, action='append', required=True)
    parser.add_argument('--replacement', nargs=3, action='append', default=[], metavar=('INDEX', 'RUN', 'GRADE'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.original, args.replacement)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        json.dump(report, output, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
