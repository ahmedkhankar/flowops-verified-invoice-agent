# FlowOps Invoice v2

A separately versioned extension of the feedback-v1 workflow engine. This is a
simulated merchant operations process, not a production payment integration.

## Native behaviour

- `InvoiceState` persists unit prices/quantities, VAT, stored total, lock, version
  and optional actual split allocation. Derived line amounts are not persisted twice.
- `invoice_case` mechanically converts external invoice inputs. `want` never enters
  operational state, tool instructions or model observations.
- Integer workers propose changes; a separate Decimal verifier checks persisted results.
- The existing single-use capability and human-approval mechanisms remain in place.
- Merchant-system locks are checked in the trusted deployment service, even with a
  legitimate capability or a lock imposed after staging. Refusals are structured data.
- The model selects actions; no automatic rules fallback is enabled. Rules runs are
  explicitly separate offline baselines, never model results.
- Correct invoices may close unchanged after fresh checks. Unsupported problems end
  with an auditable escalation/review record, not a fabricated successful repair.
- Original split cases continue through the same staged engine with real split checks.

## Tests (run versions in separate processes)

From the original project root:

```bash
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider
```

From `versions/invoice-v2/`:

```bash
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 ../../.venv/bin/python -m pytest tests -q -p no:cacheprovider
```

Use explicit test paths. An unqualified recursive pytest invocation at the parent
root tries to import both versions' same-named modules into one process; that is not
a supported test layout. Version imports must never be mixed.

## Evaluation

Supported native entry point: `scripts/evaluate_invoice_exam.py` in this workspace.
It imports only v2 source and implements no merchant-backend override. The previous
external kit is preserved as historical evidence, including its broken override.
The copied legacy six-case recorder exists for regression compatibility tests; use
the original root recorder for historical feedback-v1 diagnostics.

All live evaluations require a new v2 freeze and exact installed model digest.
Requested model: `qwen3:4b-instruct`; temperature 0; thinking disabled; fallback OFF.
Every case records requests, structured responses, actions, tool results, state,
verification, terminal audit and scoring. Output directories are exclusive and never
reused. The first live run is preserved, even if it fails.

The known twelve-case exam is diagnostic/regression data, not held-out evaluation.
No independent/unseen results are claimed. Further runs or development after the
first live exam require a new instruction from the project owner.
