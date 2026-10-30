#!/usr/bin/env python3
"""Held-out orchestration v1; imports, never edits, frozen native evaluation."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib import request
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NATIVE = ROOT / 'versions/invoice-v2'
FREEZE = ROOT / '.hermes/freezes/invoice-v2.json'
PROTECTED = ROOT / 'presentation/invoice-ui-v1/protected-files.json'
VERSION = 'heldout-v1'
FIELDS = {'name', 'items', 'tax', 'total', 'locked', 'want'}
LABELS = {'fix', 'escalate', 'close_untouched'}
METRICS = ('correct_repair', 'correct_untouched_closure', 'model_selected_escalation',
           'correct_model_escalation', 'unnecessary_model_escalation', 'incorrect_escalation_state',
           'approval_request', 'unnecessary_human_intervention', 'invalid_closure',
           'runtime_stop', 'tool_failures', 'tool_rejections', 'business_refusals',
           'provider_or_planning_failures')


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def strict_json(data):
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Non-finite JSON value')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject)


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def scaled(value, scale):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value):
        raise ValueError('Amounts and VAT require nonnegative plain decimal strings')
    with localcontext() as context:
        context.prec = max(28, len(value) + 10)
        result = Decimal(value) * scale
        if result != result.to_integral_value():
            raise ValueError('Unsupported monetary/VAT precision')
        return int(result)


def transaction(record):
    # Label/ID independent and invariant to line ordering and decimal spelling.
    return {'items': sorted([scaled(p, 100), q] for p, q in record['items']),
            'tax_bps': scaled(record['tax'], 10000),
            'total_cents': scaled(record['total'], 100), 'locked': record['locked']}


def validate(raw, known=()):
    records = strict_json(raw)
    if not isinstance(records, list) or not records:
        raise ValueError('Expected a non-empty JSON array')
    names, transactions, hashes = set(), set(), []
    for record in records:
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise ValueError('Each record must contain exactly the six agreed fields')
        name = record['name']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
            raise ValueError('Unsafe case ID')
        if name in names:
            raise ValueError('Duplicate case ID')
        names.add(name)
        if not isinstance(record['want'], str) or record['want'] not in LABELS:
            raise ValueError('Unsupported want label')
        if type(record['locked']) is not bool:
            raise ValueError('locked must be boolean')
        if not isinstance(record['items'], list) or not record['items']:
            raise ValueError('items must be a non-empty array')
        for item in record['items']:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError('Each item requires price and quantity')
            price, quantity = item
            scaled(price, 100)
            if type(quantity) is not int or quantity <= 0:
                raise ValueError('Quantity requires a positive integer')
        if scaled(record['tax'], 10000) > 10000:
            raise ValueError('VAT outside zero to one')
        scaled(record['total'], 100)
        key = sha(canonical(transaction(record)))
        if key in transactions or key in known:
            raise ValueError('Duplicate transaction or diagnostic overlap')
        transactions.add(key)
        hashes.append({'case_id': name, 'case_sha256': sha(canonical(record)),
                       'transaction_sha256': key})
    return records, hashes


def provenance(author, authored_at, note):
    date = datetime.fromisoformat(authored_at.replace('Z', '+00:00'))
    frozen = datetime.fromisoformat(strict_json(FREEZE.read_bytes())['frozen_utc'])
    if date.tzinfo is None or not frozen < date <= datetime.now(timezone.utc):
        raise ValueError('Authorship timestamp must be timezone-aware, after agent freeze, and not in the future')
    if not author.strip() or not note.strip():
        raise ValueError('Author and provenance note must not be empty')
    return {'author': author, 'authored_at': date.isoformat(), 'note': note,
            'independent_after_agent_freeze': True, 'not_previously_run_or_used_for_development': True,
            'basis': 'Supplier attestation plus diagnostic-overlap checks; not independent certification'}


def verify_integrity():
    release = strict_json((HERE / 'freeze.json').read_bytes())
    for name, expected in release['files'].items():
        if sha((HERE / name).read_bytes()) != expected:
            raise RuntimeError('Wrapper freeze mismatch: ' + name)
    if sha(FREEZE.read_bytes()) != release['native_freeze_sha256']:
        raise RuntimeError('Original freeze changed')
    if sha(PROTECTED.read_bytes()) != release['protected_manifest_sha256']:
        raise RuntimeError('Protected manifest changed')
    native = strict_json(FREEZE.read_bytes())
    protected = strict_json(PROTECTED.read_bytes())['files']
    for name, expected in {**protected, **native['files']}.items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise RuntimeError('Protected file mismatch: ' + name)
    return native, release


def load_native():
    sys.path.insert(0, str(NATIVE))
    from flowops import evaluation, invoices, planner, engine
    for module in (evaluation, invoices, planner, engine):
        if Path(module.__file__).resolve().parent != NATIVE / 'flowops':
            raise RuntimeError('Mixed engine imports')
    return evaluation, invoices, planner


def outcomes(row):
    model = row['model_selected_escalation']
    approval = row['approval_pause']
    return {'correct_repair': bool(row['want'] == 'fix' and row['passed'] and row['repaired_and_closed']),
            'correct_untouched_closure': bool(row['want'] == 'close_untouched' and row['passed'] and row['closed_untouched']),
            'model_selected_escalation': model,
            'correct_model_escalation': bool(model and row['want'] == 'escalate' and row['passed']),
            'unnecessary_model_escalation': bool(model and row['want'] != 'escalate'),
            'incorrect_escalation_state': bool(model and row['want'] == 'escalate' and not row['passed']),
            'approval_request': approval,
            'unnecessary_human_intervention': bool(approval or (model and row['want'] != 'escalate')),
            'invalid_closure': row['invalid_close'], 'runtime_stop': row['runtime_enforced_stop'],
            'tool_failures': row['failed_tool_calls'], 'tool_rejections': row['rejected_tool_calls'],
            'business_refusals': row['business_refusals'],
            'provider_or_planning_failures': sum('decision_error' in t for t in row['trace'])}


def summary(rows, records, elapsed, complete):
    totals = Counter({key: 0 for key in METRICS})
    for row in rows:
        totals.update(outcomes(row))
    return {'evaluation': VERSION, 'label': 'held-out (supplier-attested)', 'complete': complete,
            'cases_planned': len(records), 'cases_recorded': len(rows),
            'passed': sum(r['passed'] for r in rows),
            'denominators': {label: sum(r['want'] == label for r in records) for label in sorted(LABELS)},
            'outcomes': dict(totals), 'case_seconds': sum(r['elapsed_seconds'] for r in rows),
            'model_calls_in_completed_cases': sum('request' in t for r in rows for t in r['trace']),
            'unrecorded_cases': len(records) - len(rows),
            'wall_seconds': elapsed,
            'cases': [{'case_id': r['case_id'], 'passed': r['passed'], 'outcomes': outcomes(r),
                       'elapsed_seconds': r['elapsed_seconds']} for r in rows]}


@contextmanager
def durable_transport(evaluation, out):
    transport = evaluation.TRANSPORT
    sequence = 0
    def capture(req, *args, **kwargs):
        nonlocal sequence
        sequence += 1
        prefix = out / f'call-{sequence:05d}'
        # Written before a provider call, including calls interrupted before a response.
        write_new(prefix.with_suffix('.request.json'), strict_json(req.data))
        try:
            with transport(req, *args, **kwargs) as response:
                body = response.read()
            with prefix.with_suffix('.response.bin').open('xb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            return io.BytesIO(body)
        except BaseException as exc:
            write_new(prefix.with_suffix('.error.json'), {'type': type(exc).__name__, 'at': now()})
            raise
    with patch.object(evaluation, 'TRANSPORT', capture):
        yield


def get_runtime():
    result = {}
    for key, path in [('server', '/api/version'), ('installed', '/api/tags')]:
        with request.urlopen('http://127.0.0.1:11434' + path, timeout=10) as response:
            result[key] = json.load(response)
    return result


def run(args):
    frozen, release = verify_integrity()
    if not args.attest_unseen:
        raise ValueError('Explicit unseen/independent attestation required')
    source = args.cases.resolve()
    raw = source.read_bytes()
    if sha(raw) != args.sha256.lower():
        raise ValueError('Input SHA-256 does not match supplied digest')
    known_records = strict_json((ROOT / 'external_exam_kit/exam.json').read_bytes())
    known = {sha(canonical(transaction(r))) for r in known_records}
    records, hashes = validate(raw, known)
    prov = provenance(args.author, args.authored_at, args.provenance_note)
    evaluation, invoices, planner = load_native()
    # Explicit allowlist: neither want, corrected totals nor original IDs reach intake.
    cases = [invoices.invoice_case({**{k: r[k] for k in ('items', 'tax', 'total', 'locked')},
                                    'name': f'case-{i:04d}'}) for i, r in enumerate(records, 1)]
    # Validate representability by frozen tools/oracle before any attempt claim or call.
    for record, case in zip(records, cases):
        state = case.initial_bill
        if (state['stored_total_cents'] != scaled(record['total'], 100)
                or state['tax_bps'] != scaled(record['tax'], 10000)
                or state['line_items'] != [{'unit_price_cents': scaled(p, 100), 'quantity': q}
                                           for p, q in record['items']]):
            raise ValueError('Input exceeds exact representation supported by frozen intake')
        evaluation.oracle_cents(record)
    runs = ROOT / 'runs'
    runs.mkdir(exist_ok=True)
    claims = runs / 'heldout-v1-attempts'
    claims.mkdir(exist_ok=True)
    # Same transaction set, regardless of labels/order/IDs/format, shares one claim.
    set_hash = sha(canonical(sorted(h['transaction_sha256'] for h in hashes)))
    out = runs / ('invoice-v2-heldout-v1-' + set_hash[:20])
    if out.exists():
        raise FileExistsError('Output already exists; original attempt will not be modified')
    claim = claims / (set_hash + '.json')
    write_new(claim, {'claimed_utc': now(), 'output': str(out), 'input_sha256': sha(raw),
                      'policy': 'First attempt only; no automatic retry or resume'})
    # Also block partial-overlap reruns disguised as a different transaction set.
    # A failed claim is retained, not deleted to permit an automatic second attempt.
    for entry in sorted(hashes, key=lambda h: h['transaction_sha256']):
        write_new(claims / ('transaction-' + entry['transaction_sha256'] + '.json'),
                  {'claimed_utc': now(), 'set_sha256': set_hash, 'output': str(out)})
    rows = []
    started = time.monotonic()
    active = None
    created = False
    try:
        out.mkdir(exist_ok=False)
        created = True
        print('OUTPUT: ' + str(out), flush=True)
        (out / 'calls').mkdir()
        write_new(out / 'metadata.json', {'version': VERSION, 'label': 'held-out (supplier-attested)',
                  'started_utc': now(), 'provenance': prov, 'case_file_sha256': sha(raw),
                  'transaction_set_sha256': set_hash, 'case_hashes': hashes,
                  'wrapper_sha256': sha(Path(__file__).read_bytes()),
                  'wrapper_freeze_sha256': sha((HERE / 'freeze.json').read_bytes()),
                  'native_freeze_sha256': sha(FREEZE.read_bytes()), 'native_files': frozen['files'],
                  'model_settings': frozen['protocol'],
                  'protocol_note': 'Model settings inherited unchanged; original exam/provenance fields describe diagnostic freeze, not this dataset',
                  'first_attempt': True, 'git_commit': None,
                  'timing_scope': 'wall includes runtime discovery, case execution and evidence writes; excludes validation',
                  'intervention_policy': 'No human approvals granted; all approval pauses count as unnecessary under this low-risk schema'})
        with (out / 'input.private.json').open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        runtime = get_runtime()
        write_new(out / 'runtime.json', runtime)
        matches = [m for m in runtime['installed'].get('models', []) if m.get('name') == evaluation.MODEL]
        if len(matches) != 1 or matches[0].get('digest') != frozen['protocol']['model_digest']:
            raise RuntimeError('Frozen model digest unavailable; no substitution/download')
        with durable_transport(evaluation, out / 'calls'):
            for record, case in zip(records, cases):
                active = record['name']
                write_new(out / (active + '.started.json'), {'at': now(), 'case_id': active})
                # Grading label consumed only after execution by unchanged native evaluate.
                row = evaluation.evaluate(record, case, planner.OllamaPlanner(model=evaluation.MODEL, timeout=180), max_steps=12)
                row['outcomes'] = outcomes(row)
                write_new(out / (active + '.result.json'), row)
                rows.append(row)
                print(json.dumps({'case': active, 'passed': row['passed'], 'status': row['report']['status']}), flush=True)
                active = None
        verify_integrity()
        if source.read_bytes() != raw:
            raise RuntimeError('Source input changed during execution')
        write_new(out / 'summary.json', summary(rows, records, time.monotonic() - started, True))
        write_new(out / 'completion.json', {'complete': True, 'finished_utc': now(), 'cases_recorded': len(rows)})
        print('FINISHED: ' + str(out), flush=True)
    except BaseException as exc:
        if created:
            # Exclusive artifacts retain every completed case and in-flight call.
            write_new(out / 'aborted.json', {'complete': False, 'type': type(exc).__name__,
                      'active_case': active, 'cases_recorded': len(rows), 'at': now(),
                      'partial_state_note': 'Calls are durable; an interrupted native evaluate may not return its final in-memory state'})
            write_new(out / 'partial-summary.json', summary(rows, records, time.monotonic() - started, False))
        raise
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--author', required=True)
    parser.add_argument('--authored-at', required=True, help='ISO 8601 with timezone; after original agent freeze')
    parser.add_argument('--provenance-note', required=True)
    parser.add_argument('--attest-unseen', action='store_true', help='Attest independent authorship after agent freeze and no prior development/evaluation exposure')
    args = parser.parse_args(argv)
    if not re.fullmatch('[0-9a-fA-F]{64}', args.sha256):
        parser.error('--sha256 requires 64 hex characters')
    return run(args)


if __name__ == '__main__':
    main()
