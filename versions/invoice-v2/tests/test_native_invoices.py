"""Native Invoice v2 tests. Scripted model responses are not live model results."""
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path

import pytest

from flowops.cases import load_cases
from flowops.engine import WorkflowSession, AuthorizationError, _ExecutionCapability
from flowops.invoices import invoice_case
from flowops.models import AcceptanceSpec, Decision, InvoiceLine, InvoiceState
from flowops.planner import RulesPlanner, OllamaPlanner
from flowops.verifier import check_state
from flowops import evaluation

PROJECT = Path(__file__).resolve().parents[3]
EXAM = json.loads((PROJECT/'external_exam_kit/exam.json').read_text())
TOTALS = [11,1162,2875,3192,3995,4125,4337,6897,2875,2100,1725,32]


def session(index=0, **changes):
    record = deepcopy(EXAM[index])
    record.update(changes)
    return WorkflowSession(invoice_case(record))


@pytest.mark.parametrize('index,total', list(enumerate(TOTALS)))
def test_native_quantities_vat_and_external_rules_compatibility(index, total):
    record = EXAM[index]
    case = invoice_case(record)
    s = WorkflowSession(case)
    assert isinstance(s.bill, InvoiceState)
    assert [(l.unit_price_cents, l.quantity) for l in s.bill.line_items] == [
        (int(__import__('decimal').Decimal(p)*100),q) for p,q in record['items']]
    assert 'item_cents' not in s.bill.snapshot()  # no competing persisted totals
    assert s.bill.split_cents is None
    assert 'split_sum' not in s.verification.checks
    result = evaluation.evaluate(record, case, RulesPlanner())
    assert result['passed']
    assert result['correct_total_cents'] == total
    assert not result['failed_tool_calls']
    if record['locked']:
        assert result['planner_selected_escalation']
        assert not result['model_selected_escalation']  # rules are never model decisions
        assert result['final_state'] == result['initial_state']
    else:
        assert result['final_state']['stored_total_cents'] == total


@pytest.mark.parametrize('change', [
    {'tax': '0.00001'}, {'tax':'NaN'}, {'total':'0.001'}, {'total':'Infinity'},
    {'items':[['1.00',True]]}, {'items':[['1.00',1.2]]}, {'items':[['-1.00',1]]},
    {'locked':'false'}, {'items':[['1.00',0]]}, {'tax':'1.01'},
])
def test_exact_intake_rejects_silent_coercion(change):
    record=deepcopy(EXAM[0]); record.update(change)
    with pytest.raises(ValueError): invoice_case(record)


def test_native_split_checks_cannot_be_disabled():
    s=session(10)
    s.bill.split_cents=[1,1]
    result=check_state(s.bill,AcceptanceSpec(False,False,False))
    assert not result.passed
    assert result.checks['invoice_total']
    assert not result.checks['split_sum']
    assert 'service_ready' in result.checks
    # A genuine native split repairs through the same staged deployment tools.
    case=replace(s.case,initial_bill=s.bill.snapshot())
    assert WorkflowSession(case).run(RulesPlanner())['status']=='CLOSED_VERIFIED'


def test_no_change_closure_and_fresh_verification():
    s=session(11); before=s.bill.snapshot()
    assert s.act(Decision('close'))['verification']['passed']
    assert s.bill.snapshot()==before and s.deploy_attempts==0
    other=session(11); other.bill.stored_total_cents=31
    with pytest.raises(AuthorizationError): other.act(Decision('close'))
    assert not other.verification.passed


def test_already_correct_locked_invoice_can_close_read_only():
    s=session(11,locked=True); before=s.bill.snapshot()
    assert s.run(RulesPlanner())['status']=='CLOSED_VERIFIED'
    assert s.bill.snapshot()==before and s.deploy_attempts==0


def test_backend_lock_after_staging_consumes_capability_and_returns_structured_refusal(monkeypatch):
    s=session(); s.act(Decision('stage_invoice_fix')); s.bill.locked=True
    before=s.bill.snapshot(); original=s._trusted_deployment_service; seen=[]
    def capture(patch,*,capability):
        seen.append(capability)
        return original(patch,capability=capability)
    monkeypatch.setattr(s,'_trusted_deployment_service',capture)
    result=s.act(Decision('deploy'))  # intentionally bypass availability: backend must protect
    assert result['action']=='business_refused' and result['code']=='invoice_locked'
    assert result['ok'] is False and s.status=='ACTIVE'
    assert s.bill.snapshot()==before and s._active_capability is None
    assert s.deploy_attempts==1
    with pytest.raises(AuthorizationError): original(s.staged_patch,capability=seen[0])
    assert s.history[-1]['action']=='business_refused'
    assert s.step(RulesPlanner())['action']=='escalate'


@pytest.mark.parametrize('capability',[None,_ExecutionCapability('forged','deploy')])
def test_native_missing_and_forged_capabilities(capability):
    s=session(); before=s.bill.snapshot()
    with pytest.raises(AuthorizationError):
        s._trusted_deployment_service({'stored_total_cents':11},capability=capability)
    assert s.bill.snapshot()==before


def test_native_stale_and_cross_session_capability(monkeypatch):
    s=session(); other=session(); original=s._trusted_deployment_service; seen=[]
    def capture(patch,*,capability):
        if seen:
            with pytest.raises(AuthorizationError): original(patch,capability=seen[0])
        seen.append(capability)
        return original(patch,capability=capability)
    monkeypatch.setattr(s,'_trusted_deployment_service',capture)
    for _ in range(2):
        s.act(Decision('stage_invoice_fix')); s.act(Decision('deploy'))
    with pytest.raises(AuthorizationError): other._trusted_deployment_service({'stored_total_cents':11},capability=seen[-1])


