"""Pinned public inputs, private feature assignments and official evaluation."""
from dataclasses import dataclass
import json
from itertools import combinations
from pathlib import Path
import re
import subprocess

from harness.agent import Observation, Tool
from harness.agent_team import AgentTeam
from harness.config import digest
from harness.pool import select_team, bind_permissions
from harness.file_exchange import exchange_tools
from harness.execution import ContainerWorkspace
from .snapshot import capture, checked
from .diagnostics import diagnose
from .errata import clarify

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT / 'upstream'
REVISION = '63b9d44d9f39a02fccf5bf0052db48a917a011fd'
URL = 'https://github.com/cooperbench/CooperBench.git'
LIMITS = dict(tool_budget=None, max_calls=None, max_messages=None, max_reads=None,
              max_input_chars=None, finalization_reserve=2,
              token_budget=None, time_limit_seconds=7200)
WORKERS = ('worker_a', 'worker_b')
MEMBER_LIMITS = {r: dict(tool_budget=None, max_calls=None, max_messages=None, max_reads=None) for r in WORKERS}
MEMBER_LIMITS['leader'] = dict(tool_budget=0, max_calls=None, max_messages=None, max_reads=None)

EVALUATION_CONTRACT = '''Team success requires BOTH features to pass their tests on the SAME merged codebase,
AND the two submitted patches to merge with zero conflicts. The evaluator applies
each worker's frozen patch to a branch from the common base and uses ordinary git
merge. Identical patches are accepted as one shared implementation. There is no
human or LLM that resolves conflicts or implements integration instructions from
your final report. A merge conflict fails the team, even if both workers' local
tests pass. Each feature is NOT scored only against its owner's standalone patch.
Private feature assignments specify responsibility, not a prohibition on sharing
or integrating code. You may exchange code/patches through messages or explicitly
granted artifacts, and may incorporate a teammate's changes in your own workspace.
Workspaces remain isolated. share_files exports selected changes exactly;
import_files applies an explicitly shared patch without copying its text.
There is no shared Git remote. You can verify integration using ordinary tools.
Only the selected implementation files frozen by submit_assignment are evaluated;
temporary simulations and prose integration plans are not submitted code.
The leader is responsible for coordinating a deliverable that satisfies this
joint contract, but has no code tools. Decide your collaboration strategy yourselves.
Hidden tests are evaluator-only. Submission is not verification of success.'''


def verify_checkout(root=UPSTREAM):
    root = Path(root)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all'], text=True)
    if head != REVISION or dirty:
        raise ValueError('CooperBench checkout must be clean and pinned to ' + REVISION)
    return root / 'dataset'


@dataclass(frozen=True)
class Pair:
    repo: str
    task_id: int
    features: tuple[int, int]

    def __post_init__(self):
        if not re.fullmatch(r'[a-zA-Z0-9_]+_task', self.repo) or type(self.task_id) is not int or self.task_id < 0:
            raise ValueError('Invalid repository/task identity')
        if len(self.features) != 2 or any(type(i) is not int or i < 1 for i in self.features) or self.features[0] >= self.features[1]:
            raise ValueError('Select two distinct feature IDs in ascending order')

    @property
    def key(self):
        return f'{self.repo}/task{self.task_id}/features_{self.features[0]}_{self.features[1]}'

    @property
    def image(self):
        name = self.repo.removesuffix('_task').replace('_', '-')
        return f'akhatua/cooperbench-{name}:task{self.task_id}'

    def private_inputs(self, dataset, profile='official'):
        task = Path(dataset) / self.repo / f'task{self.task_id}'
        # Gold and hidden test patches are evaluator-only. Never read them here.
        return {role: clarify((task / f'feature{feature}' / 'feature.md').read_text(),
                              self.repo, self.task_id, feature, profile)
                for role, feature in zip(WORKERS, self.features)}

    @property
    def request(self):
        return ('Implement both assigned features on independent copies of the same repository. '
                'Each worker receives only its own feature description. Coordinate interfaces, '
                'conflicts and verification using direct messages. Deliver code changes in your '
                'workspace; reports alone are not solutions. The leader coordinates without '
                'editing code. Do not modify tests. Keep reproduction scripts, temporary tests and logs in '
                '.cooperbench_scratch/. Submit only implementation files via submit_assignment(paths=[...]); '
                'plain text does not submit code. Task: ' + self.key
                + '\n\nEvaluation contract:\n' + EVALUATION_CONTRACT)


def discover(dataset):
    result = []
    for task in sorted(Path(dataset).glob('*_task/task*')):
        if not task.is_dir() or not re.fullmatch(r'task\d+', task.name):
            continue
        ids = sorted(int(f.parent.name[7:]) for f in task.glob('feature*/feature.md')
                     if re.fullmatch(r'feature\d+', f.parent.name))
        result.extend(Pair(task.parent.name, int(task.name[4:]), pair) for pair in combinations(ids, 2))
    return result


