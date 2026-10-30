"""Live local evaluation; no fallback, approval grants, or payment access.

Records real loopback HTTP responses without modifying planner prompts/tools.
Existing cases are builder-authored demonstrations, not held-out evaluation.
"""
import hashlib
import argparse
import io
import json
from pathlib import Path
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib import request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flowops.cases import CASE_FILE, load_cases
from flowops.engine import WorkflowSession
from flowops.planner import OllamaPlanner, RulesPlanner
from flowops.verifier import check_state

MODEL = 'qwen3:4b-instruct'
BASE = 'http://127.0.0.1:11434'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--label', default='diagnostic-feedback-v1')
parser.add_argument('--cases-file', type=Path)
parser.add_argument('--independent-cases', action='store_true',
                    help='Only for new cases independently authored by the project owner after the implementation freeze')
parser.add_argument('--freeze-file', type=Path, required=True)
args = parser.parse_args()
if not args.label or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in args.label):
    parser.error('Label must contain only lowercase letters, digits, hyphens or underscores')
if args.independent_cases and not args.cases_file:
    parser.error('Independent evaluation requires an explicitly supplied case file')
freeze = json.loads(args.freeze_file.read_text())
for name, digest in freeze['files'].items():
    if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
        parser.error(f'Implementation differs from frozen file: {name}')
case_file = args.cases_file.resolve() if args.cases_file else CASE_FILE
if args.independent_cases and (case_file == CASE_FILE or
        hashlib.sha256(case_file.read_bytes()).digest() == hashlib.sha256(CASE_FILE.read_bytes()).digest()):
    parser.error('Original demo cases are diagnostic, never independent evaluation')
baseline = ROOT / 'runs' / 'ollama-live-20261030T055320Z'
baseline_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(baseline.iterdir()) if p.is_file()}
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT = ROOT / 'runs' / ('ollama-' + args.label + '-' + STAMP)
OUT.mkdir(parents=True, exist_ok=False)
ORIGINAL_URLOPEN = request.urlopen


def get_json(path):
    with ORIGINAL_URLOPEN(BASE + path, timeout=10) as response:
        return json.load(response)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


class Recorder:
    def __init__(self, planner):
        self.inner = planner
        self.steps = []
        self.pending = None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @contextmanager
    def capture_http(self, req, *args, **kwargs):
        if req.full_url != BASE + '/api/chat':
            raise RuntimeError('Evaluation permits only the local Ollama chat endpoint')
        payload = json.loads(req.data)
        assert payload['model'] == MODEL
        assert payload['options']['temperature'] == 0
        assert payload['think'] is False
        self.pending['request'] = payload
        with ORIGINAL_URLOPEN(req, *args, **kwargs) as response:
            data = response.read()
        envelope = json.loads(data)
        self.pending['response'] = {
            key: envelope.get(key) for key in (
                'model', 'done', 'done_reason', 'total_duration', 'load_duration',
                'prompt_eval_count', 'prompt_eval_duration', 'eval_count', 'eval_duration'
            )
        }
        # Store the public structured answer, not private thinking/reasoning fields.
        self.pending['response']['content'] = envelope.get('message', {}).get('content')
        yield io.BytesIO(data)

    def decide(self, observation):
        row = {'index': len(self.steps) + 1, 'observation_before': observation}
        self.pending = row
        start = time.monotonic()
        try:
            if isinstance(self.inner, OllamaPlanner):
                # Pass-through recorder: genuine HTTP request and original response bytes.
                # No fabricated/mocked model output is supplied.
                with patch('flowops.planner.request.urlopen', self.capture_http):
                    decision = self.inner.decide(observation)
            else:
                decision = self.inner.decide(observation)
            row['chosen_action'] = decision.action
            row['reason'] = decision.reason
            return decision
        except Exception as exc:
            row['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            row['seconds'] = round(time.monotonic() - start, 4)
            self.steps.append(row)
            self.pending = None


metadata = {
    'started_utc': datetime.now(timezone.utc).isoformat(),
    'requested_model': MODEL, 'temperature': 0, 'think': False,
    'rules_fallback': False, 'max_steps': 12, 'per_request_timeout_seconds': 180,
    'human_approvals_granted': False,
    'case_file': str(case_file),
    'case_sha256': hashlib.sha256(case_file.read_bytes()).hexdigest(),
    'experiment_label': args.label,
    'provenance': ('User-declared independently authored new cases after implementation freeze'
                   if args.independent_cases else
                   'Diagnostic experiment on original builder-authored cases; not held-out or independent evaluation'),
    'implementation_freeze': freeze,
    'original_failed_run_sha256': baseline_hashes,
    'security': 'Loopback Ollama only; no paid API, sign-in or payment access',
    'code_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                    for name in ['flowops/engine.py', 'flowops/planner.py',
                                 'flowops/fixer.py', 'flowops/verifier.py', 'flowops/models.py',
                                 'flowops/tools.py', 'scripts/evaluate_ollama_local.py']},
    'server_version': get_json('/api/version'),
}
write_json(OUT/'metadata.json', metadata)
print('Evidence directory:', OUT, flush=True)
# The separately authorized model pull may still be in progress. Inspect actual
# installed-model readiness, with a bounded deadline; never replace the model.
deadline = time.monotonic() + 1800
while True:
    tags = get_json('/api/tags')
    found = next((m for m in tags.get('models', []) if m.get('name') == MODEL), None)
    if found:
        metadata['installed_model'] = found
        write_json(OUT/'metadata.json', metadata)
        break
    if time.monotonic() >= deadline:
        raise RuntimeError('Requested model did not become installed within 30 minutes')
    time.sleep(5)

