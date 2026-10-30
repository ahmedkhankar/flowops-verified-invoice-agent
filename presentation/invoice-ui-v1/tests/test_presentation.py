"""Presentation regressions. All provider fixtures are OFFLINE, never model evidence."""
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest
import ui_core as core
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


@pytest.fixture(autouse=True)
def offline_and_preserved(monkeypatch):
    verify = core.verify_integrity
    verify()
    def forbidden(*args, **kwargs):
        raise AssertionError('Unmocked network prohibited in presentation tests')
    monkeypatch.setattr(core.evaluation, 'TRANSPORT', forbidden)
    monkeypatch.setattr(core.evaluation.request, 'urlopen', forbidden)
    yield
    verify()


def widget(items, label):
    return next(x for x in items if x.label == label)


def click(app, label):
    widget(app.button, label).click().run()
    assert not app.exception


def app_start():
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception
    return app


def fake_ai(monkeypatch, actions):
    choices = iter(actions)
    sent = []
    def transport(req, *args, **kwargs):
        payload = json.loads(req.data)
        sent.append(payload)
        return io.BytesIO(json.dumps({'model': core.MODEL, 'done': True,
                                     'message': {'content': json.dumps({'action': next(choices), 'reason': 'offline presentation fixture'})}}).encode())
    monkeypatch.setattr(core.evaluation, 'TRANSPORT', transport)
    monkeypatch.setattr(core.planner.RulesPlanner, 'decide', lambda *a: pytest.fail('Rules substitution forbidden'))
    return sent


def test_default_replay_never_constructs_live_model(monkeypatch):
    monkeypatch.setattr(core.planner.OllamaPlanner, '__init__', lambda *a, **k: pytest.fail('Replay constructed a model'))
    app = app_start()
    assert widget(app.radio, 'Mode').value == 'Saved Qwen replay'
    assert app.session_state['replay_position'] == 0
    assert any(m.label == 'Correct outcomes' and m.value == '10/12' for m in app.metric)
    assert not any(b.label == 'Execute next AI step' for b in app.button)


def test_replay_stage_is_not_a_persisted_write():
    app = app_start()
    click(app, 'Next recorded step')
    click(app, 'Next recorded step')
    assert app.session_state['replay_position'] == 2
    assert any('STAGED ONLY' in w.value for w in app.warning)
    assert any(m.label == 'Stored total' and m.value == '35.00' for m in app.metric)
    click(app, 'Next recorded step')
    assert any(m.label == 'Stored total' and m.value == '31.92' for m in app.metric)
    click(app, 'Show final outcome')
    assert any(m.label == 'Ticket state' and m.value == 'CLOSED_VERIFIED' for m in app.metric)


@pytest.mark.parametrize('name,status', [('bill09', 'ESCALATED'), ('bill11', 'PAUSED_APPROVAL')])
def test_replay_keeps_lock_and_failure_outcomes(name, status):
    app = app_start()
    widget(app.selectbox, 'Saved invoice scenario').select(name).run()
    click(app, 'Show final outcome')
    assert any(m.label == 'Ticket state' and m.value == status for m in app.metric)
    if name == 'bill09':
        assert any(m.label == 'Merchant lock' and m.value == 'LOCKED' for m in app.metric)
    else:
        assert any('failed its expected outcome' in e.value for e in app.error)
    assert not any(b.label == 'Record simulated human approval' for b in app.button)
    widget(app.selectbox, 'Saved invoice scenario').select('bill04').run()
    assert app.session_state['replay_position'] == 0


def test_recorded_view_never_executes_engine(monkeypatch):
    record = core.saved_case('bill04'); original = deepcopy(record)
    monkeypatch.setattr(core.engine.WorkflowSession, 'step', lambda *a: pytest.fail('Replay executed tool'))
    assert core.recorded_view(record, 2)['state']['stored_total_cents'] == 3500
    assert core.recorded_view(record, 2)['pending'] == {'stored_total_cents': 3192}
    assert core.recorded_view(record, 5)['state']['stored_total_cents'] == 3192
    assert record == original


