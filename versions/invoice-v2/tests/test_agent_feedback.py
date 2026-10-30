"""Interface regressions use simulated bills and scripted HTTP, not model scores."""
from copy import deepcopy
import io
import json
from urllib import request

import pytest

from flowops.cases import load_cases
from flowops.engine import ALLOWED_AGENT_ACTIONS, WorkflowSession
from flowops.models import Decision
from flowops.planner import OllamaPlanner
from flowops.tools import TOOL_CONTRACTS


def scripted_model(monkeypatch, actions):
    actions = iter(actions)
    requests = []

    def reply(req, timeout):
        payload = json.loads(req.data)
        requests.append(payload)
        action = next(actions)
        response = {'model': 'qwen3:4b-instruct', 'message': {
            'content': json.dumps({'action': action, 'reason': 'scripted interface test'})}}
        return io.BytesIO(json.dumps(response).encode())

    def forbidden(*args):
        raise AssertionError('LLM must never be replaced by rules')

    monkeypatch.setattr(request, 'urlopen', reply)
    monkeypatch.setattr('flowops.planner.RulesPlanner.decide', forbidden)
    return OllamaPlanner(model='qwen3:4b-instruct'), requests


def observations(requests):
    return [json.loads(r['messages'][1]['content']) for r in requests]


def test_model_stage_deploy_verify_close_with_real_tool_math(monkeypatch):
    planner, requests = scripted_model(monkeypatch, ['stage_split_fix', 'deploy', 'verify', 'close'])
    s = WorkflowSession(load_cases()['split_bill'])
    report = s.run(planner)
    assert report['status'] == 'CLOSED_VERIFIED'
    assert s.bill.split_cents == [550, 550]
    obs = observations(requests)
    assert obs[0]['action_history'] == []
    pending = obs[1]['pending_patch']
    assert pending['fields'] == {'split_cents': [550, 550]}
    assert pending['status'] == 'staged' and pending['deployment_ready']
    assert obs[1]['world']['split_cents'] == [600, 500]
    assert obs[1]['last_tool_result']['action'] == 'stage_split_fix'
    assert not obs[1]['last_tool_result']['verification']['passed']
    assert obs[2]['pending_patch']['status'] == 'none'
    assert obs[2]['world']['split_cents'] == [550, 550]
    assert obs[2]['verification']['passed']
    assert obs[3]['last_tool_result']['action'] == 'verify'
    assert all(len(o['allowed_actions']) > 1 for o in obs)
    assert all(r['options']['temperature'] == 0 for r in requests)
    assert all(d['provider_reported_model'] == 'qwen3:4b-instruct' for d in report['planner_decisions'])


@pytest.mark.parametrize('cid,total,split', [
    ('wrong_total_and_split', 1650, [825, 825]),
    ('rounding', 1725, [863, 862]),
])
def test_invoice_failure_excludes_wrong_repair_until_invoice_fixed(monkeypatch, cid, total, split):
    actions = ['stage_invoice_fix', 'deploy', 'stage_split_fix', 'deploy', 'verify', 'close']
    planner, requests = scripted_model(monkeypatch, actions)
    s = WorkflowSession(load_cases()[cid])
    assert s.run(planner)['status'] == 'CLOSED_VERIFIED'
    obs = observations(requests)
    assert 'stage_invoice_fix' in obs[0]['allowed_actions']
    assert 'stage_split_fix' not in obs[0]['allowed_actions']
    assert obs[1]['pending_patch']['fields'] == {'stored_total_cents': total}
    assert 'stage_split_fix' in obs[2]['allowed_actions']
    assert s.bill.stored_total_cents == total and s.bill.split_cents == split


def test_wrong_invoice_repair_is_rejected_with_feedback_not_substituted(monkeypatch):
    planner, requests = scripted_model(monkeypatch, ['stage_split_fix', 'stage_invoice_fix'])
    s = WorkflowSession(load_cases()['wrong_total_and_split'])
    before = s.bill.snapshot()
    assert s.step(planner)['action'] == 'tool_rejected'
    assert s.staged_patch is None and s.bill.snapshot() == before
    assert s.status == 'ACTIVE'
    s.step(planner)
    obs = observations(requests)[1]
    assert 'Repair invoice_total first' in obs['last_tool_error']
    assert obs['last_tool_result']['outcome'] == 'tool_rejected'
    assert [d['action'] for d in s.planner_decisions] == ['stage_split_fix', 'stage_invoice_fix']


def test_repeated_staging_gets_pending_patch_feedback_then_model_can_deploy(monkeypatch):
    planner, requests = scripted_model(monkeypatch, ['stage_split_fix', 'stage_split_fix', 'deploy', 'close'])
    s = WorkflowSession(load_cases()['split_bill'])
    assert s.run(planner)['status'] == 'CLOSED_VERIFIED'
    obs = observations(requests)
    assert 'stage_split_fix' not in obs[1]['allowed_actions']
    assert obs[2]['last_tool_result']['outcome'] == 'tool_rejected'
    assert 'already staged' in obs[2]['last_tool_error']
    assert obs[1] != obs[2]
    assert s.deploy_attempts == 1


