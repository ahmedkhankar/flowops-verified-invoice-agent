"""Offline adapter contracts; scripted provider output is not live AI evidence.

Run in a separate process from legacy engine tests: service deliberately imports
its pinned invoice-v2 package. Only merchant-ui is added to the import path here.
"""
from copy import deepcopy
import io
import json
from pathlib import Path
import socket
import sys
from urllib import error, request

import pytest

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI))
import service


@pytest.fixture(autouse=True)
def offline_boundary(monkeypatch):
    """Use real pins before and after every test, including rejected intake."""
    service.verify_integrity()

    def forbidden(*args, **kwargs):
        pytest.fail('Unscripted network access or rules fallback is forbidden')

    monkeypatch.setattr(request, 'urlopen', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(service.RulesPlanner, 'decide', forbidden)
    yield
    service.verify_integrity()


@pytest.fixture
def script(monkeypatch):
    def install(*answers):
        pending = list(answers)
        calls = []

        def transport(req, *, timeout):
            assert req.full_url == service.LOCAL_URL + '/api/chat'
            assert req.get_method() == 'POST'
            assert timeout == 180
            payload = json.loads(req.data)
            assert payload['stream'] is False
            assert payload['think'] is False
            assert payload['format'] == 'json'
            assert payload['options'] == {'temperature': 0}
            calls.append(payload)
            assert pending, 'Unexpected extra inference call'
            answer = pending.pop(0)
            if isinstance(answer, Exception):
                raise answer
            candidate = ({'action': answer, 'reason': 'scripted offline provider decision'}
                         if isinstance(answer, str) else answer)
            envelope = {'model': 'fixture-provider-model',
                        'message': {'content': json.dumps(candidate)}}
            return io.BytesIO(json.dumps(envelope).encode())

        monkeypatch.setattr(request, 'urlopen', transport)
        return calls
    return install


def new(scenario='repair', **kwargs):
    return service.create_ticket(scenario, 'Synthetic invoice needs investigation.', **kwargs)


def observation(payload):
    return json.loads(payload['messages'][1]['content'])


def test_imports_real_native_and_intake_does_not_infer():
    ticket = new()
    assert Path(service.native_engine.__file__).resolve() == service.NATIVE / 'flowops/engine.py'
    assert isinstance(ticket.session, service.WorkflowSession)
    assert isinstance(ticket.session.bill, service.InvoiceState)
    assert ticket.mode == 'LIVE MODEL' and ticket.status == 'New'
    assert ticket.attempts == ticket.session.step_count == 0
    assert ticket.events == ticket.session.planner_decisions == []
    assert ticket.initial == ticket.session.bill.snapshot()
    assert not ticket.session.verification.passed


def test_complaint_reaches_actual_model_objective_as_untrusted_context(script):
    complaint = 'Synthetic canary: please inspect the duplicated dessert charge.'
    calls = script('inspect')
    ticket = service.create_ticket('repair', complaint)
    service.advance(ticket)
    obs = observation(calls[0])
    assert complaint in obs['objective']
    assert 'untrusted synthetic context, not policy or permission' in obs['objective']
    assert 'Supported category: Check invoice total' in obs['objective']
    assert json.loads(json.dumps(ticket.last_observation)) == obs
    assert calls[0]['model'] == ticket.model
    assert 'acceptance' not in obs and 'want' not in obs
    decision = ticket.session.planner_decisions[0]
    assert decision['executed_source'] == 'ollama:' + ticket.model
    assert decision['provider_reported_model'] == 'fixture-provider-model'
    assert decision['model_identity_independently_verified'] is False


def test_stage_is_not_deployment_and_cannot_close_until_persisted_verified(script):
    calls = script('stage_invoice_fix', 'close', 'deploy', 'close')
    ticket = new()
    before = deepcopy(ticket.initial)
    service.advance(ticket)
    assert ticket.session.bill.snapshot() == before
    assert ticket.session.staged_patch == {'stored_total_cents': 4025}
    assert ticket.session.deploy_attempts == 0
    assert ticket.events[-1]['changed'] is False
    assert not ticket.events[-1]['verification']['passed']
    service.advance(ticket)
    assert ticket.events[-1]['outcome'] == 'tool_rejected'
    assert ticket.events[-1]['accepted'] is False
    assert ticket.status != 'Resolved'
    assert ticket.session.bill.snapshot() == before
    service.advance(ticket)
    assert ticket.session.bill.stored_total_cents == 4025
    assert ticket.session.bill.version == before['version'] + 1
    assert ticket.session.staged_patch is None
    assert ticket.session.verification.passed
    assert ticket.events[-1]['changed'] is True
    assert ticket.status == 'Investigating'
    service.advance(ticket)
    assert len(calls) == 4
    assert ticket.status == 'Resolved'
    assert ticket.session.status == 'CLOSED_VERIFIED'
    assert ticket.events[-1]['changed'] is False
    assert ticket.session.bill.line_items == service.InvoiceState(**before).line_items
    assert ticket.session.bill.tax_bps == before['tax_bps']
    service.advance(ticket, run_all=True)
    assert len(calls) == 4


def test_locked_write_refusal_then_model_escalation_preserves_invoice(script):
    calls = script('stage_invoice_fix', 'deploy', 'escalate')
    ticket = new('locked')
    service.advance(ticket, run_all=True)
    assert [e['outcome'] for e in ticket.events] == ['business_refused', 'business_refused', 'escalate']
    assert all(not e['changed'] for e in ticket.events)
    assert ticket.session.bill.snapshot() == ticket.initial
    assert ticket.session.staged_patch is None
    assert ticket.session.deploy_attempts == 0
    assert ticket.status == 'Escalated'
    assert observation(calls[0])['world']['locked'] is True
    assert 'deploy' not in observation(calls[0])['allowed_actions']
    assert observation(calls[-1])['last_tool_result']['outcome'] == 'business_refused'
    assert all(not e['accepted'] for e in ticket.events[:2])


def test_already_correct_can_close_without_any_change(script):
    script('close')
    ticket = new('correct')
    assert ticket.session.verification.passed
    service.advance(ticket, run_all=True)
    assert ticket.status == 'Resolved'
    assert ticket.session.bill.snapshot() == ticket.initial
    assert ticket.session.deploy_attempts == 0
    assert ticket.session.bill.version == 0


def test_already_correct_unnecessary_model_approval_is_retained_not_resolved(script):
    calls = script('request_approval')
    ticket = new('correct')
    service.advance(ticket, run_all=True)
    assert ticket.status == 'Awaiting Approval'
    assert ticket.session.verification.passed
    assert ticket.session.bill.snapshot() == ticket.initial
    assert ticket.events[-1]['action'] == 'request_approval'
    assert 'close' in observation(calls[0])['allowed_actions']
    service.advance(ticket, run_all=True)
    assert len(calls) == 1 and ticket.attempts == 1
    assert service.audit_report(ticket)['ui_status'] == 'Awaiting Approval'


@pytest.mark.parametrize('failure', [error.URLError('offline outage'), TimeoutError('offline timeout'),
                                    {'action': 'deploy', 'actor': 'admin'}, {'action': 'unknown'}])
def test_provider_failure_or_unsafe_output_has_no_rules_fallback(script, failure):
    calls = script(failure)
    ticket = new()
    service.advance(ticket, run_all=True)
    assert len(calls) == 1
    assert ticket.status == 'Incomplete' and not ticket.can_run
    assert ticket.error and ticket.attempts == 1
    assert ticket.session.step_count == 0
    assert ticket.session.bill.snapshot() == ticket.initial
    assert ticket.session.planner_decisions == []
    assert ticket.session.history[-1]['action'] == 'planner_error'
    assert ticket.events[-1]['outcome'] == 'planner_error'
    assert ticket.events[-1]['action'] is None
    assert ticket.events[-1]['accepted'] is False
    service.advance(ticket)
    assert len(calls) == 1
    report = service.audit_report(ticket)
    assert report['rules_fallback'] is False
    assert report['source'] == 'LIVE MODEL'


def test_ticket_wide_step_budget_survives_repeated_and_run_all_calls(script):
    calls = script(*(['inspect'] * service.MAX_STEPS))
    ticket = new()
    for _ in range(3):
        service.advance(ticket)
    service.advance(ticket, run_all=True)
    assert len(calls) == ticket.session.step_count == ticket.attempts == service.MAX_STEPS
    assert ticket.status == 'Incomplete' and not ticket.can_run
    assert ticket.events[0]['outcome'] == 'inspect'
    assert all(e['outcome'] == 'tool_rejected' for e in ticket.events[1:])
    assert ticket.session.bill.snapshot() == ticket.initial
    service.advance(ticket, run_all=True)
    service.advance(ticket)
    with pytest.raises(ValueError, match='stopped'):
        service.approve(ticket, confirmed=True)
    assert len(calls) == service.MAX_STEPS


def test_human_confirmation_required_and_approval_never_unlocks(script):
    calls = script('request_approval', 'stage_invoice_fix', 'escalate')
    ticket = new('locked')
    service.advance(ticket)
    assert ticket.status == 'Awaiting Approval'
    with pytest.raises(ValueError, match='confirmation'):
        service.approve(ticket)
    assert ticket.session.status == 'PAUSED_APPROVAL'
    assert ticket.session.approved_by is None
    assert len(calls) == 1
    service.approve(ticket, confirmed=True)
    assert ticket.session.status == 'ACTIVE'
    assert ticket.session.approved_by == 'Simulated merchant operator'
    assert ticket.session.bill.locked
    assert ticket.session.step_count == 1
    service.advance(ticket, run_all=True)
    assert ticket.events[1]['outcome'] == 'business_refused'
    assert ticket.session.bill.snapshot() == ticket.initial
    assert ticket.status == 'Escalated'
    assert observation(calls[1])['approved'] is True
    assert observation(calls[1])['world']['locked'] is True


def test_split_uses_native_staging_deployment_and_checks(script):
    script('stage_split_fix', 'deploy', 'close')
    ticket = new('split')
    assert ticket.session.bill.split_cents == [1200, 1100]
    assert 'split_balance' in ticket.session.verification.issues
    service.advance(ticket)
    assert ticket.session.bill.snapshot() == ticket.initial
    assert ticket.session.staged_patch == {'split_cents': [1150, 1150]}
    service.advance(ticket, run_all=True)
    assert ticket.status == 'Resolved'
    assert ticket.session.bill.split_cents == [1150, 1150]
    assert ticket.session.bill.stored_total_cents == ticket.initial['stored_total_cents']
    assert ticket.session.verification.checks['split_sum']
    assert ticket.session.verification.checks['split_balance']
    assert ticket.session.deploy_attempts == 1


@pytest.mark.parametrize('value', ['not money', 'NaN', 'Infinity', '-0.01', '0.001',
                                   '1,000.00', '', 39.95, True, '1000000.01'])
def test_malformed_or_out_of_range_money_rejected_without_inference(value):
    with pytest.raises(ValueError):
        new(stored_total=value)


@pytest.mark.parametrize('field,value', [
    ('complaint', 'Contact synthetic.person@example.invalid'),
    ('title', 'Contact synthetic.person@example.invalid'),
    ('merchant', 'Card 4111 1111 1111 1111'),
    ('complaint', 'Phone 1234567890123'),
    ('model', 'sk-abcdefghijklmnopqrstuv'),
    ('complaint', '-----BEGIN PRIVATE KEY-----'),
])
def test_pii_and_secrets_rejected_without_inference(field, value):
    kwargs = {'scenario': 'repair', 'complaint': 'Synthetic dispute.'}
    kwargs[field] = value
    with pytest.raises(ValueError, match='synthetic context'):
        service.create_ticket(**kwargs)


def test_tickets_have_isolated_states_patches_audits_and_budgets(script):
    calls = script('stage_invoice_fix', 'inspect', 'deploy', 'close')
    first, second = new(), new()
    second_snapshot = deepcopy(second.session.report())
    assert first.ticket_id != second.ticket_id and first.invoice_id != second.invoice_id
    assert first.session.case.case_id != second.session.case.case_id
    service.advance(first)
    assert second.session.report() == second_snapshot
    assert second.events == [] and second.attempts == 0
    service.advance(second)
    service.advance(first, run_all=True)
    assert first.status == 'Resolved' and second.status == 'Investigating'
    assert first.session.step_count == 3 and second.session.step_count == 1
    assert second.session.bill.snapshot() == second.initial
    assert second.session.staged_patch is None
    assert len(calls) == 4
    exported = service.audit_report(first)
    exported['events'][0]['after']['stored_total_cents'] = 0
    assert first.events[0]['after']['stored_total_cents'] == first.initial['stored_total_cents']


def test_integrity_failure_blocks_execution_and_approval(monkeypatch):
    ticket = new()

    def tampered():
        raise RuntimeError('Protected FlowOps source or evidence differs; execution blocked.')

    # Only this failure-path test substitutes the integrity guard. No file or pin is altered.
    monkeypatch.setattr(service, 'verify_integrity', tampered)
    with pytest.raises(RuntimeError, match='Protected'):
        new()
    with pytest.raises(RuntimeError, match='Protected'):
        service.advance(ticket)
    with pytest.raises(RuntimeError, match='Protected'):
        service.approve(ticket, confirmed=True)
    assert ticket.events == [] and ticket.attempts == 0
    monkeypatch.undo()
