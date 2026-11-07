"""Build opt-in MAS integration fragments without launching or writing anything."""

from pathlib import Path
import shlex

from .store import identifier


def fragments(root, run_id, *, python, actor='unknown', role='worker', entrypoint=None, mode='full', protocol='observations-v1', share_context=False):
    identifier(run_id)
    if role not in ('lead', 'worker'):
        raise ValueError('role must be lead or worker')
    if mode not in ('full', 'observations'):
        raise ValueError('mode must be full or observations')
    root = Path(root)
    if not root.is_absolute() or not Path(python).is_absolute():
        raise ValueError('Use absolute target-runtime paths')
    entry = str(Path(entrypoint).absolute() if entrypoint else Path(__file__).with_name('entrypoint.py').resolve())
    common = ['--root', str(root), '--run-id', run_id]
    hook_args = [python, '-I', entry, 'hook', *common, '--protocol', protocol]
    if share_context:
        hook_args += ['--share-context', '--mode', mode]
    hook = shlex.join(hook_args)
    return dict(
        settings=dict(hooks={event: [dict(hooks=[dict(type='command', command=hook)])]
                            for event in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure',
                                          'SessionStart', 'SessionEnd', 'SubagentStart', 'SubagentStop')}),
        mcp=dict(mcpServers=dict(evidence=dict(command=python,
            args=['-I', entry, 'mcp', *common, '--actor', actor, '--role', role,
                  '--protocol', protocol, '--mode', mode]))))
