# Setup

Python 3.11+ is recommended. The recorded validation used Python 3.12. This repository does not bundle a virtual environment. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r versions/invoice-v2/requirements.txt
```

Dependencies specify version ranges, not a reproducible lockfile.

## Offline native CLI (rules, not AI)

```sh
cd versions/invoice-v2
../../.venv/bin/python -B -m flowops.cli --all --planner rules
```

The built-in six synthetic compatibility scenarios include escalation and a policy-approval pause; not every scenario is expected to close. To load native invoices, use native `initial_bill.line_items` with `unit_price_cents` and positive integer `quantity`, plus `tax_bps`, `stored_total_cents`, `locked` and optional `split_cents`; see `flowops/invoices.py` and `flowops/models.py`. The offline smoke check constructs three fresh synthetic examples through `invoice_case` without any private/external case file.

## Saved diagnostic viewer

From the repository root:

```sh
.venv/bin/python -B -m streamlit run public-demo/app.py --server.address 127.0.0.1 --server.port 8513 --browser.gatherUsageStats false
```

Choose bill04 (repair), bill09 (lock), or bill11 (unnecessary approval). Move the slider through saved decisions. This reduced UI has no live execution or approval controls. Recorded verification exercised Streamlit AppTest renders and interactions; it did not test a persistent HTTP deployment.

`versions/invoice-v2/app.py` is the original compatibility dashboard: defaults to a rules baseline, supports optional inference controls, and is not the native saved-evidence presentation. Its Ollama default alias differs from the evaluation model. Do not treat a default UI setting as experiment provenance. The published validation records do not include a fresh live-AI execution.

## Offline software checks

From `versions/invoice-v2/`, using your installed interpreter:

```sh
python -B -m pytest tests -q -p no:cacheprovider --ignore=tests/test_native_invoices.py --ignore=tests/test_native_exam_runner.py --ignore=tests/test_evaluation_harness.py
```

Three original modules depend on deliberately excluded external cases or historical runs; they remain unchanged rather than weakened. The full historical suite is not self-contained in this public export. `tools/validate_staging.py` documents historical validation against the source project's existing `.venv`; it is not a portable repository installer. Each check runs in a fresh process with outbound Python network events blocked.
