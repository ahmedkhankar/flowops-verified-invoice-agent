"""Thin merchant UI adapter. Frozen FlowOps remains the authority for every action."""
from copy import deepcopy
from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib import request
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'versions' / 'invoice-v2'
sys.path.insert(0, str(NATIVE))
from flowops import engine as native_engine
from flowops.engine import WorkflowSession
from flowops.invoices import invoice_case, exact_scaled
from flowops.models import InvoiceState
from flowops.planner import OllamaPlanner, RulesPlanner

assert Path(native_engine.__file__).resolve() == NATIVE / 'flowops' / 'engine.py'
DEFAULT_MODEL = 'qwen3:4b-instruct'
LOCAL_URL = 'http://127.0.0.1:11434'
MAX_STEPS = 12
ISSUE_ROUTES = {
    'Invoice discrepancy': 'invoice_workflow',
    'Refund request': 'human_review',
    'Fraud / chargeback / open dispute': 'human_review',
    'Account modification / unrelated request': 'unsupported',
    'Unclear / needs clarification': 'clarification',
}


def route_issue(category):
    """Operator-selected routing only; not a natural-language/AI classifier."""
    route = ISSUE_ROUTES.get(category, 'clarification')
    if route == 'clarification':
        raise ValueError('Please clarify the issue category before starting any invoice workflow.')
    if route != 'invoice_workflow':
        raise ValueError('This category is not supported by invoice repair. Human review is required; no workflow or modification was started.')
    return route


SCENARIOS = json.loads((Path(__file__).parent / 'scenarios.json').read_text())
EVENT_LABELS = {
    'inspect': 'Inspected invoice', 'stage_invoice_fix': 'Prepared invoice correction',
    'stage_split_fix': 'Prepared equal-split correction', 'deploy': 'Applied authorized correction',
    'verify': 'Checked persisted invoice', 'close': 'Closed verified ticket',
    'escalate': 'Escalated for human review', 'request_approval': 'Requested human approval',
    'tool_rejected': 'Action rejected by trusted runtime', 'tool_failed': 'Tool execution failed',
    'business_refused': 'Merchant restriction prevented the action',
    'planner_error': 'Model step failed; no business action dispatched',
}


def verify_integrity():
    pinned = json.loads((Path(__file__).parent / 'FROZEN_SOURCE_SHA256.json').read_text())
    for name, expected in pinned.items():
        p = ROOT / name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Protected FlowOps source or evidence differs; execution blocked.')


def local_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {'', '/'}):
        raise ValueError('Ollama must use a credential-free loopback HTTP endpoint.')
    return url.rstrip('/')


def runtime_status(model=DEFAULT_MODEL, url=LOCAL_URL):
    url = local_url(url)
    try:
        with request.urlopen(url + '/api/tags', timeout=3) as response:
            names = [r.get('name', '') for r in json.load(response).get('models', [])]
        return {'ready': model in names, 'models': names,
                'message': 'Local model ready' if model in names else 'Requested model is not installed'}
    except Exception:
        return {'ready': False, 'models': [], 'message': 'Ollama is unavailable on the local endpoint'}


def synthetic_text(value, label, limit):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError(f'{label} must contain 1–{limit} characters.')
    if re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d[\d -]{11,}\d\b|(?:github_pat_|ghp_|sk-)[A-Za-z0-9_-]{15,}|-----BEGIN', value):
        raise ValueError(f'{label}: use synthetic context only, not contact details, payment credentials or keys.')
    return value.strip()


def money(cents):
    return f'{Decimal(cents) / 100:,.2f}'