cases = load_cases(case_file)
rows = []
for mode in ['rules', 'ollama']:
    for cid, case in cases.items():
        session = WorkflowSession(case)
        recorder = Recorder(RulesPlanner() if mode == 'rules'
                            else OllamaPlanner(model=MODEL, timeout=180))
        begun = time.monotonic()
        for _ in range(12):
            if session.status != 'ACTIVE':
                break
            # run(max_steps=1) would impose a premature step-limit escalation.
            try:
                result = session.step(recorder)
            except Exception as exc:
                session.status = 'ESCALATED'
                session._event('planning_failed',
                               'Escalated after observation/planning failure; no action dispatched')
                if recorder.steps:
                    recorder.steps[-1]['run_error_type'] = type(exc).__name__
                break
            if recorder.steps:
                recorder.steps[-1]['tool_result'] = result
                recorder.steps[-1]['state_after'] = session.bill.snapshot()
                recorder.steps[-1]['verification_after'] = session.verification.as_dict()
                recorder.steps[-1]['status_after'] = session.status
            print(mode, cid, session.step_count,
                  recorder.steps[-1].get('chosen_action') if recorder.steps else None,
                  session.status, 'verified=', session.verification.passed, flush=True)
        if session.status == 'ACTIVE':
            session.status = 'ESCALATED'
            session._event('step_limit', 'Escalated after at most 12 planning steps')
        report = session.report()
        # Fresh read-only check for evaluation; use original case criteria.
        fresh = check_state(session.bill, case.acceptance)
        closed = session.status == 'CLOSED_VERIFIED'
        required_approval = case.risk == 'high' or bool(case.policy_flags)
        actions = [s['chosen_action'] for s in recorder.steps if 'chosen_action' in s]
        if session.status == 'PAUSED_APPROVAL':
            termination = 'model_requested_approval' if 'request_approval' in actions else 'policy_approval_gate'
        elif session.status == 'ESCALATED':
            if any(e['action'] == 'planning_failed' for e in session.history):
                termination = 'runtime_planning_failure'
            elif any(e['action'] == 'step_limit' for e in session.history):
                termination = 'runtime_step_limit'
            elif actions and actions[-1] == 'escalate':
                termination = 'model_selected_escalation' if mode == 'ollama' else 'rules_selected_escalation'
            else:
                termination = 'runtime_execution_failure'
        else:
            termination = 'verified_closure' if closed else session.status
        row = {
            'mode': mode, 'case_id': cid, 'status': session.status,
            'verified': fresh.passed, 'steps_used': session.step_count,
            'planner_calls': len(recorder.steps), 'actions': actions,
            'wrong_close': closed and not fresh.passed,
            'approval_violation': closed and required_approval and not session.approved_by,
            'resolved': closed and fresh.passed and (not required_approval or bool(session.approved_by)),
            'termination': termination, 'seconds': round(time.monotonic() - begun, 4),
            'fresh_acceptance_check': fresh.as_dict(),
            'trace': recorder.steps, 'report': report,
        }
        write_json(OUT/(mode + '-' + cid + '.json'), row)
        rows.append(row)
        print('OUTCOME', mode, cid, row['status'], termination, row['seconds'], flush=True)

summary = {}
for mode in ['rules', 'ollama']:
    group = [r for r in rows if r['mode'] == mode]
    summary[mode] = {
        'cases': len(group), 'resolved': sum(r['resolved'] for r in group),
        'wrong_closes': sum(r['wrong_close'] for r in group),
        'approval_violations': sum(r['approval_violation'] for r in group),
        'escalations': sum(r['status'] == 'ESCALATED' for r in group),
        'approval_pauses': sum(r['status'] == 'PAUSED_APPROVAL' for r in group),
        'selected_escalations': sum(r['termination'] in {'model_selected_escalation', 'rules_selected_escalation'} for r in group),
        'runtime_enforced_stops': sum(r['termination'].startswith('runtime_') for r in group),
        'rejected_actions': sum(e['action'] == 'tool_rejected' for r in group for e in r['report']['audit_trail']),
        'steps': sum(r['steps_used'] for r in group),
        'planner_calls': sum(r['planner_calls'] for r in group),
        'seconds': round(sum(r['seconds'] for r in group), 4),
        'cases_detail': [{k:v for k,v in r.items() if k not in ['trace','report']} for r in group],
    }
write_json(OUT/'summary.json', summary)
metadata['finished_utc'] = datetime.now(timezone.utc).isoformat()
metadata['running_models_after'] = get_json('/api/ps')
assert hashlib.sha256(case_file.read_bytes()).hexdigest() == metadata['case_sha256']
assert baseline_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(baseline.iterdir()) if p.is_file()}
for name, digest in freeze['files'].items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
metadata['frozen_files_and_original_results_unchanged'] = True
write_json(OUT/'metadata.json', metadata)
print('SUMMARY', json.dumps(summary, ensure_ascii=False), flush=True)
print('FINISHED:', OUT, flush=True)
