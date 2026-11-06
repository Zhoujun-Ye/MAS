"""Build opt-in MAS integration fragments without launching or writing anything."""

from pathlib import Path
import shlex

from .store import identifier


def fragments(root, run_id, *, python, actor='unknown', role='worker', entrypoint=None, mode='full', protocol='ledger-v1'):
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
    hook = shlex.join([python, '-I', entry, 'hook', *common, '--protocol', protocol])
    return dict(
        settings=dict(hooks={event: [dict(hooks=[dict(type='command', command=hook)])]
                            for event in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure',
                                          'SessionStart', 'SessionEnd', 'SubagentStart', 'SubagentStop')}),
        mcp=dict(mcpServers=dict(evidence=dict(command=python,
            args=['-I', entry, 'mcp', *common, '--actor', actor, '--role', role,
                  '--protocol', protocol, '--mode', mode]))))