def make_team(pair, dataset, workspaces, client, trace, *, scheduler='async', benchmark_profile='official', **limits):
    if set(workspaces) != set(WORKERS) or workspaces['worker_a'] is workspaces['worker_b']:
        raise ValueError('Two distinct private worker workspaces are required')
    catalogues = {role: {t.name: t for t in workspace.tools()} for role, workspace in workspaces.items()}
    tools = []
    for name, original in catalogues['worker_a'].items():
        if any(name not in c or c[name].schema != original.schema for c in catalogues.values()):
            raise ValueError('Worker tool catalogues must match')
        def run(args, agent, name=name):
            return catalogues[agent.name][name].run(args, agent)
        tools.append(Tool(name, original.description, original.parameters, run, budgeted=True, read_only=original.read_only))
    spec = select_team(pair.request, {
        'worker_a': 'Implement your privately assigned feature and coordinate with your peer.',
        'worker_b': 'Implement your privately assigned feature and coordinate with your peer.',
        'leader': 'Coordinate the two workers and submit a concise completion report.'}, selector='cooperbench-fixed-v2', templates={'worker_a': 'coder', 'worker_b': 'coder'})
    capabilities = {'read_file': 'read', 'read_output': 'read', 'write_file': 'code', 'terminal': 'code'}
    holder = {}
    bases = {role: checked(w, 'git rev-parse HEAD') for role, w in workspaces.items()
             if isinstance(w, ContainerWorkspace)}
    def export(role, paths):
        workspace = workspaces[role]
        transport = ContainerWorkspace(workspace.container, workspace.workdir, output_limit=2_000_000)
        return capture(transport, bases[role], paths)

    def apply(role, payload):
        workspace = workspaces[role]
        if payload['base'] != bases[role]:
            raise ValueError('Patch base differs from this workspace')
        patch = payload['patch']
        if not patch:
            return Observation('Shared patch is empty.')
        result = workspace.execute('git apply --check -', patch)
        if result['exit_code'] or result['truncated']:
            return Observation('Patch not applied: ' + result['output'], dict(error=True, error_kind='patch_conflict'))
        result = workspace.execute('git apply -', patch)
        return Observation(result['output'] or 'Patch applied.', dict(error=bool(result['exit_code']),
                           error_kind='patch_apply_failed' if result['exit_code'] else None))

    tools += exchange_tools(lambda: holder['team'], export, apply)
    capabilities.update(share_files='code', import_files='code')
    permissions = bind_permissions(spec, {tool.name: capabilities[tool.name] for tool in tools})
    team = AgentTeam(spec, 'agent_team', client, trace, tools, permissions,
                     member_inputs=pair.private_inputs(dataset, benchmark_profile), scheduler=scheduler,
                     domain_policy=dict(benchmark='cooperbench', upstream_revision=REVISION,
                         setting='leader-led-adaptation', pair=pair.key, workspaces='independent'),
                     **(LIMITS | dict(member_limits=MEMBER_LIMITS) | limits))
    holder['team'] = team
    return team


def grade(pair, patches, dataset, evaluator=None):
    if set(patches) != set(WORKERS) or any(not isinstance(p, str) for p in patches.values()):
        raise ValueError('Both worker patches must be supplied explicitly')
    if evaluator is None:
        from .native import load_evaluator
        evaluator = load_evaluator().test_merged
    raw = evaluator(repo_name=pair.repo, task_id=pair.task_id,
        feature1_id=pair.features[0], feature2_id=pair.features[1],
        patch1=patches['worker_a'], patch2=patches['worker_b'],
        backend='docker', dataset_dir=str(dataset), timeout=1800)
    if raw.get('error'):
        return dict(status='error', correct=None, raw=raw, diagnostics=diagnose(pair, raw))
    # Preserve upstream output, but do not hide its lead-alone fallback behind
    # a claim that two independently produced patches merged successfully.
    merge_ok = raw.get('merge', {}).get('status') in ('clean', 'identical')
    return dict(status='graded', correct=bool(merge_ok and raw.get('both_passed')),
                official_both_passed=raw.get('both_passed'), raw=raw, diagnostics=diagnose(pair, raw))


def load_submitted_patches(output, manifest, result):
    """Fail closed before invoking an evaluator on unbound or stale artifacts."""
    if manifest.get('submission_contract') != 'immutable-snapshot-v1':
        raise ValueError('Frozen code snapshots are required for code evaluation')
    submissions = result.get('evaluation_snapshots', {})
    if set(submissions) != set(WORKERS):
        raise ValueError('Both worker submission versions are required')
    patches = {}
    for role in WORKERS:
        snapshot = json.loads((Path(output) / (role + '.submission.json')).read_text())
        artifact = snapshot['artifact']
        patch = (Path(output) / (role + '.patch')).read_text()
        if (snapshot['submission_id'] != submissions[role]['submission_id']
                or snapshot['submission_id'] != f"{role}:v{snapshot['revision']}" + (':terminal' if snapshot['kind'] == 'terminal' else '')
                or snapshot['kind'] not in ('explicit', 'terminal')
                or snapshot['kind'] != submissions[role]['kind']
                or snapshot['digest'] != submissions[role]['digest']
                or digest(artifact) != snapshot['digest']
                or artifact['patch'] != patch or artifact['base'] != manifest['bases'][role]):
            raise ValueError('Patch does not match the frozen submission version')
        patches[role] = patch
    return patches