def test_approval_cannot_override_business_lock():
    s=WorkflowSession(replace(session(8).case,risk='high'))
    assert s.run(RulesPlanner())['status']=='PAUSED_APPROVAL'
    assert not s.planner_decisions
    s.grant_human_approval('simulated-human')
    s.staged_patch={'stored_total_cents':2875}
    before=s.bill.snapshot()
    assert s.act(Decision('deploy'))['code']=='invoice_locked'
    assert s.bill.snapshot()==before


@pytest.mark.parametrize('patch',[{'locked':False},{'tax_bps':0},{'line_items':[]},{'split_cents':[5,6]}])
def test_invoice_cannot_patch_immutable_facts_or_invent_splits(patch):
    s=session(); before=s.bill.snapshot(); s.staged_patch=patch
    with pytest.raises(AuthorizationError): s.act(Decision('deploy'))
    assert s.bill.snapshot()==before and s._active_capability is None


def test_native_false_fix_remains_unverified_and_cannot_close():
    s=WorkflowSession(replace(session().case,simulated_noop_deploy=True))
    assert s.run(RulesPlanner())['status']=='ESCALATED'
    assert s.bill.version==0 and not s.verification.passed
    assert s.deploy_attempts==2
    assert not any(e['action']=='close' for e in s.history)


@pytest.mark.parametrize('after_write',[False,True])
def test_native_failed_deployment_revokes_even_after_partial_write(monkeypatch,after_write):
    s=session(); s.act(Decision('stage_invoice_fix')); original=s._trusted_deployment_service
    def fail(patch,*,capability):
        if after_write: original(patch,capability=capability)
        raise RuntimeError('injected native failure')
    monkeypatch.setattr(s,'_trusted_deployment_service',fail)
    assert s.step(RulesPlanner())['action']=='tool_failed'
    assert s.status=='ESCALATED' and s._active_capability is None
    assert s.verification.passed is after_write


def scripted(monkeypatch,actions):
    actions=iter(actions); captured=[]
    def transport(req,*args,**kwargs):
        payload=json.loads(req.data); captured.append(payload)
        answer={'model':evaluation.MODEL,'message':{'content':json.dumps({'action':next(actions),'reason':'offline fixture'})}}
        return io.BytesIO(json.dumps(answer).encode())
    monkeypatch.setattr(evaluation,'TRANSPORT',transport)
    monkeypatch.setattr(RulesPlanner,'decide',lambda *a:pytest.fail('Rules fallback forbidden'))
    return OllamaPlanner(model=evaluation.MODEL),captured


def test_full_model_recording_label_privacy_and_real_tool_corrections(monkeypatch):
    record=deepcopy(EXAM[0]); record['want']='PRIVATE_ANSWER_CANARY'
    case=invoice_case(record)
    record['want']='fix'  # only evaluator sees the actual answer
    planner,requests=scripted(monkeypatch,['inspect','stage_invoice_fix','deploy','verify','close'])
    row=evaluation.evaluate(record,case,planner)
    assert row['passed'] and row['final_state']['stored_total_cents']==11
    assert len(row['trace'])==len(requests)==5
    assert 'PRIVATE_ANSWER_CANARY' not in json.dumps(requests)
    for payload,step in zip(requests,row['trace']):
        observation=json.loads(payload['messages'][1]['content'])
        assert not any(key in observation for key in ['want','correct_total_cents','acceptance'])
        assert payload['think'] is False and payload['options']['temperature']==0
        assert 'tool_result' in step and 'state_after' in step and 'verification_after' in step
    assert all(d['executed_source']=='ollama:'+evaluation.MODEL for d in row['report']['planner_decisions'])


def test_known_lock_model_can_select_escalation_without_attempting_write(monkeypatch):
    planner,requests=scripted(monkeypatch,['escalate'])
    row=evaluation.evaluate(EXAM[8],invoice_case(EXAM[8]),planner)
    assert row['passed'] and row['model_selected_escalation'] and not row['runtime_enforced_stop']
    obs=json.loads(requests[0]['messages'][1]['content'])
    assert obs['world']['locked']
    assert not {'stage_invoice_fix','deploy'} & set(obs['allowed_actions'])
    assert row['final_state']==row['initial_state'] and row['report']['deploy_attempts']==0


def test_runtime_stall_is_not_model_escalation(monkeypatch):
    planner,_=scripted(monkeypatch,['inspect']*12)
    row=evaluation.evaluate(EXAM[8],invoice_case(EXAM[8]),planner)
    assert not row['passed'] and row['runtime_enforced_stop']
    assert not row['model_selected_escalation'] and row['rejected_tool_calls']==11


def test_original_six_diagnostics_keep_outcomes():
    expected={'split_bill':'CLOSED_VERIFIED','wrong_total_and_split':'CLOSED_VERIFIED',
              'security_approval':'PAUSED_APPROVAL','fake_fix':'ESCALATED',
              'outage':'ESCALATED','rounding':'CLOSED_VERIFIED'}
    for cid,case in load_cases().items():
        s=WorkflowSession(case); report=s.run(RulesPlanner())
        assert report['status']==expected[cid]
        assert not any(e['action']=='tool_failed' for e in report['audit_trail'])
