"""Widget journeys: explicit rules or mocked Qwen, never unmocked inference."""
from pathlib import Path
import sys
import pytest
from streamlit.testing.v1 import AppTest

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI))
import service


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def reject(*a, **kw):
        raise AssertionError('UI software tests must not call a real runtime')
    monkeypatch.setattr(service.request, 'urlopen', reject)


def app():
    a = AppTest.from_file(str(UI / 'app.py'), default_timeout=20).run()
    assert not a.exception
    return a


def button(a, text):
    return next(b for b in a.button if b.label == text)


def checkbox(a, text):
    return next(b for b in a.checkbox if b.label == text)


def create(a, scenario='repair', mode='RULES BASELINE'):
    a.sidebar.radio[0].set_value('Create ticket').run()
    a.selectbox[0].set_value(scenario).run()
    next(s for s in a.selectbox if s.label == 'Execution source').set_value(mode)
    checkbox(a, 'This ticket contains synthetic information only.').check()
    button(a, 'Create Ticket').click().run()
    assert not a.exception
    return a.session_state['tickets'][a.session_state['active_ticket']]


def test_empty_state_and_create_ticket_navigation_no_inference():
    a=app()
    assert 'No billing tickets yet' in '\n'.join(m.value for m in a.markdown)
    assert all('guide' not in b.label.lower() for b in a.button)
    button(a,'＋ Create New Ticket').click().run()
    assert not a.exception and a.title[0].value=='Create a billing ticket'
    assert not a.session_state['tickets']


@pytest.mark.parametrize('page,title', [
    ('Overview','Merchant Operations'),
    ('Create ticket','Create a billing ticket'),
    ('Ticket workspace','Ticket workspace'),
    ('Evaluation evidence','Evaluation Evidence'),
])
def test_remaining_pages_have_no_guide_links(page, title):
    a=app()
    assert a.sidebar.radio[0].options==[
        'Overview','Create ticket','Ticket workspace','Evaluation evidence',
    ]
    a.sidebar.radio[0].set_value(page).run()
    assert not a.exception and a.title[0].value==title
    assert all('guide' not in b.label.lower() for b in a.button)
    assert not any('three-minute demo' in t.value for t in a.title)
    assert not a.session_state['tickets']


@pytest.mark.parametrize('state_key', ['page','_next_page'])
def test_retired_page_state_returns_to_overview(state_key):
    a=AppTest.from_file(str(UI / 'app.py'), default_timeout=20)
    a.session_state[state_key]='Demo guide'
    a.run()
    assert not a.exception and a.title[0].value=='Merchant Operations'
    assert a.sidebar.radio[0].value=='Overview'
    assert not a.session_state['tickets']


def test_form_requires_synthetic_confirmation():
    a=app()
    a.sidebar.radio[0].set_value('Create ticket').run()
    button(a,'Create Ticket').click().run()
    assert a.error and not a.session_state['tickets']


def test_rules_full_journey_comparison_and_audit():
    a=app(); ticket=create(a)
    assert ticket.status=='New' and ticket.mode=='RULES BASELINE'
    assert ticket.complaint in ticket.last_observation['objective']
    button(a,'Step Through').click().run()
    assert not a.exception
    assert ticket.session.staged_patch and ticket.initial==ticket.session.bill.snapshot()
    button(a,'Run Agent').click().run()
    assert not a.exception and ticket.status=='Resolved'
    assert any(e['changed'] for e in ticket.events)
    assert ticket.session.verification.passed
    assert len(a.get('download_button'))==1


def test_locked_ticket_and_new_scenario_do_not_share_state():
    a=app(); first=create(a,'locked')
    button(a,'Run Agent').click().run()
    assert not a.exception and first.status=='Escalated'
    assert first.session.bill.snapshot()==first.initial
    button(a,'Create another ticket').click().run()
    a.selectbox[0].set_value('correct').run()
    next(s for s in a.selectbox if s.label=='Execution source').set_value('RULES BASELINE')
    checkbox(a,'This ticket contains synthetic information only.').check()
    button(a,'Create Ticket').click().run()
    second=a.session_state['tickets'][a.session_state['active_ticket']]
    assert second.ticket_id!=first.ticket_id and not second.events
    assert second.session.bill.stored_total_cents==2300
    assert first.status=='Escalated'


def test_live_enable_and_failed_model_are_honest():
    a=app(); ticket=create(a,mode='LIVE MODEL')
    assert button(a,'Run Agent').disabled
    checkbox(a,'Enable real local Qwen execution for this ticket').check().run()
    button(a,'Step Through').click().run()
    assert not a.exception
    assert ticket.status=='Incomplete' and ticket.session.step_count==0
    assert ticket.events[-1]['action'] is None
    assert ticket.events[-1]['changed'] is False
    assert button(a,'Run Agent').disabled


def test_saved_evidence_does_not_create_or_modify_ticket():
    a=app(); ticket=create(a)
    snapshot=ticket.session.bill.snapshot()
    a.sidebar.radio[0].set_value('Evaluation evidence').run()
    assert not a.exception
    assert not ticket.events and ticket.session.bill.snapshot()==snapshot
    assert any('SAVED REPLAY' in m.value for m in a.markdown)
    text='\n'.join(m.value for m in a.markdown)
    assert all(case_id in text for case_id in ['h_001','h_013','h_019'])


def test_invalid_amount_is_rejected_by_form():
    a=app(); a.sidebar.radio[0].set_value('Create ticket').run()
    next(t for t in a.text_input if t.label=='Currently stored total (SAR)').set_value('12.345')
    checkbox(a,'This ticket contains synthetic information only.').check()
    button(a,'Create Ticket').click().run()
    assert a.error and not a.session_state['tickets']
