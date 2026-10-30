import json

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.agent_team import AgentTeam
from harness.communication import FORMS
from harness.pool import POOL, Member, TeamSpec, bind_permissions, select_team
from harness.trace import Trace, read_trace, validate


def submit_or_wait(messages, report="Work ready"):
    submitted = any(c['function']['name'] == 'submit_assignment' for m in messages for c in m.get('tool_calls', []))
    return dict(calls=[('wait_for_message', {})] if submitted else [('submit_assignment', dict(report=report, paths=[]))])


def policy(messages, tools, choice):
    role = messages[0]["content"].split("Reusable role: ")[1].split(".")[0]
    count = sum(m["role"] == "assistant" for m in messages)
    if role == "researcher" and count == 0:
        return {"calls": [("stock", {})]}
    if role == "researcher" and count == 1:
        return {"calls": [("send_message", {"recipient": "reviewer", "content": "Check warehouse B only.", "evidence_ids": ["e1"], "requires_reply": True})]}
    if role == 'leader':
        return dict(content='Verified final')
    if role == 'reviewer' and count > 0:
        return dict(calls=[('send_message', dict(recipient='researcher', content='Checked available evidence.')),
                           ('wait_for_message', {})])
    return submit_or_wait(messages)


def build(tmp_path, form, client=None, **limits):
    task = "Deliver only to warehouse A."
    spec = select_team(task, {"researcher": "Read inventory", "reviewer": "Verify warehouse", "leader": "Decide"})
    trace = Trace(tmp_path / f"{form}.jsonl", form)
    trace.emit("run_start")
    tool = Tool("stock", "Read stock", {"type": "object", "properties": {}},
                lambda args, agent: Observation("5 units, warehouse B only."))
    limits.setdefault("scheduler", "controlled")
    team = AgentTeam(spec, form, client or ScriptedClient(policy), trace, [tool],
                     {"researcher": ["stock"], "reviewer": [], "leader": []}, **limits)
    return task, team, trace


def test_direct_peer_delivery_and_controls(tmp_path):
    digests = set()
    for form in FORMS:
        task, team, trace = build(tmp_path, form)
        result = team.run_task(task)
        trace.emit("run_end", status=result["status"])
        trace.close()
        assert result["status"] == "completed"
        digests.add(team.control_digest)
        events = read_trace(trace.path)
        assert validate(events) == []
        assert any(e["type"] == "peer_delivery" and e["sender"] == "researcher" and e["recipient"] == "reviewer" for e in events)
        assert sum(b.used for b in team.budgets.values()) == 1
        assert all(task in a.messages[1]["content"] for a in team.agents.values())
        assert "stock" not in team.agents["reviewer"].tools
        assert "submit_assignment" not in team.agents["leader"].tools
        assert "submit_assignment" in team.agents["researcher"].tools
        with pytest.raises(ValueError):
            team.run_task(task)
    assert len(digests) == 1


