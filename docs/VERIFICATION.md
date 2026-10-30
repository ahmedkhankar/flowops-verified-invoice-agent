# Staging verification

Fresh validation used the **existing external project venv**, no installation, and a separate subprocess for each check. No inference ran. Each worker installed a Python audit hook rejecting outbound connect, DNS and sendto events. Bytecode and pytest cache writes were disabled; temporary/home outputs were redirected inside staging and cleaned afterward. Tests imported the staged native engine with an explicit module-path assertion.

## Executed results

- Clean self-contained native subset: **75 passed in 1.02s**, exit 0. Exact pytest arguments: `tests -q -p no:cacheprovider --ignore=tests/test_native_invoices.py --ignore=tests/test_native_exam_runner.py --ignore=tests/test_evaluation_harness.py`.
- Native CLI `--all --planner rules`: exit 0; split_bill, wrong_total_and_split and rounding closed verified; security_approval paused before execution; fake_fix and outage escalated. Rules are not AI performance evidence.
- Three fresh public native synthetic smoke checks: repair closed verified; locked mismatch escalated with unchanged state; correct invoice closed with unchanged state. All PASS, exit 0.
- Streamlit AppTest: initial render, full saved repair replay, preserved already-correct failure replay, and all three derivative terminal-status consistency checks PASS, exit 0. A benign bare-mode missing-ScriptRunContext warning is retained. No HTTP hosting or persistent server is claimed.

## Failed attempt retained, not hidden

An earlier staged attempt excluded the two external-case-dependent modules but still included the historical evaluation harness: **75 passed, 4 failed in 1.42s**, exit 1. Failures were missing deliberately excluded historical `runs/ollama-live-...` fixtures, not a reason to copy private data or fabricate results. The original sanitized failure log remains `validation/initial-evidence-dependent-attempt.txt`. The final clean subset additionally excludes that entire historical harness module. **This is not a full 126-test historical suite pass.** The original excluded test files remain unmodified as reference.

Logs and structured results: `validation/pytest.txt`, `validation/cli.txt`, `validation/native.txt`, `validation/ui.txt`, `validation/checks.json`. `tools/validate_staging.py` documents the exact offline worker invocations and environment guards. No network attempt, model call, package install, Git init/commit or publication was performed.

`validation/sanitization.json` records the final heuristic secret/identifier scan and original allowlist source-hash comparison. `provenance/BASELINE_STAGING_SHA256.json` preserves the earlier closed 56-file snapshot; `PUBLICATION_MANIFEST.json` is the authoritative closed inventory of this amended candidate, excluding itself; verify each recorded SHA-256 and reject unexpected files. Its own digest is returned separately in the handoff. Original integrity manifests are preserved references, not a claim that the complete private evidence tree can be verified from this subset.

## Final candidate scope

No application source, test or original replay data changed from the validated 56-file baseline. The earlier 75-test pass is retained evidence, not a fresh full-suite claim. Changes are limited to publication documentation, relocating the old staging inventory as provenance, adding the approved self-contained held-out HTML and producing final inventory/security/manifests. See RELEASE_SCOPE.md. Do not run the historical staging finaliser to regenerate original freezes or overwrite this candidate.
