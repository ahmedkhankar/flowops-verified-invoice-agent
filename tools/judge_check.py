#!/usr/bin/env python3
"""Read-only, judge-facing verification for the sanitized FlowOps repository.

No inference, network, file changes, or real payment operations are performed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'versions' / 'invoice-v2'


def integrity_check():
    manifest = json.loads((ROOT / 'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))
    files = manifest['files']
    inventory = (ROOT / 'PUBLICATION_INVENTORY.txt').read_text(encoding='utf-8').splitlines()
    assert manifest['algorithm'].lower() == 'sha256'
    assert inventory == sorted(inventory), 'Inventory order differs'
    assert len(inventory) == len(set(inventory))
    assert set(files) == set(inventory) - {'PUBLICATION_MANIFEST.json'}, 'Manifest/inventory mismatch'
    for name, expected in files.items():
        path = ROOT / name
        assert path.is_file() and path.resolve().is_relative_to(ROOT), 'Missing/invalid path: ' + name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f'Hash mismatch: {name}'
    print(f'PASS integrity: {len(inventory)} inventoried files; {len(files)} verified content hashes.', flush=True)


def run(cmd, cwd):
    print('RUN:', ' '.join(cmd), flush=True)
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f'Check exited with status {result.returncode}: {cmd}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--with-tests', action='store_true', help='Run self-contained pytest subset (requires pytest; Streamlit for 4 dashboard cases)')
    args = p.parse_args()
    integrity_check()
    run([sys.executable, '-B', '-m', 'flowops.cli', '--all', '--planner', 'rules'], NATIVE)
    print('PASS offline synthetic rules CLI. This is NOT Qwen inference.', flush=True)
    if args.with_tests:
        if importlib.util.find_spec('streamlit') is None:
            print('WARNING: Streamlit is not installed: dashboard module will skip; do not claim 75 fresh passes.', flush=True)
        run([sys.executable, '-B', '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider',
             '--ignore=tests/test_native_invoices.py',
             '--ignore=tests/test_native_exam_runner.py',
             '--ignore=tests/test_evaluation_harness.py'], NATIVE)
        print('PASS selected tests. Read the displayed pass/skip counts as reported.', flush=True)
    print('DONE: no model calls, private held-out files or payment systems used.', flush=True)


if __name__ == '__main__':
    main()
