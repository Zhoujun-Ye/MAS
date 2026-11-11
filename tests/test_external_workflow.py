import pytest

from scripts.probes.external_workflow import WorkflowFixture
from scripts.common.prompts.conditions import condition_instructions
from types import SimpleNamespace


@pytest.mark.parametrize('backend',('claude-code-single-agent','claude-code-subagents'))
def test_synthetic_native_workflow_has_bounded_baseline_steps(backend):
    fixture=WorkflowFixture(backend,'python3 fixture.py','["A"]')
    messages=[dict(role='user',content='Synthetic task')]
    names=[]
    while True:
        block=fixture.next(dict(messages=messages))
        if block['type']=='text':break
        names.append(block['name'])
        messages.extend([dict(role='assistant',content=[block]),dict(role='user',content=[
            dict(type='tool_result',tool_use_id=block['id'],content='ok')])])
        assert len(names)<=3
    assert names==(['Bash','Write'] if backend.endswith('single-agent') else ['Bash','Agent','Write'])


@pytest.mark.parametrize('mode',('full','observations','full-prompt-only'))
def test_direct_condition_api_rejects_retired_modes(mode):
    with pytest.raises(ValueError,match='retired|Retired'):
        condition_instructions(SimpleNamespace(evidence_mode=mode),'claude-code-subagents')