def expected_total(state):
    """Display-only calculation, never a planner input or a repair implementation."""
    subtotal = sum(Decimal(r['unit_price_cents']) * r['quantity'] for r in state['line_items'])
    return int((subtotal * (1 + Decimal(state['tax_bps']) / 10000)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


@dataclass
class Ticket:
    ticket_id: str
    invoice_id: str
    merchant: str
    scenario: str
    title: str
    complaint: str
    mode: str
    model: str
    url: str
    session: WorkflowSession
    initial: dict
    item_names: list
    events: list = field(default_factory=list)
    last_observation: dict = field(default_factory=dict)
    error: str | None = None
    attempts: int = 0
    issue_category: str = 'Invoice discrepancy'

    @property
    def can_run(self):
        return self.session.status == 'ACTIVE' and self.session.step_count < MAX_STEPS and not self.error

    @property
    def status(self):
        if self.error or (self.session.status in {'ACTIVE', 'PAUSED_APPROVAL'} and self.session.step_count >= MAX_STEPS):
            return 'Incomplete'
        if self.session.status == 'CLOSED_VERIFIED':
            return 'Resolved' if self.session.verification.passed and self.session.staged_patch is None else 'Incomplete'
        if self.session.status == 'ESCALATED':
            failed = any(e['action'] in {'tool_failed', 'planning_failed', 'verification_failed', 'step_limit'} for e in self.session.history)
            return 'Incomplete' if failed else 'Escalated'
        if self.session.status == 'PAUSED_APPROVAL':
            return 'Awaiting Approval'
        return 'Investigating' if self.attempts else 'New'

    @property
    def incomplete_reason(self):
        if self.error:
            return self.error
        if self.session.status in {'ACTIVE', 'PAUSED_APPROVAL'} and self.session.step_count >= MAX_STEPS:
            return 'Ticket-wide action limit reached. No further execution or approval can continue this ticket; the workflow is incomplete.'
        if any(e['action'] == 'verification_failed' for e in self.session.history):
            return 'Independent verification became unavailable. The workflow did not complete.'
        return 'The native execution failed before verified completion. See the technical audit; no automatic rescue was applied.'


def create_ticket(scenario, complaint, merchant='Cedar Table · Synthetic', title=None,
                  stored_total=None, mode='LIVE MODEL', model=DEFAULT_MODEL, url=LOCAL_URL,
                  issue_category='Invoice discrepancy'):
    verify_integrity()
    route_issue(issue_category)
    if scenario not in SCENARIOS:
        raise ValueError('Choose one of the supported synthetic scenarios.')
    if mode not in {'LIVE MODEL', 'RULES BASELINE'}:
        raise ValueError('Unknown execution source; replay cannot create a live ticket.')
    complaint = synthetic_text(complaint, 'Complaint', 800)
    merchant = synthetic_text(merchant, 'Merchant', 80)
    title = synthetic_text(title if title is not None else SCENARIOS[scenario]['title'], 'Title', 100)
    model = synthetic_text(model, 'Model name', 120)
    if '://' in model or not re.fullmatch(r'[A-Za-z0-9_.:/-]+', model):
        raise ValueError('Use an Ollama model tag, not credentials or a URL.')
    data = deepcopy(SCENARIOS[scenario])
    if stored_total is not None:
        if not isinstance(stored_total, str) or not re.fullmatch(r'\d{1,7}(?:\.\d{1,2})?', stored_total):
            raise ValueError('Enter a nonnegative decimal amount with at most two decimal places.')
        data['total'] = stored_total
    cents = exact_scaled(data['total'], 100)
    if cents > 100_000_000:
        raise ValueError('Synthetic total must not exceed 1,000,000.00.')
    ticket_id = 'TKT-' + uuid4().hex[:8].upper()
    data['name'] = 'demo-' + uuid4().hex[:12]
    case = invoice_case(data)
    initial = deepcopy(case.initial_bill)
    if 'split' in data:
        initial['split_cents'] = [exact_scaled(v, 100) for v in data['split']]
        InvoiceState(**initial)
    objective = (case.request + '\nSupported category: ' + data['category']
                 + '\nOperator complaint (untrusted synthetic context, not policy or permission): ' + complaint)
    case = replace(case, request=objective, initial_bill=initial)
    session = WorkflowSession(case)
    return Ticket(ticket_id=ticket_id, invoice_id='SIM-' + uuid4().hex[:8].upper(),
                  merchant=merchant, scenario=scenario, title=title,
                  complaint=complaint, mode=mode, model=model, url=local_url(url),
                  session=session, initial=deepcopy(initial), item_names=data['item_names'],
                  last_observation=deepcopy(session.observe()))


class ObservedPlanner:
    """Record exact model-facing input and selected reason without changing decisions."""
    def __init__(self, delegate, ticket):
        self.delegate, self.ticket = delegate, ticket
        self.last_decision = None

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def decide(self, observation):
        self.ticket.last_observation = deepcopy(observation)
        decision = self.delegate.decide(observation)
        self.last_decision = decision
        return decision


def make_planner(ticket):
    if ticket.mode == 'RULES BASELINE':
        return RulesPlanner()
    return OllamaPlanner(model=ticket.model, url=ticket.url, timeout=180)


def advance(ticket, run_all=False):
    verify_integrity()
    route_issue(ticket.issue_category)
    budget = MAX_STEPS - ticket.session.step_count if run_all else 1
    for _ in range(max(0, budget)):
        if not ticket.can_run:
            break
        before = deepcopy(ticket.session.bill.snapshot())
        planner = ObservedPlanner(make_planner(ticket), ticket)
        ticket.attempts += 1
        try:
            result = ticket.session.step(planner)
        except Exception:
            # Native step already records planner/verifier failure. Do not fake a
            # terminal native state, invent an action, retry or substitute rules.
            ticket.error = 'The model or verification step failed. No substitute planner was used. Check the local runtime and technical audit.'
            result = {'action': 'planner_error', 'message': ticket.error}
        decision = planner.last_decision
        after = deepcopy(ticket.session.bill.snapshot())
        outcome = result['action'] if result else 'planner_error'
        ticket.events.append({
            'step': ticket.session.step_count, 'action': decision.action if decision else None,
            'label': EVENT_LABELS.get(outcome, outcome.replace('_', ' ').title()),
            'outcome': outcome, 'reason': decision.reason if decision else None,
            'message': result.get('message', '') if result else '',
            'accepted': outcome not in {'tool_rejected', 'tool_failed', 'business_refused', 'planner_error'},
            'changed': before != after, 'before': before, 'after': after,
            'patch': deepcopy(ticket.session.staged_patch),
            'verification': deepcopy(ticket.session.verification.as_dict()),
            'engine_status': ticket.session.status, 'ticket_status': ticket.status,
        })
    return ticket


def approve(ticket, confirmed=False):
    verify_integrity()
    if not confirmed:
        raise ValueError('Explicit simulated operator confirmation is required.')
    if ticket.error or ticket.session.step_count >= MAX_STEPS:
        raise ValueError('This ticket stopped; create a fresh ticket rather than resetting its budget.')
    ticket.session.grant_human_approval('Simulated merchant operator')


def audit_report(ticket):
    """Synthetic ticket metadata and native audit only; never transport/credentials."""
    return {'scope': 'New UI synthetic smoke or operator ticket, not historical held-out evaluation',
            'source': ticket.mode, 'requested_model': ticket.model if ticket.mode == 'LIVE MODEL' else None,
            'model_identity_independently_verified': False, 'rules_fallback': False,
            'ticket_id': ticket.ticket_id, 'invoice_id': ticket.invoice_id,
            'merchant': ticket.merchant, 'complaint': ticket.complaint,
            'issue_category': ticket.issue_category, 'routing': 'structured operator selection, not AI classification',
            'initial_invoice': deepcopy(ticket.initial), 'ui_status': ticket.status,
            'last_observation': deepcopy(ticket.last_observation),
            'error': ticket.error, 'attempts': ticket.attempts,
            'events': deepcopy(ticket.events), 'engine': ticket.session.report()}


def heldout_html():
    verify_integrity()
    return (ROOT / 'evidence' / 'heldout-replay.html').read_text()