def test_false_fix_feedback_retry_budget_and_model_selected_escalation(monkeypatch):
    actions = ['stage_split_fix', 'deploy', 'verify', 'stage_split_fix', 'deploy', 'escalate']
    planner, requests = scripted_model(monkeypatch, actions)
    s = WorkflowSession(load_cases()['fake_fix'])
    assert s.run(planner)['status'] == 'ESCALATED'
    obs = observations(requests)
    assert 'state unchanged' in obs[2]['last_tool_result']['message']
    assert not obs[2]['verification']['passed']
    assert obs[2]['deploy_attempts'] == 1
    assert not obs[2]['last_tool_result']['persisted_state_changed']
    assert not {'deploy', 'stage_split_fix', 'close'} & set(obs[-1]['allowed_actions'])
    assert obs[-1]['deploy_attempts'] == 2
    assert s.deploy_attempts == 2 and s.bill.version == 0
    assert s.history[-1]['action'] == 'escalate'
    assert not any(e['action'] == 'step_limit' for e in s.history)


@pytest.mark.parametrize('action', ['inspect', 'verify'])
def test_repeated_read_rejected_with_new_feedback_and_no_mutation(monkeypatch, action):
    planner, requests = scripted_model(monkeypatch, [action, action, 'escalate'])
    s = WorkflowSession(load_cases()['split_bill'])
    before = s.bill.snapshot()
    s.step(planner)
    rejected = s.step(planner)
    assert rejected['action'] == 'tool_rejected'
    assert 'Repeated non-progressing read' in rejected['message']
    assert s.bill.snapshot() == before
    s.step(planner)
    obs = observations(requests)
    assert action not in obs[1]['allowed_actions']
    assert obs[2]['last_tool_result']['action'] == action
    assert obs[2]['last_tool_result']['outcome'] == 'tool_rejected'
    assert len({json.dumps(r, sort_keys=True) for r in requests}) == 3
    assert s.status == 'ESCALATED' and s.history[-1]['action'] == 'escalate'


def test_reads_become_available_when_actual_state_changes_without_version(monkeypatch):
    planner, _ = scripted_model(monkeypatch, ['inspect', 'inspect'])
    s = WorkflowSession(load_cases()['split_bill'])
    s.step(planner)
    assert 'inspect' not in s.observe()['allowed_actions']
    s.bill.split_cents = [550, 550]
    assert 'inspect' in s.observe()['allowed_actions']
    assert s.step(planner)['action'] == 'inspect'


def test_no_recovery_tool_means_no_modifying_actions_and_correct_escalation(monkeypatch):
    planner, requests = scripted_model(monkeypatch, ['escalate'])
    s = WorkflowSession(load_cases()['outage'])
    assert s.run(planner)['status'] == 'ESCALATED'
    allowed = set(observations(requests)[0]['allowed_actions'])
    assert allowed == {'inspect', 'verify', 'request_approval', 'escalate'}
    assert s.deploy_attempts == 0 and s.step_count == 1
    assert s.history[-1]['action'] == 'escalate'


def test_persistent_invalid_model_stops_without_claiming_model_escalation(monkeypatch):
    planner, requests = scripted_model(monkeypatch, ['inspect'] * 12)
    s = WorkflowSession(load_cases()['split_bill'])
    assert s.run(planner)['status'] == 'ESCALATED'
    assert s.history[-1]['action'] == 'step_limit'
    assert len([e for e in s.history if e['action'] == 'tool_rejected']) == 11
    assert not any(d['action'] == 'escalate' for d in s.planner_decisions)
    assert len({json.dumps(r, sort_keys=True) for r in requests}) == 12
    assert len(s.observe()['action_history']) == 6


def test_all_tools_described_no_biased_example_or_hidden_criteria(monkeypatch):
    planner, requests = scripted_model(monkeypatch, ['inspect'])
    s = WorkflowSession(load_cases()['split_bill'])
    s.step(planner)
    obs = observations(requests)[0]
    assert set(obs['tools']) == ALLOWED_AGENT_ACTIONS == set(TOOL_CONTRACTS)
    assert all(t['description'] and t['preconditions'] for t in obs['tools'].values())
    assert 'stage_split_fix' not in requests[0]['messages'][0]['content']
    assert 'AcceptanceSpec' not in json.dumps(requests)
    assert 'acceptance' not in json.dumps(obs).lower()
    # A model sees copies, not mutable live proposals, history or tool metadata.
    s.act(Decision('stage_split_fix'))
    detached = s.observe()
    detached['pending_patch']['fields']['split_cents'][0] = 0
    detached['action_history'][0]['verification']['passed'] = True
    detached['tools']['deploy']['description'] = 'tampered'
    assert s.staged_patch == {'split_cents': [550, 550]}
    assert not s.action_feedback[0]['verification']['passed']
    assert s.observe()['tools']['deploy']['description'] != 'tampered'


def test_approval_gate_runs_no_model_and_leaks_no_modifying_availability(monkeypatch):
    planner, requests = scripted_model(monkeypatch, [])
    s = WorkflowSession(load_cases()['security_approval'])
    assert s.run(planner)['status'] == 'PAUSED_APPROVAL'
    assert requests == [] and s.observe()['allowed_actions'] == []
    assert not s.observe()['pending_patch']['deployment_ready']
    assert s._active_capability is None and s.deploy_attempts == 0


def test_model_cannot_supply_numeric_patch(monkeypatch):
    def reply(*args, **kwargs):
        return io.BytesIO(json.dumps({'message': {'content': json.dumps({
            'action': 'deploy', 'split_cents': [0, 0]})}}).encode())
    monkeypatch.setattr(request, 'urlopen', reply)
    s = WorkflowSession(load_cases()['split_bill'])
    with pytest.raises(RuntimeError, match='unsupported fields'):
        s.step(OllamaPlanner())
    assert s.bill.split_cents == [600, 500] and s.staged_patch is None
