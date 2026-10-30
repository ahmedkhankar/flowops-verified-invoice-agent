import json
import pytest

from flowops.cases import load_cases
from flowops.engine import WorkflowSession, AuthorizationError
from flowops.models import Decision
from flowops.planner import RulesPlanner
from flowops.verifier import check_state

CASES = load_cases()


def run(case_id, *, approve=False):
    session = WorkflowSession(CASES[case_id])
    if approve:
        session.grant_human_approval('independent-reviewer')
    session.run(RulesPlanner())
    return session


def test_split_bill_end_to_end_autonomously():
    s = run('split_bill')
    assert s.status == 'CLOSED_VERIFIED'
    assert s.verification.passed
    assert s.bill.split_cents == [550, 550]
    assert any(x['action'] == 'deploy' for x in s.history)


def test_repairs_both_invoice_total_then_split():
    s = run('wrong_total_and_split')
    assert s.status == 'CLOSED_VERIFIED'
    assert s.bill.stored_total_cents == 1650
    assert s.bill.split_cents == [825, 825]
    assert s.deploy_attempts == 2


def test_high_risk_stops_before_any_modification():
    s = WorkflowSession(CASES['security_approval'])
    before = s.bill.snapshot()
    assert s.status == 'PAUSED_APPROVAL'
    assert s.step(RulesPlanner()) is None
    assert s.bill.snapshot() == before
    with pytest.raises(AuthorizationError):
        s.act(Decision('stage_split_fix'))
    with pytest.raises(ValueError):
        s.grant_human_approval('')
    s.grant_human_approval('real-human-in-simulation')
    assert s.run(RulesPlanner())['status'] == 'CLOSED_VERIFIED'
    assert s.approved_by == 'real-human-in-simulation'


def test_fake_worker_success_can_never_close():
    s = run('fake_fix')
    assert s.status == 'ESCALATED'
    assert s.deploy_attempts == 2
    assert not s.verification.passed
    assert s.bill.version == 0
    assert all(x['action'] != 'close' for x in s.history)
    with pytest.raises(AuthorizationError):
        s.act(Decision('close'))


def test_outage_without_recovery_tool_escalates():
    s = run('outage')
    assert s.status == 'ESCALATED'
    assert s.deploy_attempts == 0


def test_half_up_vat_and_odd_cent_split():
    s = run('rounding')
    assert s.status == 'CLOSED_VERIFIED'
    assert s.bill.stored_total_cents == 1725
    assert s.bill.split_cents == [863, 862]


@pytest.mark.parametrize('forged', [
    Decision('deploy', args={'team': 'security'}),
    Decision('deploy', args={'actor': 'deployment_service'}),
    Decision('deploy', args={'approved': True}),
    Decision('grant_human_approval'),
    Decision('run_shell', args={'command': 'whoami'}),
])
def test_cannot_forge_authorization_by_tool_arguments(forged):
    s = WorkflowSession(CASES['split_bill'])
    before = s.bill.snapshot()
    with pytest.raises(AuthorizationError):
        s.act(forged)
    assert s.bill.snapshot() == before
    assert not s.approved_by


def test_no_close_while_unverified_even_with_team_claim():
    s = WorkflowSession(CASES['split_bill'])
    s.staged_patch = {'split_cents': [550, 550]}
    with pytest.raises(AuthorizationError):
        s.act(Decision('close'))
    assert s.status == 'ACTIVE'
    assert s.bill.split_cents == [600, 500]


def test_fresh_verification_rejects_external_state_change():
    s = run('split_bill')
    assert s.status == 'CLOSED_VERIFIED'
    fresh = WorkflowSession(CASES['split_bill'])
    fresh.bill.split_cents = [600, 500]
    # Recomputed by authoritative verifier: cannot close despite previous tests.
    with pytest.raises(AuthorizationError):
        fresh.act(Decision('close'))


def test_agent_observation_never_includes_acceptance_spec():
    s = WorkflowSession(CASES['split_bill'])
    observation = json.dumps(s.observe())
    assert 'acceptance' not in observation.lower()
    assert 'expected_total' not in observation.lower()
    assert 'policy_sheet' in observation


def test_mutating_tool_does_not_provide_actor_parameter():
    s = WorkflowSession(CASES['split_bill'])
    s.act(Decision('stage_split_fix'))
    assert s.bill.version == 0  # staging alone is not executing a repair
    s.act(Decision('deploy'))
    assert s.bill.version == 1
    assert s.verification.passed


def test_approval_cannot_override_bad_verification():
    s = WorkflowSession(CASES['security_approval'])
    s.grant_human_approval('a-human')
    with pytest.raises(AuthorizationError):
        s.act(Decision('close'))


def test_invalid_and_unsafe_mode_do_not_close():
    s = WorkflowSession(CASES['split_bill'])
    for _ in range(2):
        event = s.step(type('BadPlanner', (), {'decide': lambda self, x: Decision('close')})())
        assert event['action'] == 'tool_rejected'
    assert s.status == 'ACTIVE'
    assert s.bill.split_cents != [550, 550]
    s.run(type('BadPlanner', (), {'decide': lambda self, x: Decision('close')})(), max_steps=2)
    assert s.status == 'ESCALATED'


def test_case_data_rejects_duplicate_ids(tmp_path):
    demo = json.loads((__import__('pathlib').Path(__file__).resolve().parents[1] / 'cases' / 'demo_cases.json').read_text())
    p = tmp_path / 'duplicates.json'
    p.write_text(json.dumps([demo[0], demo[0]]))
    with pytest.raises(ValueError, match='Duplicate'):
        load_cases(p)


def test_ollama_planner_is_strict_and_reads_world(monkeypatch):
    from flowops.planner import OllamaPlanner
    import io
    from urllib import request

    captured = {}

    def fake_urlopen(req, timeout):
        captured['payload'] = json.loads(req.data.decode())
        answer = {'message': {'content': json.dumps({'action': 'stage_split_fix', 'reason': 'split mismatch'})}}
        return io.BytesIO(json.dumps(answer).encode())

    monkeypatch.setattr(request, 'urlopen', fake_urlopen)
    obs = WorkflowSession(CASES['split_bill']).observe()
    decision = OllamaPlanner().decide(obs)
    assert decision.action == 'stage_split_fix'
    assert captured['payload']['think'] is False
    assert captured['payload']['format'] == 'json'
    observed_payload = captured['payload']['messages'][1]['content']
    assert 'split_cents' in observed_payload
    assert 'AcceptanceSpec' not in observed_payload


def test_ollama_cannot_invent_authentication_field(monkeypatch):
    from flowops.planner import OllamaPlanner
    import io
    from urllib import request

    def fake_urlopen(req, timeout):
        answer = {'message': {'content': json.dumps({
            'action': 'deploy', 'team': 'security', 'reason': 'impersonate'
        })}}
        return io.BytesIO(json.dumps(answer).encode())

    monkeypatch.setattr(request, 'urlopen', fake_urlopen)
    session = WorkflowSession(CASES['split_bill'])
    with pytest.raises(RuntimeError, match='unsupported fields'):
        session.step(OllamaPlanner())
    assert session.bill.version == 0
    assert session.status == 'ACTIVE'
