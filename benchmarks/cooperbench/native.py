"""Pinned upstream merge/tests with a bounded, network-isolated Docker backend.

Import only evaluator modules, not upstream agent/cloud package initializers.
No model, cloud SDK, daemon reconfiguration or automatic image pulls occur here.
"""
import importlib
import hashlib
from pathlib import Path
import subprocess
import sys
import shlex
import time
import types
import uuid

from .adapter import UPSTREAM, verify_checkout
from .environment import resolve
from .offline_assets import TOKENIZER_ASSETS
from harness.execution import ContainerWorkspace


BACKEND_VERSION = 'isolated-docker-cli-v9'
BUILD_WHEELS = {
    'flit_core-3.11.0-py3-none-any.whl': 'fe464c086f630f106c0fc5001ee377980f45938f03f8f0d03da08a4841748541',
    'poetry_core-1.9.1-py3-none-any.whl': '6f45dd3598e0de8d9b0367360253d4c5d4d0110c8f5c71120a14f0e0f116c1a0',
}
CONTAINER_OPTIONS = ['--network', 'none', '--cpus', '4', '--memory', '16g', '--pids-limit', '512',
                     '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                     '--env', 'PIP_NO_INDEX=1', '--env', 'PIP_NO_BUILD_ISOLATION=0',
                     '--env', 'UV_OFFLINE=1',
                     '--env', 'HF_HUB_OFFLINE=1', '--env', 'TRANSFORMERS_OFFLINE=1',
                     '--env', 'OMP_NUM_THREADS=4', '--env', 'MKL_NUM_THREADS=4',
                     '--env', 'OPENBLAS_NUM_THREADS=4', '--env', 'GOMAXPROCS=4',
                     '--env', 'CARGO_BUILD_JOBS=4',
                     '--env', 'PIP_DISABLE_PIP_VERSION_CHECK=1']


class Result:
    def __init__(self, code, output):
        self.returncode, self.output = code, output
    def stdout_read(self):
        return self.output
    def stderr_read(self):
        return ''


def diagnostic_runner_args(args):
    """Trace only the runner, retaining swallowed Go output and its exit code."""
    runner = '/usr/local/bin/runner.sh'
    if len(args) >= 2 and args[:2] == ('bash', runner):
        return ('bash', '-x', *args[1:])
    if len(args) == 3 and args[:2] == ('bash', '-c'):
        # The pinned evaluator emits this invocation as a standalone line.
        lines = args[2].splitlines(keepends=True)
        return ('bash', '-c', ''.join(
            'bash -x ' + line[len('bash '):] if line.startswith('bash ' + runner + ' ') else line
            for line in lines))
    return args


class Sandbox:
    def __init__(self, container, timeout, workdir, trace_runner=False):
        self.container, self.workdir = container, workdir
        self.trace_runner = trace_runner
        self.deadline = time.monotonic() + timeout

    def exec(self, *args):
        if self.trace_runner:
            args = diagnostic_runner_args(args)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Evaluator sandbox deadline exhausted')
        workspace = ContainerWorkspace(self.container, self.workdir, output_limit=4_000_000)
        command, stdin = shlex.join(map(str, args)), None
        if len(args) == 3 and args[:2] == ('bash', '-c') and len(command.encode()) > 60_000:
            # The upstream patch writer embeds base64 in bash -c. Linux limits
            # individual argv strings; transfer the full script via stdin.
            command = 'set -eu; file=$(mktemp); trap \'rm -f "$file"\' EXIT; cat > "$file"; bash "$file"'
            stdin = args[2]
        result = workspace.execute(command, stdin=stdin, timeout=max(1, int(remaining)))
        if result['truncated']:
            raise RuntimeError('Evaluator output exceeded capture limit')
        if result['execution_error']:
            error = TimeoutError if result['error_kind'] == 'execution_timeout' else RuntimeError
            raise error('Evaluator execution failed: ' + result['output'])
        return Result(result['exit_code'], result['output'])

    def terminate(self):
        subprocess.run(['docker', 'rm', '-f', self.container], capture_output=True, timeout=20, check=True)


