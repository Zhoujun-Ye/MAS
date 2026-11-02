"""Tools for an externally provisioned, disposable coding container.

This adapter never provisions containers or executes model commands on the host.
The caller owns container isolation, mounts, network policy and test fixtures.
"""
import subprocess
import uuid
import codecs
import hashlib
import time
from pathlib import Path

from .agent import Observation, Tool


class ContainerWorkspace:
    def __init__(self, container, workdir="/workspace", timeout=60, output_limit=30000, archive_dir=None):
        if not container or container.startswith("-") or not workdir.startswith("/"):
            raise ValueError("An explicit container and absolute workspace are required")
        self.container, self.workdir = container, workdir
        self.timeout, self.output_limit = timeout, output_limit
        self.archive_dir = Path(archive_dir) if archive_dir is not None else None
        self.outputs = {}

    @staticmethod
    def page(data, final):
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        text = decoder.decode(data, final=final)
        return text, len(data) - len(decoder.getstate()[0])

    def execute(self, command, stdin=None, *, retain=False, timeout=None, capture_all=False):
        # stdout is spooled to disk so a noisy command cannot exhaust host RAM.
        import tempfile
        marker = '__command_exit_' + uuid.uuid4().hex + ':'
        timeout = self.timeout if timeout is None else timeout
        wrapper = 'sh -c "$1"; code=$?; printf "\\n' + marker + '%s\\n" "$code"'
        with tempfile.TemporaryFile() as output:
            started = time.monotonic()
            try:
                result = subprocess.run(
                    ["docker", "exec", "-i", "-w", self.workdir, self.container,
                     "timeout", "-k", "2", str(timeout), "sh", "-c", wrapper, 'sh', command],
                    input=stdin, text=True, stdout=output, stderr=subprocess.STDOUT,
                    timeout=timeout + 10, check=False)
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
            # BusyBox timeout returns the terminating signal (143/137), unlike
            # GNU's 124. A completed command with that exit still has a marker.
            timed_out = not complete and (code == 124 or
                (code in (137, 143) and time.monotonic() - started >= timeout - 0.1))
            payload_size = size - len(suffix) - len(parts[1]) if complete else size
            output.seek(0)
            data = output.read(payload_size if capture_all else min(payload_size, self.output_limit))
            extra = {}
            if retain and self.archive_dir is not None:
                self.archive_dir.mkdir(parents=True, exist_ok=True)
                key = 'output_' + uuid.uuid4().hex
                path = self.archive_dir / (key + '.bin')
                output.seek(0)
                remaining = payload_size
                digest = hashlib.sha256()
                with path.open('xb') as saved:
                    while remaining:
                        block = output.read(min(remaining, 1024 * 1024))
                        if not block:
                            raise RuntimeError('Incomplete output capture')
                        saved.write(block)
                        digest.update(block)
                        remaining -= len(block)
                self.outputs[key] = path
                extra = dict(output_id=key, output_bytes=payload_size, output_sha256=digest.hexdigest())
        text, consumed = self.page(data, len(data) == payload_size)
        return dict(exit_code=code, output=text, **extra, next_offset=consumed,
                    truncated=not capture_all and payload_size > self.output_limit, execution_error=not complete,
                    error_kind=None if complete else 'execution_timeout' if timed_out else 'execution_transport')

    def tools(self):
        import shlex

        def observation(result):
            header = f"Exit code: {result['exit_code']}; truncated: {str(result['truncated']).lower()}\n"
            if result.get('output_id'):
                more = result['next_offset'] < result['output_bytes']
                header = (f"Exit code: {result['exit_code']}; complete output retained as {result['output_id']}; "
                          f"bytes: {result['output_bytes']}; sha256: {result['output_sha256']}; "
                          f"page: 0..{result['next_offset']}; more: {str(more).lower()}. "
                          + (f"Use read_output(id=\"{result['output_id']}\", offset={result['next_offset']}) for the rest. " if more else '')
                          + '\n')
            return Observation(header + result['output'],
                               {"error": result.get('execution_error', False),
                                'error_kind': result.get('error_kind'),
                                'exit_code': result['exit_code'],
                                'truncated': result['truncated'] and not bool(result.get('output_id')),
                                'paginated': result['truncated'] and bool(result.get('output_id')),
                                'output_preserved': bool(result.get('output_id')),
                                **{k: result[k] for k in ('output_id', 'output_bytes', 'output_sha256', 'next_offset') if k in result}})

        def invoke(args, agent):
            options = dict(retain=True, timeout=args.get('timeout_seconds')) if self.archive_dir is not None else {}
            if args.get('timeout_seconds') is not None:
                options['timeout'] = args['timeout_seconds']
            if getattr(agent, 'session_budget', None) is not None:
                agent.session_budget.check()
                options['timeout'] = min(options.get('timeout') or self.timeout, agent.session_budget.remaining_seconds())
            result = self.execute(args["command"], **options)
            return observation(result)

        def read(args, agent):
            # A read never executes repository hooks or shell text from the path.
            command = 'sha256sum -- ' if args.get('metadata_only', False) else 'cat -- '
            return invoke(dict(command=command + shlex.quote(args["path"])), agent)

        def write(args, agent):
            from pathlib import PurePosixPath
            path = args['path']
            options = dict(retain=True) if self.archive_dir is not None else {}
            if getattr(agent, 'session_budget', None) is not None:
                agent.session_budget.check()
                options['timeout'] = min(self.timeout, agent.session_budget.remaining_seconds())
            result = self.execute("mkdir -p -- " + shlex.quote(str(PurePosixPath(path).parent))
                                  + " && cat > " + shlex.quote(path), args["content"], **options)
            return observation(result)

        def read_output(args, agent):
            path = self.outputs.get(args['id'])
            if path is None:
                raise ValueError('Unknown output ID in this workspace adapter')
            offset, limit = args.get('offset', 0), args.get('limit', self.output_limit)
            size = path.stat().st_size
            if offset > size:
                raise ValueError('Offset exceeds output size')
            with path.open('rb') as stream:
                stream.seek(offset)
                data = stream.read(limit)
            if data and 128 <= data[0] < 192:
                raise ValueError('Offset splits a UTF-8 character; use the returned next_offset')
            text, count = self.page(data, offset + len(data) == size)
            end = offset + count
            return Observation(f"Output: {args['id']}; bytes: {size}; page: {offset}..{end}; "
                               f"next_offset: {end}; more: {str(end < size).lower()}\n" + text,
                               dict(error=False, output_id=args['id'], output_bytes=size, next_offset=end,
                                    paginated=end < size, output_preserved=True))

        return [
            Tool("terminal", f"Execute in the configured workspace container, which may be shared. Large output is paged when read_output is available. Default timeout {self.timeout}s; request up to 600s for builds.",
                 dict(type="object", properties={"command": dict(type="string", minLength=1),
                                                "timeout_seconds": dict(type="integer", minimum=1, maximum=600)},
                      required=["command"], additionalProperties=False), invoke, budgeted=True),
            Tool("read_file", "Read a current workspace file, or its SHA-256 with metadata_only=true. Shared files may change during execution.",
                 dict(type="object", properties={"path": dict(type="string", minLength=1),
                                                "metadata_only": dict(type="boolean")},
                      required=["path"], additionalProperties=False), read, budgeted=True, read_only=True),
            Tool("write_file", "Write a file in the assigned container.",
                 dict(type="object", properties={"path": dict(type="string", minLength=1),
                                               "content": dict(type="string")},
                      required=["path", "content"], additionalProperties=False), write, budgeted=True),
        ] + ([Tool('read_output', 'Read a page of retained output by ID from this workspace adapter. Output storage may be shared by authorized agents.',
                   dict(type='object', properties=dict(id=dict(type='string'), offset=dict(type='integer', minimum=0),
                        limit=dict(type='integer', minimum=4, maximum=self.output_limit)), required=['id'], additionalProperties=False),
                   read_output, budgeted=True, read_only=True)] if self.archive_dir is not None else [])

    def audit_snapshot(self, *, timeout=None):
        """Trusted audit hook; requires git and python3 in the existing container."""
        import json
        import shlex
        from .workspace_audit import SNAPSHOT_SCRIPT
        result = self.execute("GIT_OPTIONAL_LOCKS=0 python3 -c " + shlex.quote(SNAPSHOT_SCRIPT), capture_all=True,
                              timeout=self.timeout if timeout is None else min(self.timeout, timeout))
        if result.get("execution_error") or result["exit_code"] != 0 or result["truncated"]:
            raise RuntimeError("Workspace audit failed or exceeded capture limit")
        return json.loads(result["output"])

    def export_artifact(self, path, sha256, *, timeout=None):
        """Read a bounded regular file through the container, matching frozen bytes."""
        import json
        import shlex
        from .artifacts import ARTIFACT_READ_SCRIPT, MAX_ARTIFACT_BYTES, workspace_relative_path
        path = workspace_relative_path(path, self.workdir)
        payload = dict(root=self.workdir, path=path, sha256=sha256, max_bytes=MAX_ARTIFACT_BYTES)
        result = self.execute("python3 -I -c " + shlex.quote(ARTIFACT_READ_SCRIPT), json.dumps(payload),
                              capture_all=True, timeout=self.timeout if timeout is None else min(self.timeout, timeout))
        if result.get("execution_error"):
            raise RuntimeError("Artifact export transport failed: " + str(result.get("error_kind")))
        if result["exit_code"] != 0 or result["truncated"]:
            raise ValueError("Cannot export frozen artifact: " + result["output"][-1000:])
        return json.loads(result["output"])
