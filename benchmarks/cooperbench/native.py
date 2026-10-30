"""Pinned upstream merge/tests with a bounded, network-isolated Docker backend.

Import only evaluator modules, not upstream agent/cloud package initializers.
No model, cloud SDK, daemon reconfiguration or automatic image pulls occur here.
"""
import importlib
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import uuid

from .adapter import UPSTREAM, verify_checkout


BACKEND_VERSION = 'isolated-docker-cli-v2'
BUILD_WHEELS = {
    'flit_core-3.11.0-py3-none-any.whl': 'fe464c086f630f106c0fc5001ee377980f45938f03f8f0d03da08a4841748541',
    'poetry_core-1.9.1-py3-none-any.whl': '6f45dd3598e0de8d9b0367360253d4c5d4d0110c8f5c71120a14f0e0f116c1a0',
}
CONTAINER_OPTIONS = ['--network', 'none', '--cpus', '2', '--memory', '4g', '--pids-limit', '256',
                     '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                     '--env', 'PIP_NO_INDEX=1', '--env', 'PIP_NO_BUILD_ISOLATION=0',
                     '--env', 'PIP_DISABLE_PIP_VERSION_CHECK=1']


class Result:
    def __init__(self, code, output):
        self.returncode, self.output = code, output
    def stdout_read(self):
        return self.output
    def stderr_read(self):
        return ''


class Sandbox:
    def __init__(self, container, timeout, workdir):
        self.container, self.workdir = container, workdir
        self.deadline = time.monotonic() + timeout

    def exec(self, *args):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Evaluator sandbox deadline exhausted')
        with tempfile.TemporaryFile() as stream:
            p = subprocess.run(['docker', 'exec', '-w', self.workdir, self.container,
                                'timeout', '--kill-after=2', str(max(1, int(remaining))), *args],
                               stdout=stream, stderr=subprocess.STDOUT, timeout=remaining + 5)
            stream.seek(0)
            output = stream.read(4_000_001)
        if len(output) > 4_000_000:
            raise RuntimeError('Evaluator output exceeded capture limit')
        if p.returncode in (124, 137):
            raise TimeoutError('Evaluator command timed out or was killed')
        return Result(p.returncode, output.decode(errors='replace'))

    def terminate(self):
        subprocess.run(['docker', 'rm', '-f', self.container], capture_output=True, timeout=20, check=True)


class DockerBackend:
    def create_sandbox(self, image, timeout=600, workdir='/workspace'):
        # Inspect first: a failed gate must not cause an implicit network pull.
        subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, timeout=15, check=True)
        name = 'mas-info-eval-' + uuid.uuid4().hex[:12]
        subprocess.run(['docker', 'run', '-d', '--name', name, '--label', 'project=MAS-information',
                        *CONTAINER_OPTIONS, '--entrypoint', '', '-w', workdir, image, 'sleep', 'infinity'],
                       capture_output=True, timeout=30, check=True)
        sandbox = Sandbox(name, timeout, workdir)
        try:
            provision_build_tools(sandbox)
            if sandbox.exec('mkdir', '-p', '/patches').returncode:
                raise RuntimeError('Unable to initialize evaluator patch directory')
        except BaseException:
            sandbox.terminate()
            raise
        return sandbox


def provision_build_tools(sandbox):
    """Copy only hash-pinned public wheels; keep workers/evaluators offline."""
    cache = Path(__file__).resolve().parents[2] / '.cache/cooperbench-wheels'
    for filename, digest in BUILD_WHEELS.items():
        wheel = cache / filename
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != digest:
            raise ValueError('Build wheel digest mismatch: ' + filename)
        subprocess.run(['docker', 'cp', str(wheel), sandbox.container + ':/tmp/' + filename],
                       capture_output=True, timeout=20, check=True)
    result = sandbox.exec('python', '-m', 'pip', 'install', '--no-index', '--no-deps',
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
