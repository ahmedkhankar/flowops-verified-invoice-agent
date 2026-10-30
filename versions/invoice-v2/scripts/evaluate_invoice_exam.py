#!/usr/bin/env python3
"""Native Invoice v2 diagnostic. No exam-specific business overrides or fallback."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib import request

WORKSPACE = Path(__file__).resolve().parents[1]
PROJECT = WORKSPACE.parents[1]
sys.path.insert(0, str(WORKSPACE))
from flowops import engine, planner, models
from flowops.invoices import invoice_case
from flowops.evaluation import MODEL, BASE, evaluate, aggregate


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files(root, hashes):
    for name, expected in hashes.items():
        if digest(root/name) != expected:
            raise RuntimeError('Hash mismatch; do not run: ' + name)


def write_new(path, value):
    with path.open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def get_json(path):
    with request.urlopen(BASE + path, timeout=10) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['rules', 'ollama'], required=True)
    parser.add_argument('--exam', type=Path, default=PROJECT/'external_exam_kit/exam.json')
    parser.add_argument('--freeze-file', type=Path)
    parser.add_argument('--max-steps', type=int, default=12)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.mode == 'ollama' and not args.freeze_file:
        parser.error('Live evaluation requires a frozen implementation')
    if args.max_steps != 12:
        parser.error('This diagnostic protocol is frozen at 12 steps')
    for module in [engine, planner, models]:
        if Path(module.__file__).resolve().parent != WORKSPACE/'flowops':
            raise RuntimeError('Mixed implementation imports are prohibited')
    historical = json.loads((WORKSPACE/'historical-integrity.json').read_text())['files']
    verify_files(PROJECT, historical)
    frozen = json.loads(args.freeze_file.read_text()) if args.freeze_file else None
    if frozen:
        verify_files(PROJECT, frozen['files'])
        if args.mode == 'ollama' and frozen['protocol']['model'] != MODEL:
            raise RuntimeError('Wrong frozen model')
    exam_bytes = args.exam.read_bytes()
    records = json.loads(exam_bytes)
    if not isinstance(records, list) or len({r['name'] for r in records}) != len(records):
        raise ValueError('Exam requires unique records')
    if any(r['want'] not in {'fix', 'escalate', 'close_untouched'} for r in records):
        raise ValueError('Unknown expected-outcome label')
    # This conversion does not access want or any computed oracle.
    cases = [invoice_case(record) for record in records]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = args.output or PROJECT/'runs'/('invoice-v2-exam-' + args.mode + '-' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    metadata = {'implementation_version': 'invoice-v2', 'mode': args.mode,
                'started_utc': datetime.now(timezone.utc).isoformat(),
                'exam_sha256': hashlib.sha256(exam_bytes).hexdigest(),
                'exam_file': str(args.exam.resolve()),
                'freeze': frozen, 'freeze_sha256': digest(args.freeze_file) if frozen else None,
                'requested_model': MODEL if args.mode == 'ollama' else None,
                'temperature': 0, 'thinking': False, 'rules_fallback': False,
                'max_steps': 12, 'provenance': 'Known external diagnostic exam; not held-out',
                'business_lock': 'Native InvoiceState and trusted deployment service; no overlays',
                'git_commit': None, 'git_reason': 'Source project is not a Git repository'}
    write_new(out/'metadata.json', metadata)
    rows = []
    started = time.monotonic()
    try:
        if args.mode == 'ollama':
            runtime = {'server': get_json('/api/version'), 'installed': get_json('/api/tags')}
            matches = [m for m in runtime['installed'].get('models', []) if m['name'] == MODEL]
            if len(matches) != 1 or matches[0]['digest'] != frozen['protocol']['model_digest']:
                raise RuntimeError('Exact frozen model digest is not installed; do not download or substitute')
            write_new(out/'runtime.json', runtime)
        for record, case in zip(records, cases):
            selected_planner = (planner.OllamaPlanner(model=MODEL, timeout=180)
                                if args.mode == 'ollama' else planner.RulesPlanner())
            row = evaluate(record, case, selected_planner, max_steps=12)
            write_new(out/(record['name']+'.json'), row)
            rows.append(row)
            print(json.dumps({'case': row['case_id'], 'passed': row['passed'],
                              'actions': row['selected_actions'], 'status': row['report']['status']}, ensure_ascii=False), flush=True)
        verify_files(PROJECT, historical)
        if frozen:
            verify_files(PROJECT, frozen['files'])
        if args.exam.read_bytes() != exam_bytes:
            raise RuntimeError('Exam changed during execution')
        summary = aggregate(rows)
        summary['wall_seconds'] = time.monotonic() - started
        summary['output_directory'] = str(out)
        summary['historical_and_frozen_files_unchanged'] = True
        write_new(out/'summary.json', summary)
        write_new(out/'completion.json', {'finished_utc': datetime.now(timezone.utc).isoformat(),
                                        'complete': True, 'cases_recorded': len(rows)})
        print('SUMMARY ' + json.dumps(summary), flush=True)
        print('FINISHED: ' + str(out), flush=True)
    except BaseException as exc:
        write_new(out/'aborted.json', {'type': type(exc).__name__, 'message': str(exc),
                                     'cases_recorded': len(rows), 'first_attempt_preserved': True})
        raise
    return out


if __name__ == '__main__':
    main()