def test_team_state_exposes_budget_and_grants_but_not_private_facts(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.run_task(task)
    states = [json.loads(m['content'])['team_state'] for m in team.agents['reviewer'].messages
              if m['role'] == 'user' and '"team_state"' in m['content']]
    assert states[-1]['domain_budget']['used'] == 0
    assert states[-1]['available_evidence_ids'] == ['e1']
    assert 'warehouse B' not in json.dumps(states)
    trace.close()


def test_acl_and_retrieval_not_a_global_notebook(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.run_task(task)
    reviewer = team.agents["reviewer"]
    read = reviewer.tools["read_evidence"].run
    assert "warehouse B only" in read({"id": "e1"}, reviewer).text
    before = team.read_budgets['reviewer'].used
    assert "not granted" in read({"id": "e999"}, reviewer).text
    assert team.read_budgets['reviewer'].used == before
    # Both the producer and the recipient completed with plain text. Neither
    # completion may implicitly forward owned or received evidence to leader.
    assert team.information.visible_ids('leader', 'e') == []
    with pytest.raises(ValueError):
        team.queue("reviewer", "leader", "Invented ref", ["e999"])
    trace.close()


def test_duplicate_completion_is_explicit_error_and_requester_receives_report(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.run_task(task)
    reviewer = team.agents['reviewer']
    sent = team.sent
    with pytest.raises(ValueError, match='already submitted'):
        team.submit_assignment(reviewer, 'late report', [])
    assert team.sent == sent
    trace.close()
    assert any(e['type'] == 'peer_queued' and e['sender'] == 'reviewer' and e['recipient'] == 'researcher'
               for e in read_trace(trace.path))


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_leader_can_initiate_before_any_worker_report(tmp_path, scheduler):
    def respond(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        count = sum(m['role'] == 'assistant' for m in messages)
        if role == 'leader':
            assert 'PRIVATE_WORKER_INPUT' not in str(messages)
            if count == 0:
                assert not any(m.get('content', '').startswith('Message ') for m in messages)
                return dict(calls=[('send_message', dict(recipient=r, content='Please begin.', requires_reply=True))
                                   for r in ('researcher', 'reviewer')] + [('wait_for_message', {})])
            return dict(content='Final')
        if 'Please begin.' not in str(messages):
            return dict(calls=[('wait_for_message', {})])
        return submit_or_wait(messages)
    task, team, trace = build(tmp_path, "agent_team", ScriptedClient(respond), scheduler=scheduler,
                              member_inputs={'researcher': 'PRIVATE_WORKER_INPUT'})
    assert team.run_task(task)['status'] == 'completed'
    trace.emit('run_end', status='completed')
    trace.close()
    events = read_trace(trace.path)
    leader_start = next(e['t'] for e in events if e['type'] == 'model_input' and e['agent'] == 'leader')
    first_submission = next(e['t'] for e in events if e['type'] == 'submission_snapshot')
    assert leader_start < first_submission
    assert team.control['startup'] == 'all-members-ready-v1'
    assert validate(events) == []


def test_adaptive_and_search_channels_removed(tmp_path):
    with pytest.raises(ValueError, match='Invalid handoff'):
        build(tmp_path, 'adaptive')
    task, team, trace = build(tmp_path, "agent_team")
    names = {tool.name for tool in team.communication_tools('researcher')}
    assert not names & {'request_evidence', 'search_artifacts'}
    trace.close()


def test_failed_domain_result_does_not_create_evidence(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.domain['stock'].run = lambda *args: Observation('Tool failed', {'error': True})
    assert team.run_task(task)['status'] == 'completed'
    assert not team.evidence and sum(b.used for b in team.budgets.values()) == 1
    trace.close()


def test_call_and_message_caps(tmp_path):
    task, team, trace = build(tmp_path, "agent_team", max_calls=3)
    result = team.run_task(task)
    assert result["status"] == "completed" and result["termination"] == "tasks_submitted"
    assert all(n <= 3 for n in team.calls_by_member.values())
    assert team.calls > 3  # Each member has its own quota.
    trace.close()


def test_message_limit_finalizes_with_explicit_resource_label(tmp_path):
    task, team, trace = build(tmp_path, "agent_team", max_messages=1)
    result = team.run_task(task)
    assert result["status"] == "completed" and result["termination"] == "tasks_submitted"
    assert all(n <= 1 for n in team.messages_by_member.values())
    assert "success" not in result  # Submission is not correctness.
    trace.close()


def test_capability_binding_does_not_grant_execution_to_reviewer():
    spec = select_team("check", {"executor": "Act", "reviewer": "Verify", "leader": "Summarize"})
    permissions = bind_permissions(spec, {"inspect": "read", "mutate": "execute"})
    assert permissions["reviewer"] == ("inspect",)
    assert permissions["executor"] == ("inspect", "mutate")
    assert permissions["leader"] == ()


def test_harness_rejects_leader_domain_grant(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    with pytest.raises(ValueError, match="communication-only"):
        AgentTeam(team.spec, "agent_team", team.client, trace, list(team.domain.values()),
                  {"researcher": ["stock"], "reviewer": [], "leader": ["stock"]})
    trace.close()


@pytest.mark.parametrize("form", FORMS)
def test_workspace_through_real_tool_loop_and_direct_peer_delivery(tmp_path, form):
    def respond(messages, tools, choice):
        role = messages[0]["content"].split("Reusable role: ")[1].split(".")[0]
        count = sum(m["role"] == "assistant" for m in messages)
        if role == "researcher":
            if count == 0:
                return dict(calls=[("publish_artifact", dict(kind="artifact", title="Calculation", content="PRIVATE_VALUE=17"))])
            if count == 1:
                return dict(calls=[("send_message", dict(recipient="reviewer", content="Verify this result",
                                                         artifact_ids=["a1"], requires_reply=True))])
            return submit_or_wait(messages, "Finished research")
        if role == "reviewer":
            state = json.loads(messages[-1]["content"])["team_state"]
            already_read = any(call["function"]["name"] == "read_artifact"
                               for m in messages for call in m.get("tool_calls", []))
            if state["available_artifact_ids"] and not already_read:
                return dict(calls=[("read_artifact", dict(id="a1"))])
            if not already_read:
                assert "PRIVATE_VALUE=17" not in str(messages)
            return submit_or_wait(messages, "Checked available information")
        assert "publish_artifact" in tools and "stock" not in tools
        assert "a1" not in json.loads(messages[-1]["content"])["team_state"]["available_artifact_ids"]
        return dict(content="Final decision")
    task, team, trace = build(tmp_path, form, ScriptedClient(respond), max_calls=48)
    result = team.run_task(task)
    trace.emit("run_end", status=result["status"])
    trace.close()
    assert result["status"] == "completed"
    assert result["termination"] == "tasks_submitted"
    assert validate(read_trace(trace.path)) == []
    assert "a1" in team.access["reviewer"]


def test_forged_leader_tool_call_cannot_retrieve(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.run_task(task)
    leader = team.agents["leader"]
    used = sum(b.used for b in team.budgets.values())
    obs = leader.run_tool(dict(id="forged", function=dict(name="stock", arguments="{}")))
    assert obs.meta["error"] and sum(b.used for b in team.budgets.values()) == used
    obs = team.domain_tool(team.domain["stock"]).run({}, leader)
    assert obs.meta["error_kind"] == "permission_denied"
    trace.close()


@pytest.mark.parametrize("form", FORMS)
def test_artifact_delivery_has_no_workspace_backdoor(tmp_path, form):
    task, team, trace = build(tmp_path, form)
    team.run_task(task)
    researcher, leader = team.agents["researcher"], team.agents["leader"]
    artifact = json.loads(researcher.tools["publish_artifact"].run(
        dict(kind="memory", title="Private note", content="PRIVATE_ARTIFACT"), researcher).text)
    assert "PRIVATE_ARTIFACT" not in str(leader.messages)
    for tool in ("read_artifact", "verify_artifact", "recover_artifact"):
        obs = leader.run_tool(dict(id=tool, function=dict(name=tool, arguments=json.dumps(dict(id=artifact["id"])))))
        assert obs.meta["error"] and "PRIVATE_ARTIFACT" not in obs.text
    team.queue("researcher", "leader", "Share note", [], artifact_ids=[artifact["id"]])
    team.deliver()
    assert artifact["id"] in team.access["leader"]
    obs = leader.tools["read_artifact"].run(dict(id=artifact["id"]), leader)
    assert "PRIVATE_ARTIFACT" in obs.text
    trace.close()


def test_context_overflow_is_incomplete_without_truncation(tmp_path):
    task, team, trace = build(tmp_path, "agent_team", max_input_chars=1)
    result = team.run_task(task)
    assert result["status"] == "incomplete" and result["reason"] == "member_limits"
    assert set(result['halted_members'].values()) == {'context_length'}
    assert task in team.agents["researcher"].messages[1]["content"]
    trace.close()


def test_new_request_cannot_reuse_team(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    with pytest.raises(ValueError, match="New public request"):
        team.run_task("A different request")
    trace.close()


def test_pool_and_solo_route(tmp_path):
    assert len(POOL) == 9 and "constraint_analyst" in POOL
    with pytest.raises(ValueError):
        TeamSpec("x", (Member("invented_expert", "work"),))
    spec = select_team("Small task", {"solver": "Solve directly"})
    with Trace(tmp_path / "solo.jsonl", "solo") as trace:
        team = AgentTeam(spec, "agent_team", ScriptedClient(lambda *a: {"content": "done"}), trace, [], {"solver": []})
        assert team.run_task("Small task")["status"] == "completed"
        assert team.calls == 1 and team.sent == 0


def test_stable_role_prefix_and_reasoning_passback(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.run_task(task)
    inputs = [r[0] for r in team.client.requests if r[0][0]["content"].startswith(POOL["researcher"].system)]
    assert len(inputs) > 1
    assert all(m["reasoning_content"] == "thinking" for history in inputs for m in history if m["role"] == "assistant")
    original = team.agents["researcher"].messages
    assert not any("handoff_instruction" in str(m) for m in original)
    trace.close()


def test_final_format_retry_is_counted_and_preserves_history(tmp_path):
    spec = select_team("Small task", {"solver": "Solve directly"})
    def reply(messages, *args):
        return {"content": "done" if any(m["role"] == "assistant" for m in messages) else "recap"}
    with Trace(tmp_path / "format.jsonl", "format") as trace:
        team = AgentTeam(spec, "agent_team", ScriptedClient(reply), trace, [], {"solver": []},
                         final_validator=lambda text: text == "done", final_contract="Return done.")
        result = team.run_task("Small task")
        assert result["status"] == "completed" and team.calls == 2
        assert any(m.get("content") == "recap" for m in team.agents["solver"].messages)


def test_cooperative_stop_prevents_new_calls(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.should_stop = lambda: True
    result = team.run_task(task)
    assert result["reason"] == "interrupted" and team.calls == 0
    trace.close()


@pytest.mark.parametrize("form", FORMS)
def test_finalization_delivers_sent_report_without_an_extra_model_call(tmp_path, form):
    secret = "PRIVATE_UNENCODED_REPORT"
    def reply(messages, tools, choice):
        if choice == "none":
            assert secret in str(messages)
            return {"content": "Insufficient evidence"}
        return {"calls": [("submit_assignment", {"report": secret})]}
    task, team, trace = build(tmp_path, form, ScriptedClient(reply), max_calls=2)
    result = team.run_task(task)
    assert result["termination"] == "budget_finalization"
    assert team.calls_by_member['leader'] == 2
    trace.close()


def test_budget_finalization_refuses_tools_and_counts_format_repair(tmp_path):
    def reply(messages, tools, choice):
        if 'submit_assignment' in tools:
            return dict(calls=[('submit_assignment', dict(report='Ready'))])
        if choice == "none":
            previous = sum(m["role"] == "assistant" for m in messages)
            return {"calls": [("stock", {})]} if previous == 1 else {"content": "valid"}
        return {"calls": [("stock", {})]}
    task, team, trace = build(tmp_path, "agent_team", ScriptedClient(reply), max_calls=3,
                              finalization_reserve=2)
    result = team.run_task(task)
    assert result["status"] == "completed" and team.calls_by_member['leader'] == 3
    assert sum(b.used for b in team.budgets.values()) == 0  # Finalization did not execute the requested tool.
    trace.emit("run_end", status=result["status"])
    trace.close()
    assert validate(read_trace(trace.path)) == []


@pytest.mark.parametrize("old", ["summary", "structured", "document_retrieval", "full_context", "adaptive"])
def test_old_modes_are_rejected(tmp_path, old):
    with pytest.raises(ValueError, match="Invalid handoff"):
        build(tmp_path, old)


def test_verbatim_mailbox_has_no_model_call_or_private_context_copy(tmp_path):
    task, team, trace = build(tmp_path, "agent_team")
    team.run_task(task)
    team.agents['researcher'].append(dict(role='user', content='PRIVATE_UNSENT_FACT'))
    text = 'Correction:\n  use x != 3; preserve spacing. 不确定。'
    before = team.calls
    team.queue('researcher', 'reviewer', text, [])
    team.deliver()
    team.receive('reviewer')
    received = team.agents['reviewer'].messages[-1]['content']
    assert received.split('\n\n', 1)[1] == text
    assert team.calls == before
    assert 'PRIVATE_UNSENT_FACT' not in str(team.agents['reviewer'].messages)
    assert team.ready['reviewer'] and team.submitted['reviewer']
    assert team.tasks['reviewer']['revision'] == 1
    trace.close()


def test_correction_wakes_worker_without_invalidating_submission(tmp_path):
    counts = {}
    def reply(messages, tools, choice):
        role = messages[0]['content'].split('Reusable role: ')[1].split('.')[0]
        counts[role] = counts.get(role, 0) + 1
        if role == 'reviewer' and counts[role] == 1:
            return dict(calls=[('send_message', dict(recipient='researcher', content='Correction: use 7.'))])
        if role == 'leader':
            return dict(content='Final')
        if role == 'researcher' and counts[role] == 2:
            return dict(calls=[('wait_for_message', {})])
        return dict(calls=[('submit_assignment', dict(report='Complete'))])
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(reply))
    assert team.run_task(task)['termination'] == 'tasks_submitted'
    assert counts['researcher'] == 2
    assert team.tasks['researcher']['revision'] == 1
    assert all(t['status'] == 'submitted' for r, t in team.tasks.items() if r != 'leader')
    trace.close()


def test_all_waiting_is_not_success(tmp_path):
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(
        lambda *a: dict(calls=[('wait_for_message', {})])))
    result = team.run_task(task)
    assert result['status'] == 'incomplete'
    assert result['reason'] == 'team_waiting_without_messages'
    trace.close()


@pytest.mark.parametrize('value, expected', [(7, 'passed'), (3, 'failed')])
def test_real_code_verification_is_separate_from_claimed_completion(tmp_path, value, expected):
    import subprocess
    import sys
    source = tmp_path / 'solution.py'
    source.write_text('result = ' + str(value))
    def verify(submissions):
        assert set(submissions) == {'researcher', 'reviewer'}
        result = subprocess.run([sys.executable, '-c',
            'from solution import result; assert result == 7'], cwd=tmp_path,
            capture_output=True, text=True, timeout=10)
        return dict(status='passed' if result.returncode == 0 else 'failed', exit_code=result.returncode)
    task, team, trace = build(tmp_path, 'agent_team', verifier=verify)
    result = team.run_task(task)
    assert result['status'] == 'completed'
    assert result['verification']['status'] == expected
    trace.close()