class DockerBackend:
    def create_sandbox(self, image, timeout=1800, workdir='/workspace'):
        # Inspect first: a failed gate must not cause an implicit network pull.
        trace_runner = image.startswith('akhatua/cooperbench-go-chi:')
        environment = resolve(image)
        image = environment['image_id']
        options = [arg for key, value in environment['runtime_env'].items() for arg in ('--env', key + '=' + value)]
        name = 'mas-info-eval-' + uuid.uuid4().hex[:12]
        sandbox = Sandbox(name, timeout, workdir, trace_runner=trace_runner)
        try:
            subprocess.run(['docker', 'run', '-d', '--name', name, '--label', 'project=MAS-information',
                            *CONTAINER_OPTIONS, *options, '--entrypoint', '', '-w', workdir, image, 'sleep', 'infinity'],
                           capture_output=True, timeout=30, check=True)
            provision_build_tools(sandbox)
            provision_public_assets(sandbox, environment['runtime_env'])
            if environment['runtime_env'].get('COOPERBENCH_PUBLIC_ASSETS') == 'pdf':
                checked = sandbox.exec('python3', '-c',
                    "import importlib.util,pathlib; p=pathlib.Path(importlib.util.find_spec('llama_index.core').origin).resolve(); "
                    "assert p.is_relative_to(pathlib.Path('/workspace/repo/llama-index-core')), p")
                if checked.returncode:
                    raise RuntimeError('Task core must be imported from the editable workspace: ' + checked.stdout_read())
            if sandbox.exec('mkdir', '-p', '/patches').returncode:
                raise RuntimeError('Unable to initialize evaluator patch directory')
        except BaseException:
            # docker run may create the container before an interrupted client
            # returns. Remove only this uniquely named, project-owned sandbox.
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=20, check=False)
            raise
        return sandbox


def provision_public_assets(sandbox, runtime_env):
    """Install explicit offline transports without changing repository/tests."""
    profile = runtime_env.get('COOPERBENCH_PUBLIC_ASSETS')
    if not profile:
        return
    target = '/opt/cooperbench-public'
    if profile == 'tiktoken':
        target += '/tiktoken'
    if sandbox.exec('mkdir', '-p', target).returncode:
        raise RuntimeError('Unable to initialize public asset directory')
    files = [(Path(__file__).with_name('offline_assets.py'), 'mas_cooperbench_offline.py')]
    if profile == 'tiktoken':
        root = Path(__file__).resolve().parents[2] / '.cache/cooperbench-public/tiktoken'
        files = [(root / hashlib.sha1(url.encode()).hexdigest(), hashlib.sha1(url.encode()).hexdigest())
                 for url in TOKENIZER_ASSETS]
    if profile == 'pdf':
        files.append((Path(__file__).resolve().parents[2] / '.cache/cooperbench-public/dummy.pdf', 'dummy.pdf'))
    for source, name in files:
        subprocess.run(['docker', 'cp', str(source), sandbox.container + ':' + target + '/' + name],
                       check=True, capture_output=True, timeout=30)
    if profile == 'tiktoken':
        return
    result = sandbox.exec('python3', '-c',
        "import pathlib,sysconfig; p=pathlib.Path(sysconfig.get_paths()['purelib'])/'mas_cooperbench_offline.pth'; "
        "p.write_text('/opt/cooperbench-public\\nimport mas_cooperbench_offline; mas_cooperbench_offline.install()\\n')")
    if result.returncode:
        raise RuntimeError('Unable to install offline asset transport: ' + result.stdout_read())


def provision_build_tools(sandbox):
    """Copy only hash-pinned public wheels; keep workers/evaluators offline."""
    cache = Path(__file__).resolve().parents[2] / '.cache/cooperbench-wheels'
    for filename, digest in BUILD_WHEELS.items():
        wheel = cache / filename
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != digest:
            raise ValueError('Build wheel digest mismatch: ' + filename)
        subprocess.run(['docker', 'cp', str(wheel), sandbox.container + ':/tmp/' + filename],
                       capture_output=True, timeout=20, check=True)
    result = sandbox.exec('python3', '-m', 'pip', 'install', '--no-index', '--no-deps',
                          *['/tmp/' + name for name in BUILD_WHEELS])
    if result.returncode:
        raise RuntimeError('Offline build dependency install failed: ' + result.stdout_read())


def load_evaluator():
    verify_checkout()
    root = UPSTREAM / 'src/cooperbench'
    # Namespace package shells avoid __init__ importing every hosted agent/SDK.
    # sandbox.py, base.py, tasks.py and utils.py themselves are unmodified upstream.
    for name, relative in [('cooperbench', ''), ('cooperbench.eval', 'eval'),
                           ('cooperbench.runner', 'runner'), ('cooperbench.eval.backends', 'eval/backends')]:
        path = str(root / relative)
        if name in sys.modules:
            if path not in getattr(sys.modules[name], '__path__', []):
                raise RuntimeError('Conflicting evaluator package already imported')
            continue
        package = types.ModuleType(name)
        package.__path__ = [path]
        sys.modules[name] = package
    def get_backend(name='docker'):
        if name != 'docker':
            raise ValueError('Only isolated local Docker evaluation is authorized')
        return DockerBackend()
    sys.modules['cooperbench.eval.backends'].get_backend = get_backend
    return importlib.import_module('cooperbench.eval.sandbox')
