"""Offline tests of the diagnostic recorder, freeze guard and result attribution.

Synthetic HTTP fixtures are NOT live-model benchmark evidence.
"""
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import sys
from urllib import request

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'runs/ollama-live-20261030T055320Z'


def fixture_project(tmp_path):
    for directory in ['flowops', 'scripts', 'cases', BASELINE]:
        source = ROOT.parents[1] / directory if directory == BASELINE else ROOT / directory
        shutil.copytree(source, tmp_path / directory)
    paths = ['flowops/engine.py', 'flowops/planner.py', 'flowops/tools.py',
             'flowops/fixer.py', 'flowops/verifier.py', 'flowops/models.py',
             'scripts/evaluate_ollama_local.py']
    freeze = {'files': {name: hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in paths}}
    frozen = tmp_path/'freeze.json'
    frozen.write_text(json.dumps(freeze))
    return frozen


@pytest.mark.parametrize('repeat', [False, True])
def test_full_harness_counters_trace_and_baseline_preservation(tmp_path, monkeypatch, repeat):
    frozen = fixture_project(tmp_path)
    baseline = tmp_path/BASELINE
    before = {p.name: p.read_bytes() for p in baseline.iterdir() if p.is_file()}
    cases = json.loads((tmp_path/'cases/demo_cases.json').read_text())
    sequences = {
        'split_bill': ['stage_split_fix', 'deploy', 'verify', 'close'],
        'wrong_total_and_split': ['stage_invoice_fix', 'deploy', 'stage_split_fix', 'deploy', 'close'],
        'fake_fix': ['stage_split_fix', 'deploy', 'stage_split_fix', 'deploy', 'escalate'],
        'outage': ['escalate'],
        'rounding': ['stage_invoice_fix', 'deploy', 'stage_split_fix', 'deploy', 'close'],
    }
    queues = {c['request']: iter(sequences.get(c['case_id'], [])) for c in cases}
    seen = []

    def fake_http(req, *args, **kwargs):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith('/api/version'):
            data = {'version': 'offline-fixture'}
        elif url.endswith('/api/tags'):
            data = {'models': [{'name': 'qwen3:4b-instruct', 'digest': 'fixture-not-a-real-model'}]}
        elif url.endswith('/api/ps'):
            data = {'models': []}
        elif url.endswith('/api/chat'):
            payload = json.loads(req.data)
            seen.append(payload)
            obs = json.loads(payload['messages'][1]['content'])
            action = 'inspect' if repeat else next(queues[obs['objective']])
            data = {'model': 'qwen3:4b-instruct', 'message': {
                'content': json.dumps({'action': action, 'reason': 'offline fixture'})}}
        else:
            raise AssertionError('Unexpected network destination: ' + url)
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(request, 'urlopen', fake_http)
    monkeypatch.setattr(sys, 'argv', ['evaluate', '--freeze-file', str(frozen), '--label', 'diagnostic-test'])
    namespace = runpy.run_path(str(tmp_path/'scripts/evaluate_ollama_local.py'), run_name='__main__')
    out = namespace['OUT']
    summary = json.loads((out/'summary.json').read_text())
    metadata = json.loads((out/'metadata.json').read_text())
    assert summary['rules']['resolved'] == 3
    ai = summary['ollama']
    assert ai['wrong_closes'] == ai['approval_violations'] == 0
    assert ai['approval_pauses'] == 1
    if repeat:
        assert ai['resolved'] == ai['selected_escalations'] == 0
        assert ai['runtime_enforced_stops'] == 5
        assert ai['rejected_actions'] == 55 and ai['planner_calls'] == 60
    else:
        assert ai['resolved'] == 3 and ai['selected_escalations'] == 2
        assert ai['runtime_enforced_stops'] == ai['rejected_actions'] == 0
        assert ai['planner_calls'] == 20
    assert len(seen) == ai['planner_calls']
    assert metadata['rules_fallback'] is False
    assert metadata['frozen_files_and_original_results_unchanged'] is True
    assert 'Diagnostic' in metadata['provenance']
    assert all(p['options']['temperature'] == 0 for p in seen)
    assert all(json.loads(p['messages'][1]['content'])['tools'] for p in seen)
    for detail in ai['cases_detail']:
        row = json.loads((out/('ollama-'+detail['case_id']+'.json')).read_text())
        assert len(row['trace']) == detail['planner_calls']
        for step in row['trace']:
            assert 'request' in step and 'response' in step
            assert 'tool_result' in step and 'verification_after' in step
    assert {p.name: p.read_bytes() for p in baseline.iterdir() if p.is_file()} == before


def test_freeze_guard_blocks_changed_code_before_any_network(tmp_path, monkeypatch):
    frozen = fixture_project(tmp_path)
    (tmp_path/'flowops/tools.py').write_text('# changed after freeze\n')
    monkeypatch.setattr(sys, 'argv', ['evaluate', '--freeze-file', str(frozen)])
    monkeypatch.setattr(request, 'urlopen', lambda *a, **k: pytest.fail('Network before freeze validation'))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(tmp_path/'scripts/evaluate_ollama_local.py'), run_name='__main__')
    assert exc.value.code == 2


def test_original_cases_cannot_be_declared_independent(tmp_path, monkeypatch):
    frozen = fixture_project(tmp_path)
    monkeypatch.setattr(request, 'urlopen', lambda *a, **k: pytest.fail('Network before provenance validation'))
    monkeypatch.setattr(sys, 'argv', ['evaluate', '--freeze-file', str(frozen),
                                    '--cases-file', str(tmp_path/'cases/demo_cases.json'), '--independent-cases'])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(tmp_path/'scripts/evaluate_ollama_local.py'), run_name='__main__')
    assert exc.value.code == 2
