"""Shared standalone fixture retains Single denial and Subagents semantics."""

import pytest

from scripts.probes.native_transport import Fixture, frames
from scripts.probes.external_workflow import WorkflowFixture


def request(**extra):
    return dict(model='synthetic',tools=[{'name':'Agent'}],**extra)


def test_single_issues_two_denied_delegations_then_finishes():
    fixture=Fixture('single-agent',100)
    assert [fixture.reply(request())['content'][0]['name'] for _ in range(2)]==['Agent','Task']
    response=fixture.reply(request(messages=[dict(content=[dict(type='tool_result',tool_use_id='probe-Agent',is_error=True)])]))
    assert response['stop_reason']=='end_turn' and fixture.rejections=={'probe-Agent'}
    assert fixture.delegated is False


def test_subagents_delegates_only_once_and_budget_fixture_preserves_usage():
    fixture=Fixture('subagents',1_000_000)
    first=fixture.reply(request())
    assert first['content'][0]['name']=='Agent' and first['usage']['input_tokens']==100
    second=fixture.reply(request())
    assert second['stop_reason']=='end_turn' and second['usage']['input_tokens']==1_000_000
    assert fixture.delegated is True


@pytest.mark.parametrize('mode',['single-agent','subagents'])
def test_both_modes_share_complete_native_stream_frames(mode):
    response=Fixture(mode,100).reply(request())
    result=frames(response)
    assert [r['type'] for r in result]==['message_start','content_block_start','content_block_delta',
                                        'content_block_stop','message_delta','message_stop']
    assert result[0]['message']['content']==[] and result[-2]['delta']['stop_reason']=='tool_use'


def test_fixture_is_bounded_without_paid_fallback():
    fixture=Fixture('subagents',100)
    for _ in range(32):fixture.reply(request())
    with pytest.raises(ValueError,match='ceiling'):fixture.reply(request())


@pytest.mark.parametrize('backend', ('claude-code-single-agent', 'claude-code-subagents'))
def test_synthetic_native_workflow_has_bounded_baseline_steps(backend):
    fixture = WorkflowFixture(backend, 'python3 fixture.py', '["A"]')
    messages = [dict(role='user', content='Synthetic task')]
    names = []
    while True:
        block = fixture.next(dict(messages=messages))
        if block['type'] == 'text':
            break
        names.append(block['name'])
        messages.extend([dict(role='assistant', content=[block]), dict(role='user', content=[
            dict(type='tool_result', tool_use_id=block['id'], content='ok')])])
        assert len(names) <= 3
    assert names == (['Bash', 'Write'] if backend.endswith('single-agent') else ['Agent', 'Bash', 'Write'])
