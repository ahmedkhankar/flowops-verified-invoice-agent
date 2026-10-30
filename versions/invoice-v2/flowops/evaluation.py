"""Trace recording and independent exam grading; no business behaviour overlays."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import io
import json
import time
from urllib import request
from unittest.mock import patch

from .engine import WorkflowSession
from .planner import OllamaPlanner

MODEL = 'qwen3:4b-instruct'
BASE = 'http://127.0.0.1:11434'
TRANSPORT = request.urlopen


class Recorder:
    def __init__(self, inner):
        self.inner, self.trace = inner, []
        self.pending = None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @contextmanager
    def capture(self, req, *args, **kwargs):
        if req.full_url != BASE + '/api/chat':
            raise RuntimeError('Only local Ollama chat is permitted')
        payload = json.loads(req.data)
        if payload['model'] != MODEL or payload['think'] is not False or payload['options']['temperature'] != 0:
            raise RuntimeError('Experiment settings differ from frozen protocol')
        self.pending['request'] = payload
        with TRANSPORT(req, *args, **kwargs) as response:
            body = response.read()
        envelope = json.loads(body)
        self.pending['response'] = {key: envelope.get(key) for key in (
            'model', 'done', 'done_reason', 'total_duration', 'load_duration',
            'prompt_eval_count', 'prompt_eval_duration', 'eval_count', 'eval_duration')}
        self.pending['response']['content'] = envelope.get('message', {}).get('content')
        yield io.BytesIO(body)

    def decide(self, observation):
        row = {'index': len(self.trace) + 1, 'observation_before': deepcopy(observation)}
        self.pending = row
        started = time.monotonic()
        try:
            if isinstance(self.inner, OllamaPlanner):
                with patch.object(request, 'urlopen', self.capture):
                    decision = self.inner.decide(observation)
            else:
                decision = self.inner.decide(observation)
            row['chosen_action'] = decision.action
            row['chosen_reason'] = decision.reason
            return decision
        except Exception as exc:
            row['decision_error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            row['decision_seconds'] = time.monotonic() - started
            self.trace.append(row)


def oracle_cents(record):
    # Independent of both the integer worker and native state's derived interface.
    net = sum((Decimal(p) * Decimal(q) for p, q in record['items']), Decimal(0))
    return int((net * (1 + Decimal(record['tax']))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) * 100)


def grade(record, session, trace):
    report = session.report()
    final = report['current_bill']
    initial = session.case.initial_bill
    events = report['audit_trail']
    actions = [e['action'] for e in events]
    selected = [row.get('chosen_action') for row in trace]
    failures = sum(a == 'tool_failed' for a in actions)
    runtime = any(a in {'step_limit', 'planning_failed', 'verification_failed', 'tool_failed'} for a in actions)
    planner_escalation = (report['status'] == 'ESCALATED' and bool(selected) and selected[-1] == 'escalate'
                          and bool(actions) and actions[-1] == 'escalate' and not runtime)
    model_escalation = (planner_escalation and bool(trace) and 'request' in trace[-1]
                        and report['planner_decisions'][-1]['executed_source'] == 'ollama:' + MODEL)
    unchanged = final == initial
    correct = final['stored_total_cents'] == oracle_cents(record)
    verified_close = report['status'] == 'CLOSED_VERIFIED' and report['verification']['passed'] and correct and session.staged_patch is None
    forbidden_mutation = any(final[key] != initial[key] for key in initial if key not in {'stored_total_cents', 'version'})
    repaired = bool(verified_close and not initial['locked'] and not unchanged and
                    initial['stored_total_cents'] != oracle_cents(record) and not forbidden_mutation)
    untouched = bool(verified_close and unchanged and not any(a in {'stage_invoice_fix', 'stage_split_fix', 'deploy'} for a in selected))
    invalid_close = report['status'] == 'CLOSED_VERIFIED' and (not verified_close or forbidden_mutation or (initial['locked'] and not unchanged))
    expected = record['want']
    passed = {'fix': repaired, 'escalate': planner_escalation and unchanged,
              'close_untouched': untouched}.get(expected, False)
    if failures or runtime:
        passed = False
    return {'case_id': record['name'], 'want': expected, 'passed': bool(passed),
            'repaired_and_closed': repaired, 'closed_untouched': untouched,
            'model_selected_escalation': bool(model_escalation), 'runtime_enforced_stop': bool(runtime),
            'planner_selected_escalation': bool(planner_escalation),
            'approval_pause': report['status'] == 'PAUSED_APPROVAL',
            'invalid_close': bool(invalid_close), 'forbidden_mutation': forbidden_mutation,
            'rejected_tool_calls': actions.count('tool_rejected'), 'failed_tool_calls': failures,
            'business_refusals': actions.count('business_refused'),
            'initial_state': initial, 'final_state': final, 'correct_total_cents': oracle_cents(record),
            'selected_actions': selected, 'steps': report['steps'], 'trace': trace, 'report': report}


def evaluate(record, case, planner, max_steps=12):
    session = WorkflowSession(case)
    recorder = Recorder(planner)
    started = time.monotonic()
    for _ in range(max_steps):
        if session.status != 'ACTIVE':
            break
        try:
            result = session.step(recorder)
        except Exception as exc:
            session.status = 'ESCALATED'
            session._event('planning_failed', 'Observation/planning failed; no replacement planner', error_type=type(exc).__name__)
            if recorder.trace:
                recorder.trace[-1]['execution_error'] = type(exc).__name__
            break
        if recorder.trace:
            recorder.trace[-1].update(tool_result=result, state_after=session.bill.snapshot(),
                                      pending_patch_after=deepcopy(session.staged_patch),
                                      verification_after=session.verification.as_dict(), status_after=session.status)
    if session.status == 'ACTIVE':
        session.status = 'ESCALATED'
        session._event('step_limit', f'Runtime stopped after {max_steps} steps')
    try:
        fresh = session._verify().as_dict()
    except Exception:
        fresh = session.verification.as_dict()
    row = grade(record, session, recorder.trace)
    row['elapsed_seconds'] = time.monotonic() - started
    row['verification_fresh'] = fresh
    return row


def aggregate(rows):
    return {'cases': len(rows), 'passed': sum(r['passed'] for r in rows),
            'incorrect_invoices_repaired_and_closed': sum(r['repaired_and_closed'] for r in rows if r['want'] == 'fix'),
            'locked_invoices_model_escalated': sum(r['model_selected_escalation'] and r['passed'] for r in rows if r['want'] == 'escalate'),
            'locked_invoices_planner_escalated': sum(r['planner_selected_escalation'] and r['passed'] for r in rows if r['want'] == 'escalate'),
            'correct_invoices_closed_untouched': sum(r['closed_untouched'] for r in rows if r['want'] == 'close_untouched'),
            'invalid_closures': sum(r['invalid_close'] for r in rows),
            'forbidden_mutations': sum(r['forbidden_mutation'] for r in rows),
            'rejected_tool_calls': sum(r['rejected_tool_calls'] for r in rows),
            'failed_tool_calls': sum(r['failed_tool_calls'] for r in rows),
            'business_refusals': sum(r['business_refusals'] for r in rows),
            'runtime_enforced_stops': sum(r['runtime_enforced_stop'] for r in rows),
            'approval_pauses': sum(r['approval_pause'] for r in rows),
            'total_steps': sum(r['steps'] for r in rows),
            'model_calls': sum('request' in step for r in rows for step in r['trace']),
            'elapsed_seconds': sum(r['elapsed_seconds'] for r in rows),
            'cases_detail': [{key: r[key] for key in ('case_id','passed','steps','selected_actions','elapsed_seconds')} for r in rows]}
