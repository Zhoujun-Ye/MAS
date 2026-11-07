"""Offline engineering regressions, without a model provider."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from harness.evidence_mas.decision import complete_access
from harness.evidence_mas.sharing import pure_delay
from harness.runtime_support import runtime
from scripts.studies import benchmark_matrix as matrix


def test_access_requires_contiguous_input_and_output_not_read_count():
    def page(start, count):
        return dict(start=start, input_characters=count, output_characters=count,
                    total={'input': 10, 'output': 10})
    assert not complete_access([page(0, 1)] * 20)
    assert not complete_access([page(0, 4), page(5, 5)])
    assert complete_access([page(5, 5), page(0, 5)])
    assert complete_access([page(0, 6), page(4, 6)])


@pytest.mark.parametrize('command,expected', [
    ('sleep 30', True), ('/bin/sleep 0.5;', True),
    ('sleep 60; echo waited', True), ('sleep 40; echo done', True),
    ('sleep 30; echo "$SECRET"', False),
    ('while kill -0 "$pid"; do sleep 1; done', False),
    ('python compute.py; sleep 1', False), ('echo "sleep 30"', False),
    ('sleep $(compute)', False), ('sleep infinity', False)])
def test_wait_advice_does_not_parse_or_rewrite_real_work(command, expected):
    assert pure_delay(dict(hook_event_name='PostToolUse', tool_name='Bash',
                           tool_input={'command': command})) is expected


def test_capability_checks_import_not_merely_presence(tmp_path):
    (tmp_path/'broken_fixture.py').write_text('raise RuntimeError("broken ABI")')
    command = runtime.capability_command(['broken_fixture'])
    result = subprocess.run([sys.executable, *command[1:]], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 2
    receipt = json.loads(result.stdout)
    assert receipt['required_modules']['broken_fixture'] is False
    assert receipt['import_errors']['broken_fixture'] == 'RuntimeError'
    assert 'broken ABI' not in result.stdout


def test_functional_probes_are_frozen_and_not_run_on_host(tmp_path):
    path = tmp_path/'capability.py'
    marker = tmp_path/'must-not-exist'
    path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    first = runtime.capability_probes([path])
    assert not marker.exists()
    path.write_text('raise RuntimeError("missing model data")\n')
    assert first[0]['sha256'] != runtime.capability_probes([path])[0]['sha256']
    assert not marker.exists()
    path.write_text('invalid python !')
    with pytest.raises(SyntaxError):
        runtime.capability_probes([path])


def test_matrix_forwards_and_freezes_functional_probe(tmp_path):
    probe = tmp_path/'functional.py'
    probe.write_text('assert 2 + 2 == 4\n')
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path, image='fixture',
        credentials=tmp_path/'private', cpus=8, record_resources=True, compute_threads=4,
        require_module=[], capability_probe=[str(probe)], effort='high',
        backends=['claude-code-subagents', 'full'], concurrency=8, judge_concurrency=2)
    command = matrix.solver_command(args, 'kramabench', SimpleNamespace(id='fixture'), 'full', tmp_path/'out')
    assert command[command.index('--capability-probe') + 1] == str(probe)
    assert matrix.protocol_settings(args)['capability_probes'] == runtime.capability_probes([probe])
