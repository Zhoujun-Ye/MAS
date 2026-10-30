"""Tools for an externally provisioned, disposable coding container.

This adapter never provisions containers or executes model commands on the host.
The caller owns container isolation, mounts, network policy and test fixtures.
"""
import subprocess
import uuid

from .agent import Observation, Tool


class ContainerWorkspace:
    def __init__(self, container, workdir="/workspace", timeout=60, output_limit=30000):
        if not container or container.startswith("-") or not workdir.startswith("/"):
            raise ValueError("An explicit container and absolute workspace are required")
        self.container, self.workdir = container, workdir
        self.timeout, self.output_limit = timeout, output_limit

    def execute(self, command, stdin=None):
        # stdout is spooled to disk so a noisy command cannot exhaust host RAM.
        import tempfile
        marker = '__command_exit_' + uuid.uuid4().hex + ':'
        wrapper = 'sh -c "$1"; code=$?; printf "\\n' + marker + '%s\\n" "$code"'
        with tempfile.TemporaryFile() as output:
            try:
                result = subprocess.run(
                    ["docker", "exec", "-i", "-w", self.workdir, self.container,
                     "timeout", "--kill-after=2", str(self.timeout), "sh", "-c", wrapper, 'sh', command],
                    input=stdin, text=True, stdout=output, stderr=subprocess.STDOUT,
                    timeout=self.timeout + 10, check=False)
                transport_code = result.returncode
            except subprocess.TimeoutExpired:
                transport_code = 124
            except OSError as error:
                return dict(exit_code=None, output=str(error), truncated=False,
                            execution_error=True, error_kind='execution_transport')
            size = output.tell()
            output.seek(max(0, size - 100))
            tail = output.read()
            suffix = b'\n' + marker.encode()
            parts = tail.rsplit(suffix, 1)
            complete = transport_code == 0 and len(parts) == 2 and parts[1].strip().isdigit()
            code = int(parts[1].strip()) if complete else transport_code
            payload_size = size - len(suffix) - len(parts[1]) if complete else size
            output.seek(0)
            data = output.read(min(payload_size, self.output_limit))
        return dict(exit_code=code, output=data.decode(errors="replace"),
                    truncated=payload_size > self.output_limit, execution_error=not complete,
                    error_kind=None if complete else 'execution_timeout' if code == 124 else 'execution_transport')

    def tools(self):
        import shlex

        def observation(result):
            header = f"Exit code: {result['exit_code']}; truncated: {str(result['truncated']).lower()}\n"
            return Observation(header + result['output'],
                               {"error": result.get('execution_error', False),
                                'error_kind': result.get('error_kind'),
                                **{k: result[k] for k in ('exit_code', 'truncated')}})

        def invoke(args, agent):
            result = self.execute(args["command"])
            return observation(result)

        def read(args, agent):
            # A read never executes repository hooks or shell text from the path.
            command = 'sha256sum -- ' if args.get('metadata_only', False) else 'cat -- '
            return invoke(dict(command=command + shlex.quote(args["path"])), agent)

        def write(args, agent):
            from pathlib import PurePosixPath
            path = args['path']
            result = self.execute("mkdir -p -- " + shlex.quote(str(PurePosixPath(path).parent))
                                  + " && cat > " + shlex.quote(path), args["content"])
            return observation(result)

        return [
            Tool("terminal", "Execute a shell command in the assigned disposable container.",
                 dict(type="object", properties={"command": dict(type="string", minLength=1)},
                      required=["command"], additionalProperties=False), invoke, budgeted=True),
            Tool("read_file", "Read a file, or its SHA-256 with metadata_only=true. Allowed after submission without reopening; reads current workspace, not frozen snapshot.",
                 dict(type="object", properties={"path": dict(type="string", minLength=1),
                                                "metadata_only": dict(type="boolean")},
                      required=["path"], additionalProperties=False), read, budgeted=True, read_only=True),
            Tool("write_file", "Write a file in the assigned container.",
                 dict(type="object", properties={"path": dict(type="string", minLength=1),
                                               "content": dict(type="string")},
                      required=["path", "content"], additionalProperties=False), write, budgeted=True),
        ]
