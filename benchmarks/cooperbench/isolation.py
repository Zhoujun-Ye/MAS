"""Fail-closed worker Git isolation; evaluator sandboxes are separate."""
import re
import shlex

from .snapshot import checked


ISOLATION_VERSION = 'base-history-only-v1'


def verify_worker(workspace, base):
    if not re.fullmatch(r'[0-9a-f]{40,64}', base):
        raise ValueError('Expected an explicit base commit')
    if checked(workspace, 'git rev-parse HEAD') != base:
        raise ValueError('Worker HEAD differs from task base')
    if checked(workspace, 'git status --porcelain --untracked-files=all'):
        raise ValueError('Worker repository must start clean')
    if checked(workspace, 'git remote'):
        raise ValueError('Worker still has upstream remotes')
    if checked(workspace, 'git for-each-ref --format="%(refname)"'):
        raise ValueError('Worker must start detached without retained refs')
    if checked(workspace, f'git rev-list --all --not {base}'):
        raise ValueError('Future commits remain reachable')
    if checked(workspace, 'git reflog show --all --format="%H"'):
        raise ValueError('Worker reflogs must be empty')
    checked(workspace, 'test -d .git && test ! -e .git/objects/info/alternates '
            '&& test ! -e .git/info/grafts && test ! -e .git/shallow '
            '&& test ! -e .git/worktrees && test ! -e .git/lost-found')
    fsck = checked(workspace, 'git fsck --full --no-reflogs --unreachable')
    if re.search(r'(?m)^(unreachable|dangling) ', fsck):
        raise ValueError('Unreachable Git objects remain recoverable')
    checked(workspace, 'test -z "$(find /patches -mindepth 1 -print -quit)"')
    return dict(version=ISOLATION_VERSION, base=base, future_refs=False, unreachable_objects=False,
                evaluator_patches_present=False)


def prepare_worker(workspace):
    """Only call on a newly provisioned project-owned disposable container."""
    base = checked(workspace, 'git rev-parse HEAD')
    if not re.fullmatch(r'[0-9a-f]{40,64}', base):
        raise ValueError('Invalid worker base')
    if checked(workspace, 'git status --porcelain --untracked-files=all'):
        raise ValueError('Refusing to sanitize an already-used worker')
    checked(workspace, 'test -d .git && test ! -e .git/objects/info/alternates '
            '&& test ! -e .git/info/grafts && test ! -e .git/shallow && test ! -e .git/worktrees')
    checked(workspace, f'git checkout --detach {shlex.quote(base)}')
    checked(workspace, 'git remote | while IFS= read -r remote; do git remote remove "$remote" || exit; done')
    checked(workspace, "git for-each-ref --format='delete %(refname)' | git update-ref --stdin")
    checked(workspace, 'rm -rf .git/lost-found .git/ORIG_HEAD .git/FETCH_HEAD .git/MERGE_HEAD')
    checked(workspace, 'git reflog expire --expire=now --all && git gc --prune=now --quiet')
    receipt = verify_worker(workspace, base)
    checked(workspace, 'mkdir -p .cooperbench_scratch && printf "\\n/.cooperbench_scratch/\\n" >> .git/info/exclude')
    return receipt
