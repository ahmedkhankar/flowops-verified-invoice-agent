"""Wrapper-only synthetic fixtures; no held-out data and no real networking."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('heldout_wrapper', HERE / 'run.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
sys.path.insert(0, str(w.NATIVE))
from flowops import evaluation, planner


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('Real network forbidden in wrapper tests')
    monkeypatch.setattr(w.request, 'urlopen', fail)
    monkeypatch.setattr(evaluation, 'TRANSPORT', fail)
    monkeypatch.setattr(planner.RulesPlanner, 'decide', fail)


def fixture_records():
    # Authored solely as developer-visible unit fixtures, never claimed held-out.
    return [dict(name='fixture_repair', items=[['6.13', 3]], tax='0.07', total='1.00', locked=False, want='fix'),
            dict(name='fixture_close', items=[['2.00', 4]], tax='0.00', total='8.00', locked=False, want='close_untouched'),
            dict(name='fixture_lock', items=[['7.91', 1]], tax='0.03', total='1.00', locked=True, want='escalate')]


def test_schema_and_hashes():
    records = fixture_records()
    parsed, hashes = w.validate(json.dumps(records).encode())
    assert parsed == records and len(hashes) == 3
    assert all(len(row['transaction_sha256']) == 64 for row in hashes)


@pytest.mark.parametrize('field,value', [
    ('name', '../escape'), ('name', ''), ('name', 'x' * 81),
    ('total', 1.23), ('total', '-1.00'), ('total', '0.001'),
    ('total', 'NaN'), ('total', '1e2'), ('tax', '1.01'), ('tax', '0.00001'),
    ('locked', 1), ('want', 'repair'), ('want', []), ('items', []),
    ('items', [['1.00', True]]), ('items', [['1.00', 0]]),
    ('items', [['1.00', 1.5]]), ('items', [['1.00', -1]]),
    ('items', [['1.00']]), ('items', [['0.001', 1]])])
def test_invalid_schema(field, value):
    record = fixture_records()[0]
    record[field] = value
    with pytest.raises(ValueError):
        w.validate(json.dumps([record]).encode())


def test_duplicate_ids_keys_and_extra_fields():
    a, b, _ = fixture_records()
    b['name'] = a['name']
    with pytest.raises(ValueError, match='Duplicate case ID'):
        w.validate(json.dumps([a, b]).encode())
    a['answer'] = 42
    with pytest.raises(ValueError):
        w.validate(json.dumps([a]).encode())
    with pytest.raises(ValueError, match='Duplicate JSON key'):
        w.strict_json('{"x":1,"x":2}')
    with pytest.raises(ValueError):
        w.validate(b'[]')
    with pytest.raises(ValueError):
        w.strict_json('[NaN]')


def test_transaction_equivalence_and_overlap():
    a = fixture_records()[0]
    b = {**a, 'name': 'renamed', 'want': 'escalate', 'items': [['06.130', 3]], 'tax': '0.0700'}
    assert w.transaction(a) == w.transaction(b)
    with pytest.raises(ValueError, match='Duplicate transaction'):
        w.validate(json.dumps([a, b]).encode())
    known = {w.sha(w.canonical(w.transaction(a)))}
    with pytest.raises(ValueError, match='diagnostic overlap'):
        w.validate(json.dumps([b]).encode(), known)


def setup_run(tmp_path, monkeypatch, records=None):
    root = tmp_path / 'project'
    (root / 'external_exam_kit').mkdir(parents=True)
    (root / 'external_exam_kit/exam.json').write_text('[]')
    records = records or fixture_records()
    source = tmp_path / 'developer-fixture.json'
    source.write_text(json.dumps(records))
    monkeypatch.setattr(w, 'ROOT', root)
    support = tmp_path / 'wrapper-support'
    support.mkdir()
    (support / 'freeze.json').write_text('{"offline_fixture":true}')
    monkeypatch.setattr(w, 'HERE', support)
    frozen = w.strict_json(w.FREEZE.read_bytes())
    monkeypatch.setattr(w, 'verify_integrity', lambda: (frozen, {}))
    monkeypatch.setattr(w, 'get_runtime', lambda: {'installed': {'models': [
        {'name': evaluation.MODEL, 'digest': frozen['protocol']['model_digest']}]}})
    args = SimpleNamespace(cases=source, sha256=w.sha(source.read_bytes()), author='Offline test',
                           authored_at='2026-10-30T08:05:00+00:00', provenance_note='Synthetic fixture, not held-out', attest_unseen=True)
    return args, root


def transport_for(actions, requests):
    actions = iter(actions)
    def fake(req, *args, **kwargs):
        payload = json.loads(req.data)
        requests.append(payload)
        return io.BytesIO(json.dumps({'model': evaluation.MODEL, 'message': {
            'content': json.dumps({'action': next(actions), 'reason': 'OFFLINE unit fixture'})}}).encode())
    return fake


def test_complete_run_labels_private_durable_calls_and_no_retry(tmp_path, monkeypatch):
    args, root = setup_run(tmp_path, monkeypatch)
    requests = []
    monkeypatch.setattr(evaluation, 'TRANSPORT', transport_for(
        ['stage_invoice_fix', 'deploy', 'close', 'close', 'escalate'], requests))
    out = w.run(args)
    data = json.loads((out / 'summary.json').read_text())
    assert data['passed'] == 3 and data['complete']
    assert data['outcomes']['correct_repair'] == 1
    assert data['outcomes']['correct_untouched_closure'] == 1
    assert data['outcomes']['correct_model_escalation'] == 1
    assert data['outcomes']['runtime_stop'] == 0
    assert len(requests) == len(list((out / 'calls').glob('*.request.json'))) == 5
    for request in requests:
        observation = json.loads(request['messages'][1]['content'])
        text = json.dumps(observation)
        assert 'want' not in text and 'correct_total_cents' not in text
        assert 'fixture_repair' not in text and 'fixture_close' not in text
        assert request['model'] == evaluation.MODEL and request['think'] is False
        assert request['options']['temperature'] == 0
    before = {str(p.relative_to(out)): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    with pytest.raises(FileExistsError):
        w.run(args)
    assert before == {str(p.relative_to(out)): p.read_bytes() for p in out.rglob('*') if p.is_file()}


def test_interruption_preserves_completed_cases_and_inflight_request(tmp_path, monkeypatch):
    args, root = setup_run(tmp_path, monkeypatch)
    actions = iter(['stage_invoice_fix', 'deploy', 'close'])
    def interrupt(req, *a, **k):
        try:
            action = next(actions)
        except StopIteration:
            raise KeyboardInterrupt()
        return io.BytesIO(json.dumps({'model': evaluation.MODEL, 'message': {
            'content': json.dumps({'action': action})}}).encode())
    monkeypatch.setattr(evaluation, 'TRANSPORT', interrupt)
    with pytest.raises(KeyboardInterrupt):
        w.run(args)
    out = next((root / 'runs').glob('invoice-v2-heldout-v1-*'))
    partial = json.loads((out / 'partial-summary.json').read_text())
    assert not partial['complete'] and partial['cases_recorded'] == 1
    assert (out / 'fixture_repair.result.json').exists()
    assert (out / 'calls/call-00004.request.json').exists()
    assert (out / 'calls/call-00004.error.json').exists()
    assert not (out / 'completion.json').exists()
    with pytest.raises(FileExistsError):
        w.run(args)


@pytest.mark.parametrize('action,metric', [('escalate', 'unnecessary_model_escalation'),
                                         ('request_approval', 'approval_request')])
def test_unnecessary_interventions(tmp_path, monkeypatch, action, metric):
    args, root = setup_run(tmp_path, monkeypatch, [fixture_records()[1]])
    monkeypatch.setattr(evaluation, 'TRANSPORT', transport_for([action], []))
    out = w.run(args)
    result = json.loads((out / 'summary.json').read_text())
    assert result['passed'] == 0
    assert result['outcomes'][metric] == 1
    assert result['outcomes']['unnecessary_human_intervention'] == 1


def test_provider_failure_is_retained_runtime_stop(tmp_path, monkeypatch):
    args, root = setup_run(tmp_path, monkeypatch)
    def fail(*a, **k):
        raise OSError('Synthetic provider outage')
    monkeypatch.setattr(evaluation, 'TRANSPORT', fail)
    out = w.run(args)
    result = json.loads((out / 'summary.json').read_text())
    assert result['passed'] == 0 and result['outcomes']['runtime_stop'] == 3
    assert result['outcomes']['provider_or_planning_failures'] == 3
    assert len(list((out / 'calls').glob('*.error.json'))) == 3


def test_wrong_digest_and_missing_attestation_do_not_claim(tmp_path, monkeypatch):
    args, root = setup_run(tmp_path, monkeypatch)
    args.sha256 = '0' * 64
    with pytest.raises(ValueError, match='SHA-256'):
        w.run(args)
    assert not (root / 'runs').exists()
    args.attest_unseen = False
    with pytest.raises(ValueError, match='attestation'):
        w.run(args)


def test_integrity_checks_real_protected_files():
    # No supplied case file is opened. Runs only after wrapper freeze exists.
    if not (HERE / 'freeze.json').exists():
        pytest.skip('Freeze created only after initial test pass')
    frozen, _ = w.verify_integrity()
    assert frozen['version'] == 'invoice-v2'
