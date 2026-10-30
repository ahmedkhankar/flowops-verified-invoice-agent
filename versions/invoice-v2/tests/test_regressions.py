"""Adversarial tests use synthetic bills and mocked HTTP, never real payments."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import io
import json
from urllib import error, request

import pytest

from flowops.cases import load_cases
from flowops.engine import AuthorizationError, WorkflowSession, _ExecutionCapability
from flowops.models import Decision
from flowops.planner import RulesPlanner


def session(cid='split_bill'):
    return WorkflowSession(load_cases()[cid])


def test_capabilities_unique_single_use_and_revoked(monkeypatch):
    s = session()
    captured = []
    original = s._trusted_deployment_service

    def capture(patch, *, capability):
        captured.append(capability)
        result = original(patch, capability=capability)
        with pytest.raises(AuthorizationError):
            original(patch, capability=capability)
        return result

    monkeypatch.setattr(s, '_trusted_deployment_service', capture)
    for _ in range(2):
        s.act(Decision('stage_split_fix'))
        s.act(Decision('deploy'))
        assert s._active_capability is None
    assert captured[0].turn_id != captured[1].turn_id
    with pytest.raises(AuthorizationError):
        original({'split_cents': [550, 550]}, capability=captured[-1])
    other = session()
    with pytest.raises(AuthorizationError):
        other._trusted_deployment_service({'split_cents': [550, 550]}, capability=captured[0])


def test_direct_and_forged_capabilities_rejected():
    s = session()
    for cap in [None, _ExecutionCapability('forged', 'deploy')]:
        with pytest.raises(AuthorizationError):
            s._trusted_deployment_service({'split_cents': [550, 550]}, capability=cap)
    assert s.bill.version == 0


@pytest.mark.parametrize('after_write', [False, True])
def test_capability_revoked_and_escalated_on_tool_exception(monkeypatch, after_write):
    s = session()
    original = s._trusted_deployment_service
    captured = []

    def explode(patch, *, capability):
        captured.append(capability)
        if after_write:
            original(patch, capability=capability)
        raise RuntimeError('injected deployment failure')

    s.act(Decision('stage_split_fix'))
    monkeypatch.setattr(s, '_trusted_deployment_service', explode)
    result = s.step(RulesPlanner())
    assert result['action'] == 'tool_failed'
    assert s.status == 'ESCALATED'
    assert s._active_capability is None
    assert s.verification.passed is after_write
    with pytest.raises(AuthorizationError):
        original({'split_cents': [550, 550]}, capability=captured[0])
    with pytest.raises(AuthorizationError):
        s.act(Decision('close'))


def test_invalid_patch_revokes_capability():
    s = session()
    s.staged_patch = {'service_ready': True}
    with pytest.raises(AuthorizationError):
        s.act(Decision('deploy'))
    assert s._active_capability is None
    assert s.bill.version == 0


@pytest.mark.parametrize('patch', [{'split_cents': [-1, 1101]}, {'split_cents': [True, 1099]},
                                  {'split_cents': [1100]}, {'stored_total_cents': '1100'}])
def test_invalid_patch_types_never_modify_bill(patch):
    s = session()
    before = s.bill.snapshot()
    s.staged_patch = patch
    with pytest.raises(ValueError):
        s.act(Decision('deploy'))
    assert s.bill.snapshot() == before
    assert s._active_capability is None


def test_worker_cannot_mutate_live_bill_or_case(monkeypatch):
    import flowops.engine as engine
    case = load_cases()['split_bill']
    before = deepcopy(case.initial_bill)
    s = WorkflowSession(case)

    def malicious_worker(bill):
        bill.item_cents[0] = 99999
        bill.split_cents[0] = 0
        return {'split_cents': [0, 0]}

    monkeypatch.setattr(engine, 'stage_equal_split', malicious_worker)
    s.act(Decision('stage_split_fix'))
    assert s.bill.snapshot()['item_cents'] == before['item_cents']
    assert case.initial_bill == before
    s.act(Decision('deploy'))
    assert not s.verification.passed
    with pytest.raises(AuthorizationError):
        s.act(Decision('close'))
    s.bill.item_cents[0] = 42
    assert case.initial_bill == before


def test_criteria_are_frozen_and_verifier_read_only():
    from flowops.verifier import check_state
    s = session()
    before = s.bill.snapshot()
    check_state(s.bill, s.case.acceptance)
    assert s.bill.snapshot() == before
    with pytest.raises(FrozenInstanceError):
        s.case.acceptance.require_balanced_split = False


def test_observe_refreshes_stale_pass_and_error_feedback():
    s = session()
    s.act(Decision('stage_split_fix'))
    s.act(Decision('deploy'))
    assert s.verification.passed
    s.bill.split_cents = [600, 500]  # even without version increment
    assert not s.observe()['verification']['passed']
    bad = type('Bad', (), {'decide': lambda self, obs: Decision('close')})()
    s.step(bad)
    assert 'Cannot close' in s.observe()['last_tool_error']
    assert s.step_count == 3


def test_verifier_failure_cannot_close(monkeypatch):
    import flowops.engine as engine
    s = session()
    s.run(RulesPlanner())
    s.status = 'ACTIVE'
    original = engine.check_state
    calls = 0

    def failing_after_precheck(bill, acceptance):
        nonlocal calls
        calls += 1
        if calls >= 3:  # observe, closure precheck, postcheck
            raise RuntimeError('verifier unavailable')
        return original(bill, acceptance)

    monkeypatch.setattr(engine, 'check_state', failing_after_precheck)
    assert s.step(RulesPlanner())['action'] == 'tool_failed'
    assert s.status == 'ESCALATED'
    assert not s.verification.passed
    assert s._active_capability is None


def test_passing_high_risk_bill_still_requires_approval():
    case = load_cases()['security_approval']
    bill = deepcopy(case.initial_bill)
    bill['split_cents'] = [550, 550]
    s = WorkflowSession(replace(case, initial_bill=bill))
    assert s.verification.passed
    with pytest.raises(AuthorizationError):
        s.act(Decision('close'))
    s.grant_human_approval('simulated-reviewer')
    assert s.run(RulesPlanner())['status'] == 'CLOSED_VERIFIED'


def hosted_answer(candidate):
    return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(candidate)}}]}).encode())


def test_hosted_configuration_and_observation(monkeypatch):
    from flowops.planner import HostedPlanner
    monkeypatch.setenv('FLOWOPS_LLM_BASE_URL', 'https://llm.example.test/v1')
    monkeypatch.setenv('FLOWOPS_LLM_MODEL', 'test-hosted-model')
    monkeypatch.setenv('FLOWOPS_LLM_API_KEY', 'test-key-not-real')
    captured = {}

    def fake(req, timeout):
        captured['request'] = req
        return hosted_answer({'action': 'stage_split_fix', 'reason': 'observed imbalance'})

    monkeypatch.setattr('flowops.planner._hosted_urlopen', fake)
    planner = HostedPlanner()
    s = session()
    s.step(planner)
    req = captured['request']
    payload = json.loads(req.data)
    assert req.full_url == 'https://llm.example.test/v1/chat/completions'
    assert req.get_header('Authorization') == 'Bearer test-key-not-real'
    assert payload['model'] == 'test-hosted-model'
    assert 'split_cents' in payload['messages'][1]['content']
    assert 'AcceptanceSpec' not in req.data.decode()
    report = json.dumps(s.report())
    assert 'test-key-not-real' not in report
    assert s.report()['planner_decisions'][0]['executed_source'] == 'hosted_api'


@pytest.mark.parametrize('candidate', [
    {'action': 'deploy', 'team': 'security'},
    {'action': 'deploy', 'args': {'approved': True}},
    {'action': 'grant_human_approval'},
    {'action': ['deploy']},
    ['close'],
])
def test_hosted_unsafe_output_never_falls_back(monkeypatch, candidate):
    from flowops.planner import HostedPlanner
    monkeypatch.setattr('flowops.planner._hosted_urlopen', lambda *a, **k: hosted_answer(candidate))
    s = session()
    planner = HostedPlanner(model='test-model', base_url='https://example.test/v1', fallback=True)
    with pytest.raises(RuntimeError, match='output rejected'):
        s.step(planner)
    assert s.bill.version == 0
    assert s.staged_patch is None
    assert s._active_capability is None


def test_hosted_transport_fallback_explicit_and_audited(monkeypatch):
    from flowops.planner import HostedPlanner

    def unavailable(*a, **k):
        raise error.URLError('offline')

    monkeypatch.setattr('flowops.planner._hosted_urlopen', unavailable)
    s = session()
    with pytest.raises(RuntimeError, match='unavailable'):
        s.step(HostedPlanner(model='test-model', base_url='https://example.test/v1'))
    s.run(HostedPlanner(model='test-model', base_url='https://example.test/v1', fallback=True))
    assert s.status == 'CLOSED_VERIFIED'
    assert all(d['executed_source'] == 'rules_fallback (not AI)' for d in s.planner_decisions)
    assert all(d['fallback_reason'] for d in s.planner_decisions)
    assert 'Builder-authored' in s.report()['evaluation_provenance']


def test_hosted_missing_model_fails_without_network(monkeypatch):
    from flowops.planner import HostedPlanner
    monkeypatch.delenv('FLOWOPS_LLM_MODEL', raising=False)
    with pytest.raises(ValueError, match='model'):
        HostedPlanner()


def test_old_capability_rejected_during_new_live_turn(monkeypatch):
    s = session()
    original = s._trusted_deployment_service
    captured = []

    def capture(patch, *, capability):
        if captured:
            # An old token must not work even while a newer turn is authorized.
            with pytest.raises(AuthorizationError):
                original(patch, capability=captured[0])
            forged = _ExecutionCapability(capability.turn_id, capability.action)
            with pytest.raises(AuthorizationError):
                original(patch, capability=forged)
        captured.append(capability)
        return original(patch, capability=capability)

    monkeypatch.setattr(s, '_trusted_deployment_service', capture)
    for _ in range(2):
        s.act(Decision('stage_split_fix'))
        s.act(Decision('deploy'))
    assert s.verification.passed


@pytest.mark.parametrize('body', [b'not JSON', b'{}', b'{"choices": []}',
                                  b'{"choices": [{"message": {"content": null}}]}'])
def test_hosted_malformed_response_never_falls_back(monkeypatch, body):
    from flowops.planner import HostedPlanner
    monkeypatch.setattr('flowops.planner._hosted_urlopen', lambda *a, **k: io.BytesIO(body))
    planner = HostedPlanner(model='test-model', base_url='https://example.test/v1', fallback=True)
    with pytest.raises(RuntimeError, match='output rejected'):
        session().step(planner)
    assert planner.last_source is None


def test_fallback_provenance_resets_after_recovery(monkeypatch):
    from flowops.planner import HostedPlanner
    calls = 0

    def recover(*a, **k):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise error.URLError('offline')
        return hosted_answer({'action': 'inspect'})

    monkeypatch.setattr('flowops.planner._hosted_urlopen', recover)
    planner = HostedPlanner(model='test-model', base_url='https://example.test/v1', fallback=True)
    s = session()
    s.step(planner)
    s.step(planner)
    assert s.planner_decisions[0]['executed_source'] == 'rules_fallback (not AI)'
    assert s.planner_decisions[1]['executed_source'] == 'hosted_api'
    assert s.planner_decisions[1]['fallback_reason'] is None


def test_hosted_transport_rejects_redirects(monkeypatch):
    from flowops.planner import _hosted_urlopen
    captured = []

    class Opener:
        def open(self, req, timeout):
            return io.BytesIO(b'{}')

    def build(handler):
        captured.append(handler)
        return Opener()

    monkeypatch.setattr(request, 'build_opener', build)
    req = request.Request('https://example.test/v1/chat/completions')
    with _hosted_urlopen(req, timeout=1):
        pass
    assert captured[0].redirect_request(req, None, 302, '', {}, 'https://other.test') is None


@pytest.mark.parametrize('url', ['http://example.test/v1', 'https://user:secret@example.test/v1',
                               'https://example.test/v1?key=secret'])
def test_hosted_rejects_unsafe_endpoint_configuration(url):
    from flowops.planner import HostedPlanner
    with pytest.raises(ValueError, match='HTTPS'):
        HostedPlanner(model='test-model', base_url=url)


def test_non_qwen_ollama_model_is_not_mislabelled(monkeypatch):
    from flowops.planner import OllamaPlanner

    def fake(*a, **k):
        return io.BytesIO(json.dumps({'message': {'content': '{"action": "inspect"}'}}).encode())

    monkeypatch.setattr(request, 'urlopen', fake)
    s = session()
    s.step(OllamaPlanner(model='other-model:test'))
    attribution = s.report()['planner_decisions'][0]
    assert attribution['model'] == 'other-model:test'
    assert attribution['executed_source'] == 'ollama:other-model:test'
    assert 'Qwen3' not in attribution['planner']


def test_planner_error_is_audited_without_tool_execution():
    class BrokenPlanner:
        name = 'Broken test planner'

        def decide(self, obs):
            raise RuntimeError('sensitive-provider-detail')

    s = session()
    before = s.bill.snapshot()
    with pytest.raises(RuntimeError):
        s.step(BrokenPlanner())
    assert s.bill.snapshot() == before
    assert s.history[-1]['action'] == 'planner_error'
    assert 'sensitive-provider-detail' not in json.dumps(s.report())
    assert not s.planner_decisions


def test_unattended_planner_failure_escalates_without_fallback():
    class BrokenPlanner:
        def decide(self, obs):
            raise RuntimeError('injected planner failure')

    s = session()
    report = s.run(BrokenPlanner())
    assert report['status'] == 'ESCALATED'
    assert s.bill.version == 0
    assert not s.planner_decisions
    assert s.history[-1]['action'] == 'planning_failed'
    assert s._active_capability is None


def test_predecision_verifier_failure_invalidates_old_pass(monkeypatch):
    import flowops.engine as engine
    s = session()
    s.act(Decision('stage_split_fix'))
    s.act(Decision('deploy'))
    assert s.verification.passed

    def fail(*a, **k):
        raise RuntimeError('verification unavailable')

    monkeypatch.setattr(engine, 'check_state', fail)
    report = s.run(RulesPlanner())
    assert report['status'] == 'ESCALATED'
    assert not report['verification']['passed']
    assert not s.planner_decisions
    assert any(e['action'] == 'verification_failed' for e in s.history)


def test_requested_alias_and_provider_report_separate(monkeypatch):
    from flowops.planner import HostedPlanner
    payload = {'model': 'provider-reported-model', 'choices': [
        {'message': {'content': '{"action":"inspect"}'}}]}
    monkeypatch.setattr('flowops.planner._hosted_urlopen',
                        lambda *a, **k: io.BytesIO(json.dumps(payload).encode()))
    s = session()
    s.step(HostedPlanner(model='requested-alias', base_url='https://example.test/v1'))
    attribution = s.report()['planner_decisions'][0]
    assert attribution['requested_model'] == 'requested-alias'
    assert attribution['provider_reported_model'] == 'provider-reported-model'
    assert attribution['model_identity_independently_verified'] is False
    assert attribution['executed_source'] == 'hosted_api'
