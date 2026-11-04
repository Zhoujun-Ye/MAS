"""Keep the selected current results; relocate older output namespaces reversibly."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._io import write_json


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_backend(value):
    return 'claude-code-agent-team' if value == 'claude-code' else value


def relocated(value, mapping):
    for old, new in mapping.items():
        if value == old or value.startswith(old+'/'):
            return new+value[len(old):]
    return value


def retain(root, publication, archive, *, execute=False, reports_only=False, expected_tasks=104):
    root, publication, archive = (Path(p).resolve() for p in (root, publication, archive))
    current = root/'current'
    if current.exists() or archive.exists():
        raise FileExistsError('Current/archive destination already exists')
    if archive.is_relative_to(root) or root.is_relative_to(archive):
        raise ValueError('Archive and output roots must not overlap')
    source = publication/'summary.json'
    result = json.loads(source.read_text())
    rows = result['rows']
    identities = {(r['task_id'], canonical_backend(r['backend'])) for r in rows}
    if len(identities) != 2*expected_tasks or len(rows) != len(identities):
        raise ValueError('Expected exactly two matched current cohorts')
    for backend in ('deepagents', 'claude-code-agent-team'):
        if len({t for t,b in identities if b == backend}) != expected_tasks:
            raise ValueError('Current cohort is incomplete')
    children = sorted(root.iterdir())
    mapping = {str(p): str(archive/p.name) for p in children}
    plan = dict(selected_attempts=len(rows), reports_only=reports_only, output=str(current),
                source_publication_sha256=sha(source), archive_map=mapping, permanently_deleted=0)
    if not execute:
        return dict(plan, status='planned')
    stage = root/('.current-preparing-'+uuid.uuid4().hex[:10])
    stage.mkdir(mode=0o700)
    archive.mkdir(parents=True, mode=0o700, exist_ok=False)
    derived = copy.deepcopy(result)
    copied = []
    for row in derived['rows']:
        task, backend = row['task_id'], canonical_backend(row['backend'])
        if '/' in task or task in {'', '.', '..'}:
            raise ValueError('Unsafe task ID')
        old_backend = row.get('source_backend', row['backend'])
        origin = Path(row['source_run'])/task/old_backend
        if not reports_only:
            if origin.is_symlink() or not origin.resolve().is_relative_to(root):
                raise ValueError('Selected raw evidence must be inside this output root')
            target = stage/'evidence'/task/backend
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(origin, target, symlinks=True)
            artifact = target/'submission.json'
            if artifact.is_symlink() or sha(artifact) != row['grade']['submission_file_sha256']:
                raise ValueError('Copied artifact hash mismatch')
            if sha(origin/'report.json') != sha(target/'report.json'):
                raise ValueError('Copied native report hash mismatch')
            old_root = Path(row['source_run'])
            new_root = archive/old_root.relative_to(root)
            row['origin'] = dict(original_execution_root=str(old_root), archived_run=str(new_root),
                                 original_backend=old_backend, native_report_sha256=sha(target/'report.json'))
            row['source_run'] = str(current/'evidence')
            row['source_backend'] = backend
            copied.append(dict(task_id=task, backend=backend, submission_sha256=sha(artifact)))
        else:
            row['source_run'] = relocated(row['source_run'], mapping)
            row['source_backend'] = old_backend
        row['backend'] = backend
    # Relink provenance pointers in this derived publication, never in frozen logs.
    for value in derived.get('source_audits', {}).values():
        path = str(value.get('path', ''))
        value['original_path'] = value.get('original_path', path)
        value['path'] = relocated(path, mapping)
    for row in derived['rows']:
        if row.get('replacement'):
            previous = row['replacement']['previous_source_run']
            row['replacement']['previous_source_run'] = relocated(previous, mapping)
    for row in derived.get('linked_single_diagnostics', []):
        row['source_run'] = relocated(row['source_run'], mapping)
    derived['retention'] = dict(source_publication_sha256=plan['source_publication_sha256'],
                                reports_only=reports_only, archive_map=mapping)
    write_json(stage/'comparison/summary.json', derived)
    for name, backend in (('single','deepagents'), ('team','claude-code-agent-team')):
        subset = [r for r in derived['rows'] if r['backend'] == backend]
        write_json(stage/'comparison'/name/'summary.json', dict(cohort=name,
            statistics=derived['cohorts'][name], rows=subset))
    if (publication/'REPORT.md').exists():
        shutil.copy2(publication/'REPORT.md', stage/'comparison/REPORT.md')
    if (publication/'replacements.json').exists():
        replacements = json.loads((publication/'replacements.json').read_text())
        for row in replacements:
            row['previous_source_run'] = relocated(row['previous_source_run'], mapping)
            row['archived_new_source_run'] = relocated(row['new_source_run'], mapping)
            row['new_source_run'] = str(current/'evidence') if not reports_only else relocated(row['new_source_run'], mapping)
        write_json(stage/'comparison/replacements.json', replacements)
    plan.update(status='retained', copied_evidence=len(copied), selected_artifacts=copied,
                relocator_sha256=sha(Path(__file__)))
    write_json(archive/'relocation.json', plan)
    write_json(stage/'manifest.json', plan)
    for path in children:
        path.rename(archive/path.name)
    stage.rename(current)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--publication', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--reports-only', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    value = retain(args.root, args.publication, args.archive, execute=args.execute, reports_only=args.reports_only)
    print(json.dumps({k:v for k,v in value.items() if k != 'selected_artifacts'}))


if __name__ == '__main__':
    main()