def test_native_live_pipeline_real_engine_and_private_labels(monkeypatch):
    sent = fake_ai(monkeypatch, ['inspect', 'stage_invoice_fix', 'deploy', 'verify', 'close'])
    ticket = core.LiveTicket(core.seed_cases()['bill04'])
    assert type(ticket.session.bill).__name__ == 'InvoiceState'
    ticket.step(); ticket.step()
    assert ticket.session.bill.stored_total_cents == 3500
    assert ticket.session.staged_patch == {'stored_total_cents': 3192}
    ticket.step()
    assert ticket.session.bill.stored_total_cents == 3192 and ticket.session.bill.version == 1
    ticket.run()
    assert ticket.session.status == 'CLOSED_VERIFIED'
    assert len(sent) == 5
    for body in sent:
        assert body['model'] == core.MODEL and body['think'] is False and body['options']['temperature'] == 0
        assert '"want":' not in body['messages'][1]['content']
        assert '"correct_total_cents":' not in body['messages'][1]['content']
    exported = ticket.export()
    assert exported['mode'] == 'live_ai' and exported['rules_fallback'] is False
    assert len(exported['trace']) == 5
    assert all('request' in s and 'response' in s and 'tool_result' in s and 'state_after' in s for s in exported['trace'])
    assert all(x['executed_source'] == 'ollama:' + core.MODEL for x in exported['report']['planner_decisions'])


def test_live_model_selected_escalation_is_not_runtime(monkeypatch):
    fake_ai(monkeypatch, ['escalate'])
    ticket = core.LiveTicket(core.seed_cases()['bill09']); before = ticket.session.bill.snapshot()
    ticket.step()
    assert core.disposition(ticket.session.report()) == 'Model-selected escalation'
    assert ticket.session.bill.snapshot() == before


def test_provider_failure_has_no_fallback_or_false_escalation(monkeypatch):
    def fail(*args, **kwargs): raise URLError('offline provider failure')
    monkeypatch.setattr(core.evaluation, 'TRANSPORT', fail)
    monkeypatch.setattr(core.planner.RulesPlanner, 'decide', lambda *a: pytest.fail('No fallback'))
    ticket = core.LiveTicket(core.seed_cases()['bill04']); ticket.run()
    assert core.disposition(ticket.session.report()) == 'Runtime-enforced stop'
    assert ticket.session.bill.version == 0
    assert ticket.export()['trace'][0]['decision_error']


def test_total_budget_cannot_be_extended_by_step_buttons(monkeypatch):
    sent = fake_ai(monkeypatch, ['inspect'] * 12)
    ticket = core.LiveTicket(core.seed_cases()['bill09'])
    for _ in range(15): ticket.step()
    assert len(sent) == 12 and ticket.session.step_count == 12
    assert core.disposition(ticket.session.report()) == 'Runtime-enforced stop'


def test_human_approval_uses_native_gate_and_cannot_unlock(monkeypatch):
    sent = fake_ai(monkeypatch, ['escalate'])
    ticket = core.LiveTicket(replace(core.seed_cases()['bill09'], risk='high'))
    ticket.step(); assert not sent
    assert core.disposition(ticket.session.report()) == 'Policy-required human approval'
    with pytest.raises(ValueError): ticket.approve(' ')
    ticket.approve('Simulated reviewer')
    assert ticket.session.bill.locked
    ticket.step()
    assert core.disposition(ticket.session.report()) == 'Model-selected escalation'
    assert ticket.session.bill.locked and ticket.session.bill.version == 0


def test_no_change_closure_supported_without_rewriting_recorded_failures(monkeypatch):
    fake_ai(monkeypatch, ['close'])
    ticket = core.LiveTicket(core.seed_cases()['bill11']); before = ticket.session.bill.snapshot()
    ticket.step()
    assert ticket.session.status == 'CLOSED_VERIFIED' and ticket.session.bill.snapshot() == before
    summary, records = core.recorded_evaluation()
    assert summary['passed'] == 10 and summary['correct_invoices_closed_untouched'] == 0
    assert not next(r for r in records if r['case_id'] == 'bill11')['passed']


def test_verifier_outage_invalidates_pass_without_crashing_ui(monkeypatch):
    ticket = core.LiveTicket(core.seed_cases()['bill11'])
    assert ticket.session.verification.passed
    def fail(*a): raise RuntimeError('verifier unavailable')
    monkeypatch.setattr(core.engine, 'check_state', fail)
    assert ticket.observe() is None
    assert not ticket.session.verification.passed and ticket.session.status == 'ESCALATED'


