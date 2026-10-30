"""Exercise the retained dashboard without starting a server or calling an API."""
from pathlib import Path
import pytest

pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def click(app, label):
    next(b for b in app.button if b.label == label).click().run()
    assert not app.exception


def test_dashboard_split_bill_runs_to_verified_outcome():
    app = AppTest.from_file(APP, default_timeout=20).run()
    assert not app.exception
    assert app.session_state['flow_session'].status == 'ACTIVE'
    click(app, 'Run to outcome')
    s = app.session_state['flow_session']
    assert s.status == 'CLOSED_VERIFIED'
    assert s.bill.split_cents == [550, 550]
    assert s._active_capability is None


def test_dashboard_approval_is_explicit():
    app = AppTest.from_file(APP, default_timeout=20).run()
    app.selectbox[0].select('security_approval').run()
    assert not app.exception
    assert app.session_state['flow_session'].status == 'PAUSED_APPROVAL'
    assert app.session_state['flow_session'].deploy_attempts == 0
    click(app, 'Record human approval')
    click(app, 'Run to outcome')
    assert app.session_state['flow_session'].status == 'CLOSED_VERIFIED'


def test_dashboard_exposes_hosted_mode_without_network(monkeypatch):
    monkeypatch.setenv('FLOWOPS_LLM_MODEL', 'test-model')
    app = AppTest.from_file(APP, default_timeout=20).run()
    app.radio[0].set_value('Hosted LLM API').run()
    assert not app.exception
    assert any(t.label == 'Hosted API base URL' for t in app.text_input)
    assert not app.checkbox[0].value
    assert app.session_state['flow_session'].step_count == 0


def test_dashboard_verifier_failure_escalates_without_stale_pass(monkeypatch):
    app = AppTest.from_file(APP, default_timeout=20).run()
    click(app, 'Run to outcome')
    assert app.session_state['flow_session'].verification.passed

    def fail(*a, **k):
        raise RuntimeError('injected verifier outage')

    monkeypatch.setattr('flowops.engine.check_state', fail)
    app.run()
    assert not app.exception
    assert app.session_state['flow_session'].status == 'ESCALATED'
    assert not app.session_state['flow_session'].verification.passed
    assert next(m for m in app.metric if m.label == 'Independent verification').value == 'FAIL'
