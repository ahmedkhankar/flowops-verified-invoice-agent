"""Native runner tests use synthetic HTTP exclusively, never real inference."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from urllib import error

import pytest

from flowops import evaluation
from flowops.invoices import invoice_case
from flowops.engine import WorkflowSession
from flowops.models import Decision
from flowops.planner import RulesPlanner, OllamaPlanner
from flowops.cases import load_cases

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[1]


def runner():
    spec=importlib.util.spec_from_file_location('native_exam_runner',ROOT/'scripts/evaluate_invoice_exam.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_complete_runner_recording_scores_and_exclusive_outputs(tmp_path,monkeypatch):
    mod=runner(); seen=[]
    frozen=tmp_path/'freeze.json'
    frozen.write_text(json.dumps({'files':{},'protocol':{'model':evaluation.MODEL,'model_digest':'offline-fixture'}}))
    def metadata(path):
        return {'models':[{'name':evaluation.MODEL,'digest':'offline-fixture'}]} if path=='/api/tags' else {'version':'offline-fixture'}
    def transport(req,*args,**kwargs):
        payload=json.loads(req.data); seen.append(payload)
        obs=json.loads(payload['messages'][1]['content'])
        action=('close' if obs['verification']['passed'] else 'escalate' if obs['world']['locked'] else
                'deploy' if obs['pending_patch_fields'] else 'stage_invoice_fix')
        return io.BytesIO(json.dumps({'model':evaluation.MODEL,'message':{
            'content':json.dumps({'action':action,'reason':'offline runner fixture'})}}).encode())
    monkeypatch.setattr(mod,'get_json',metadata)
    monkeypatch.setattr(evaluation,'TRANSPORT',transport)
    monkeypatch.setattr(RulesPlanner,'decide',lambda *a:pytest.fail('No model substitution allowed'))
    out=tmp_path/'evidence'
    argv=['--mode','ollama','--freeze-file',str(frozen),'--output',str(out)]
    mod.main(argv)
    summary=json.loads((out/'summary.json').read_text())
    assert summary['passed']==12 and summary['incorrect_invoices_repaired_and_closed']==8
    assert summary['locked_invoices_model_escalated']==summary['correct_invoices_closed_untouched']==2
    assert summary['model_calls']==len(seen)==28
    assert summary['invalid_closures']==summary['runtime_enforced_stops']==summary['failed_tool_calls']==0
    assert len(list(out.glob('bill*.json')))==12
    for path in out.glob('bill*.json'):
        record=json.loads(path.read_text())
        assert record['verification_fresh']==record['report']['verification']
        for step in record['trace']:
            assert 'request' in step and 'response' in step and 'state_after' in step
            assert 'tool_result' in step and 'verification_after' in step
    before={p.name:p.read_bytes() for p in out.iterdir()}
    with pytest.raises(FileExistsError): mod.main(argv)
    assert before=={p.name:p.read_bytes() for p in out.iterdir()}


def test_runner_rejects_tampering_before_inference_or_outputs(tmp_path,monkeypatch):
    mod=runner(); frozen=tmp_path/'freeze.json'
    frozen.write_text(json.dumps({'files':{'versions/invoice-v2/flowops/engine.py':'wrong-hash'}}))
    monkeypatch.setattr(mod,'get_json',lambda *a:pytest.fail('Network before hash verification'))
    with pytest.raises(RuntimeError,match='Hash mismatch'):
        mod.main(['--mode','ollama','--freeze-file',str(frozen),'--output',str(tmp_path/'never')])
    assert not (tmp_path/'never').exists()


def test_native_json_case_loader(tmp_path):
    raw=json.loads((PROJECT/'external_exam_kit/exam.json').read_text())[0]
    case=invoice_case(raw)
    p=tmp_path/'cases.json'
    p.write_text(json.dumps([{'case_id':case.case_id,'title':case.title,'request':case.request,
                             'risk':'low','initial_bill':case.initial_bill}]))
    loaded=load_cases(p)
    assert loaded[case.case_id].initial_bill['line_items'][0]['quantity']==1
    assert WorkflowSession(loaded[case.case_id]).run(RulesPlanner())['status']=='CLOSED_VERIFIED'


@pytest.mark.parametrize('action',['stage_invoice_fix','deploy'])
def test_known_lock_invalid_action_gets_business_feedback_not_python_error(action):
    raw=json.loads((PROJECT/'external_exam_kit/exam.json').read_text())[8]
    s=WorkflowSession(invoice_case(raw)); before=s.bill.snapshot()
    selected=type('Selected',(),{'decide':lambda self,obs:Decision(action)})()
    result=s.step(selected)
    assert result['action']=='business_refused' and result['code']=='invoice_locked'
    assert s.status=='ACTIVE' and s.bill.snapshot()==before
    assert s._active_capability is None


def test_provider_failure_is_runtime_failure_never_fallback(monkeypatch):
    def fail(*args,**kwargs): raise error.URLError('offline fixture')
    monkeypatch.setattr(evaluation,'TRANSPORT',fail)
    monkeypatch.setattr(RulesPlanner,'decide',lambda *a:pytest.fail('Fallback forbidden'))
    raw=json.loads((PROJECT/'external_exam_kit/exam.json').read_text())[0]
    row=evaluation.evaluate(raw,invoice_case(raw),OllamaPlanner(model=evaluation.MODEL))
    assert not row['passed'] and row['runtime_enforced_stop']
    assert not row['model_selected_escalation']
    assert row['trace'][0]['decision_error']
    assert row['final_state']==row['initial_state']
