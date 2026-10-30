"""Presentation adapter only: immutable v2 engine, real AI or read-only evidence."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from threading import Lock
from uuid import uuid4

UI = Path(__file__).resolve().parent
PROJECT = UI.parents[1]
NATIVE = PROJECT / 'versions/invoice-v2'
RUN = PROJECT / 'runs/invoice-v2-exam-ollama-20261030T080451Z'
sys.path.insert(0, str(NATIVE))
from flowops import engine, models, planner, evaluation
from flowops.cases import load_cases
from flowops.invoices import invoice_case

for module in (engine, models, planner, evaluation):
    if Path(module.__file__).resolve().parent != NATIVE / 'flowops':
        raise RuntimeError('Mixed engine imports: launch presentation UI in a fresh process')

MODEL = 'qwen3:4b-instruct'
# Frozen Recorder temporarily wraps urllib during a call. Serialize UI calls across sessions.
MODEL_LOCK = Lock()
TERMINAL_EVENTS = {'tool_failed', 'planning_failed', 'verification_failed', 'step_limit'}


def read_json(path):
    return json.loads(path.read_text())


def verify_integrity():
    files = read_json(UI / 'protected-files.json')['files']
    for name, expected in files.items():
        if hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Protected file mismatch: ' + name)
    return len(files)


def replay_names():
    return [r['case_id'] for r in read_json(RUN / 'summary.json')['cases_detail']]


def saved_case(case_id):
    if case_id not in replay_names():
        raise ValueError('Unknown saved case')
    return read_json(RUN / (case_id + '.json'))


def seed_cases():
    # Scoring labels are removed before native intake; no golden amounts are used.
    cases = {}
    for record in read_json(PROJECT / 'external_exam_kit/exam.json'):
        clean = {k: record[k] for k in ('name', 'items', 'tax', 'total', 'locked')}
        cases[record['name']] = invoice_case(clean)
    cases.update({'legacy:' + name: case for name, case in load_cases().items()})
    return cases


def custom_case(issue, rows, vat, total, locked, needs_approval=False):
    if not issue.strip():
        raise ValueError('A merchant issue is required')
    record = {'name': 'merchant-' + uuid4().hex[:8],
              'items': [[row['Unit price'], row['Quantity']] for row in rows],
              'tax': vat, 'total': total, 'locked': locked}
    case = invoice_case(record)
    return replace(case, request=issue.strip(), risk='high' if needs_approval else 'low')


def money(cents):
    sign = '-' if cents < 0 else ''
    amount = abs(cents)
    return f'{sign}{amount // 100}.{amount % 100:02d}'


def disposition(report):
    events = report['audit_trail']
    runtime = any(e['action'] in TERMINAL_EVENTS for e in events)
    decisions = report['planner_decisions']
    if report['status'] == 'ESCALATED':
        explicit = (not runtime and bool(events) and events[-1]['action'] == 'escalate'
                    and bool(decisions) and decisions[-1]['action'] == 'escalate'
                    and decisions[-1]['executed_source'] == 'ollama:' + MODEL)
        return 'Model-selected escalation' if explicit else 'Runtime-enforced stop'
    if report['status'] == 'PAUSED_APPROVAL':
        return ('Model-requested human approval' if events and events[-1]['action'] == 'request_approval'
                else 'Policy-required human approval')
    return {'CLOSED_VERIFIED': 'Verified closure', 'ACTIVE': 'In progress'}.get(report['status'], report['status'])


def recorded_view(record, position):
    trace = record['trace']
    position = max(0, min(position, len(trace)))
    if position:
        last = trace[position - 1]
        state = last['state_after']
        checks = last['verification_after']
        status = last['status_after']
        pending = last['pending_patch_after']
        before = last['observation_before']['world']
    else:
        state = before = record['initial_state']
        checks = trace[0]['observation_before']['verification']
        status = trace[0]['observation_before']['status']
        pending = None
    return {'state': state, 'before': before, 'verification': checks, 'status': status,
            'pending': pending, 'frames': trace[:position], 'position': position,
            'complete': position == len(trace)}


class LiveTicket:
    """No alternate planner and no synthetic business actions in the UI."""
    def __init__(self, case):
        self.session = engine.WorkflowSession(case)
        self.initial = deepcopy(self.session.bill.snapshot())
        self.recorder = evaluation.Recorder(planner.OllamaPlanner(model=MODEL, timeout=180))
        self.ticket_id = uuid4().hex
        self.last_error = None

    def observe(self):
        try:
            return self.session.observe()
        except Exception as exc:
            self.last_error = type(exc).__name__ + ': independent verification unavailable'
            return None

    def step(self):
        session = self.session
        if session.status != 'ACTIVE':
            return
        if session.step_count >= 12:
            session.run(self.recorder, max_steps=0)
            return
        previous = len(self.recorder.trace)
        with MODEL_LOCK:
            try:
                result = session.step(self.recorder)
            except Exception as exc:
                session.status = 'ESCALATED'
                session._event('planning_failed', 'Live UI stopped; no fallback planner', error_type=type(exc).__name__)
                self.last_error = f'{type(exc).__name__}: {exc}'
                result = {'action': 'planning_failed', 'message': self.last_error}
            if len(self.recorder.trace) > previous:
                self.recorder.trace[-1].update(
                    tool_result=deepcopy(result), state_after=session.bill.snapshot(),
                    pending_patch_after=deepcopy(session.staged_patch),
                    verification_after=session.verification.as_dict(), status_after=session.status)
        if session.step_count >= 12 and session.status == 'ACTIVE':
            session.run(self.recorder, max_steps=0)

    def run(self):
        for _ in range(max(0, 12 - self.session.step_count)):
            if self.session.status != 'ACTIVE':
                break
            self.step()

    def approve(self, reviewer):
        self.session.grant_human_approval(reviewer)

    def view(self):
        session = self.session
        frames = self.recorder.trace
        before = frames[-1]['observation_before']['world'] if frames else self.initial
        return {'state': session.bill.snapshot(), 'before': before,
                'verification': session.verification.as_dict(), 'status': session.status,
                'pending': deepcopy(session.staged_patch), 'frames': frames,
                'position': len(frames), 'complete': session.status != 'ACTIVE'}

    def export(self):
        return {'presentation_version': 'invoice-ui-v1', 'mode': 'live_ai',
                'ticket_id': self.ticket_id, 'requested_model': MODEL,
                'temperature': 0, 'thinking': False, 'rules_fallback': False,
                'provenance': 'New interactive simulation, not the recorded diagnostic evaluation',
                'initial_state': self.initial, 'trace': deepcopy(self.recorder.trace),
                'report': self.session.report()}


def recorded_evaluation():
    summary = read_json(RUN / 'summary.json')
    rows = [saved_case(name) for name in replay_names()]
    if sum(row['passed'] for row in rows) != summary['passed']:
        raise RuntimeError('Saved summary differs from case artifacts')
    return summary, rows