def test_live_ui_explicit_enable_and_native_execution(monkeypatch):
    sent = fake_ai(monkeypatch, ['inspect', 'stage_invoice_fix', 'deploy', 'verify', 'close'])
    app = app_start()
    widget(app.radio, 'Mode').set_value('Live Qwen execution').run()
    click(app, 'Create live ticket')
    assert not sent
    assert widget(app.button, 'Execute next AI step').disabled
    widget(app.checkbox, 'Enable new local Qwen calls').check().run()
    click(app, 'Execute next AI step')
    assert len(sent) == 1
    click(app, 'Run AI to outcome (12-step total limit)')
    assert app.session_state['live_ticket'].session.status == 'CLOSED_VERIFIED'
    assert len(sent) == 5
    assert any(m.label == 'Correct outcomes' and m.value == '10/12' for m in app.metric)
    widget(app.radio, 'Mode').set_value('Saved Qwen replay').run()
    assert not any(b.label == 'Execute next AI step' for b in app.button)


@pytest.mark.parametrize('kwargs', [{'issue': ''}, {'rows': []}, {'rows': [{'Unit price': '1.00', 'Quantity': 1.2}]}, {'vat': '0.00001'}])
def test_custom_intake_validation_is_native(kwargs):
    args = {'issue': 'Investigate invoice', 'rows': [{'Unit price': '1.00', 'Quantity': 2}],
            'vat': '0.05', 'total': '2.00', 'locked': False}
    args.update(kwargs)
    with pytest.raises(ValueError): core.custom_case(**args)


def test_custom_native_ui_intake_and_model_requested_approval(monkeypatch):
    sent = fake_ai(monkeypatch, ['request_approval'])
    app = app_start()
    widget(app.radio, 'Mode').set_value('Live Qwen execution').run()
    widget(app.radio, 'Merchant issue intake').set_value('New merchant invoice').run()
    click(app, 'Create native invoice ticket')
    assert app.session_state['live_ticket'].session.bill.line_items[0].quantity == 3
    assert not sent
    widget(app.checkbox, 'Enable new local Qwen calls').check().run()
    click(app, 'Execute next AI step')
    assert core.disposition(app.session_state['live_ticket'].session.report()) == 'Model-requested human approval'
    assert any(b.label == 'Record simulated human approval' for b in app.button)


def test_human_approval_ui_requires_confirmation_and_identity(monkeypatch):
    sent = fake_ai(monkeypatch, [])
    app = app_start()
    widget(app.radio, 'Mode').set_value('Live Qwen execution').run()
    widget(app.selectbox, 'Invoice or split-bill scenario').select('legacy:security_approval').run()
    click(app, 'Create live ticket')
    ticket = app.session_state['live_ticket']
    assert ticket.session.status == 'PAUSED_APPROVAL' and not sent
    click(app, 'Record simulated human approval')
    assert ticket.session.approved_by is None
    widget(app.checkbox, 'I am recording a human decision, not an AI-granted approval').check()
    click(app, 'Record simulated human approval')
    assert ticket.session.approved_by is None
    widget(app.checkbox, 'I am recording a human decision, not an AI-granted approval').check()
    widget(app.text_input, 'Reviewer identity (simulation only)').set_value('Demo reviewer')
    click(app, 'Record simulated human approval')
    assert ticket.session.status == 'ACTIVE' and ticket.session.approved_by == 'Demo reviewer'
    assert not sent


def test_split_workflow_remains_available(monkeypatch):
    fake_ai(monkeypatch, ['stage_split_fix', 'deploy', 'close'])
    ticket = core.LiveTicket(core.seed_cases()['legacy:split_bill']); ticket.run()
    assert ticket.session.status == 'CLOSED_VERIFIED' and ticket.session.bill.split_cents == [550, 550]


def test_integrity_error_blocks_entire_ui(monkeypatch):
    def fail(): raise RuntimeError('Hash mismatch fixture')
    monkeypatch.setattr(core, 'verify_integrity', fail)
    app = app_start()
    assert any('Execution disabled' in e.value for e in app.error)
    assert not any(b.label == 'Execute next AI step' for b in app.button)


def test_core_import_identity_and_saved_case_allowlist():
    assert Path(core.engine.__file__).resolve().parent == core.NATIVE / 'flowops'
    with pytest.raises(ValueError): core.saved_case('../metadata')
    assert core.money(3192) == '31.92'
