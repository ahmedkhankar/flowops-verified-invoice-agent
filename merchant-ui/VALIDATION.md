# Merchant UI validation — separate from frozen evaluation

## Software checks

- Existing self-contained native/public-export suite: **75 passed**. Original fixture-dependent exclusions remain unchanged: `test_native_invoices.py`, `test_native_exam_runner.py`, `test_evaluation_harness.py`.
- Final merchant UI suite: **49 passed**, covering adapter contracts, Streamlit widget journeys, structured issue routing and final review regressions. These checks use real native sessions with mocked transport/scripted decisions or explicitly labelled rules execution; they are not model-performance evidence.
- Covered: complaint in the actual serialized model objective, no inference on ticket creation, stage-without-mutation, deploy then verified closure, locks/refusals, approval confirmation, unnecessary approval preservation, ticket-wide budget, split checks, malformed/unsafe input, provider failures without rules fallback, isolated tickets, navigation, downloads and read-only recorded evidence.
- Protected-source guard pins **39 original native/reference/evidence files** from the existing repository baseline. No engine, verifier, evaluation implementation, old test or saved evidence file was edited.

An initial test invocation encountered incompatible packages injected through the tool environment's Python path. Removing that process-level injection resolved it; no frozen source or dependency requirement was changed. A new adapter test exposed missing title validation on direct adapter calls; the new adapter was corrected, then all 38 checks passed. This was a UI-layer fix, not a historical evaluation alteration.

## Minimal new real-model smoke checks

Final routing/review changes were checked offline, with no further inference. The live integration smoke below was retained from the earlier UI build, before the structured issue selector was added; its invoice path is unchanged. It is not a fresh model evaluation of the final routing layer.

Actual local `qwen3:4b-instruct`, temperature 0, thinking disabled, rules fallback OFF. Each new synthetic scenario was attempted once. No held-out case was run. The same service functions bound to the UI buttons were used; detailed records were retained locally outside the repository.

| New builder-authored demo | Actual selected actions | Saved invoice | Outcome |
|---|---|---|---|
| Invoice total mismatch | inspect → stage_invoice_fix → deploy → verify → close | 39.95 → 40.25; version 0 → 1 | CLOSED_VERIFIED; checks pass; no human approval |
| Locked invoice dispute | inspect → verify → escalate | 25.95 unchanged; locked; version 0 | ESCALATED; discrepancy unresolved; no write |
| Already-correct review | inspect → verify → close | 23.00 unchanged; version 0 | CLOSED_VERIFIED; no human approval |
| Controlled unavailable endpoint | No selected business action | Unchanged | UI Incomplete; native ACTIVE with planner_error; zero fallback |

The controlled outage used an unreachable loopback endpoint without stopping the shared Ollama service. Provider timeout/unsafe-output cases are also covered in offline tests.

**The new already-correct demo closed, but this does not erase the four historical held-out unnecessary approvals.** These inputs and complaint context differ from the protected evaluation; this is integration smoke evidence, not a robustness estimate or new benchmark. The underlying frozen planner/tools were not tuned. No failed historical run was replaced and no automatic closure logic was inserted.

## Browser review

- Actual local HTTP server readiness checked on port 8503.
- Overview, ticket form, staging, repaired timeline, before/after invoices and locked escalation exercised in a real desktop browser.
- Rendered at **1600×900** and **1440×900**; reviewed screenshots showed legible business labels and no horizontal overflow at 1440.
- Browser repair/lock demonstrations deliberately used the persistent **RULES BASELINE** label to avoid duplicating model calls. These screenshots are UI/engine evidence, not fresh Qwen evidence. Qwen execution was checked separately through the same adapter as recorded above.
- Seven widget tests separately exercised the button/form bindings, explicit live enabling, failed live transport, scenario isolation and immutable evidence navigation. Browser interaction plus live adapter checks do not constitute a browser-driven live-model recording.
- Screenshots and detailed local smoke audits are excluded from the Git update. No video or synthetic narration was generated for this task.

## Remaining limits

Final focused regressions prove non-invoice categories/unknown categories cannot create sessions or start modifications, complaint text cannot grant approval/unlock/expand tools, approval at the final action is shown as Incomplete, native tool failure is not falsely described as exhaustion, and untrusted display text is not rendered as Markdown. The audit includes detached latest observation and initial state. Routing is operator-selected, not an AI classifier or automatic semantic filter; an incorrectly selected category remains a limitation.

Synthetic merchant operations only. No real POS, payments, user authentication, customer data, enterprise permissions or measured savings. Tickets are in-memory per browser session; export before leaving. Run Agent renders after its loop; Step Through is the best narration control. A requested approval is not autonomous resolution. A failed or exhausted attempt is not silently repaired. Input pattern checks are not universal PII anonymisation; only synthetic text is allowed. Model identity is provider-reported, not independently attested.

Historical result scopes remain **16/20 post-freeze held-out**, **10/12 known diagnostic**, **12/12 known-set rules baseline**, **126 historical full native tests**, and **75 public-export tests**. New UI checks do not change or pool these figures.
