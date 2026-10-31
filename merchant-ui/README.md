# Merchant Operations UI

A thin, functional Streamlit interface over the existing frozen Invoice v2 engine. No hosted service, API key, separate agent or new backend is required.

## Launch from the repository root

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r versions/invoice-v2/requirements.txt
.venv/bin/python -B -m streamlit run merchant-ui/app.py --server.address 127.0.0.1 --server.port 8503 --browser.gatherUsageStats false
```

Open **http://127.0.0.1:8503**. Bind only to loopback; GitHub stores source, not a running merchant service. Existing dependencies are reused; no frontend build or paid API is introduced. The repository's `.streamlit/config.toml` supplies the dark theme when launched from its root.

For live AI, install/start Ollama separately and have `qwen3:4b-instruct` available. The UI checks `/api/tags` without inference and reports availability. It does not download a model or start the service. On a machine already provisioned for the frozen evaluation, no new model download is needed. The requested tag can be changed in the ticket form; there is no silent substitute if it is absent. Model identity is provider-reported, not independently attested.

The UI uses local `http://127.0.0.1:11434`, temperature 0, `think:false`, and rules fallback OFF. Requests are server-side. The service adapter accepts only credential-free loopback endpoints; no remote endpoint or API secret is exposed in the browser. The controlled outage check uses an unreachable loopback endpoint instead of disrupting another process's model server.

## Product journey

1. **Overview:** synthetic-environment label, current-session tickets, clear empty state and Create New Ticket.
2. **Create ticket:** choose one of four newly authored synthetic demos, enter a synthetic complaint/title, inspect prices/quantities/VAT and optionally change the stored decimal total. The lock and recorded split are scenario-defined, not user permissions. Confirm synthetic input. Submitting creates a real `WorkflowSession`, but makes no model call.
3. **Ticket workspace:** see complaint, saved/calculated total, lock, version and actual verification. Enable real execution for LIVE MODEL, then use **Step Through** or **Run Agent**. A persistent source label distinguishes LIVE MODEL from a deliberately selected RULES BASELINE ticket. An existing ticket never silently switches source.
4. **Invoice before / after:** itemized original and current saved invoice; VAT, difference, split and version; proposed patches remain separate from persisted changes.
5. **Resolution & audit:** genuine native status, actual step count, checks, human intervention and optional JSON audit. Technical details are collapsed by default.
6. **Evaluation evidence:** unchanged self-contained selected h_001/h_013/h_019 records, explicitly SAVED REPLAY. No planner is constructed and no actions are dispatched. These are not intake scenarios.

## What the complaint actually does

### Structured issue routing, not an AI classifier

The operator selects the issue category. Only **Invoice discrepancy** may create an invoice workflow. **Refund request** and **Fraud / chargeback / open dispute** require human review; **Account modification / unrelated request** is unsupported; **Unclear / needs clarification** and unknown categories require clarification. Blocked submissions create no native session, call no model/tool and cannot be reported as resolved. The adapter rechecks the selected category before execution, and the workspace/audit show it.

This is **structured routing**, not automatic natural-language classification. Operators must select the category accurately; a miscategorised complaint is not detected semantically. Text cannot grant approval, override locks or add tools. Complaint/title/merchant display strings use plain-text rendering rather than active Markdown. No additional model was introduced.

The native `invoice_case()` helper creates a generic objective and ignores complaint text. This UI calls that exact helper and then uses `dataclasses.replace` to append a supported issue category and the operator's untrusted complaint to **`CaseSpec.request`**. `WorkflowSession.observe()['objective']` therefore contains that context, and the real `OllamaPlanner` sends it to Qwen.

This is not general-purpose semantic triage, arbitrary invoice-file parsing or a policy override. Numeric invoice state, locks, checks and trusted tool contracts govern what is possible. Merchant name, synthetic invoice ID and item descriptions are display metadata; prices and quantities are native state. The exact last planning observation (or initial preview before execution) is available in an audit expander. UI-calculated expected totals are display-only and are not injected as oracle answers. Acceptance specifications and grading labels never enter the planner observation.

UI ticket prompts/context are new operational inputs; outcomes are not retroactive improvements to the historical evaluation. All scenarios in `scenarios.json` are builder-authored demonstration data, not relabelled held-out transactions. A two-way equal split is supported; unequal settlement, arbitrary POS files and actual merchant integrations are not.

## Runtime and outcome boundaries

- `service.py` imports the repository's `versions/invoice-v2` package and asserts engine module identity. `FROZEN_SOURCE_SHA256.json` pins the imported native files and historical references/evidence as they existed before this UI work. A mismatch blocks execution; pins are not regenerated to hide a frozen edit.
- Every action uses `WorkflowSession.step()` and its real worker, write capability, authoritative lock and independent verifier. The adapter never applies invoice corrections or forces closure.
- One ticket-wide budget of 12 selected actions is shared by all Step/Run clicks, including after simulated approval. When exhausted without a native terminal outcome, the UI reports **Incomplete**, explicitly preserving the native status; it does not manufacture closure or rewrite engine history.
- A planning/provider failure is **Incomplete**, with no synthetic action or rules fallback. A genuine model-selected escalation is **Escalated**, not a repair. Tool/runtime/verifier failures are not presented as successful escalations.
- An already-correct invoice may still pause for approval. This remains **Awaiting Approval**, not autonomous success, unless the ticket-wide action budget has expired, in which case it is **Incomplete** with no approval control. Optional operator approval requires explicit confirmation and calls native `grant_human_approval`; it does not unlock state or bypass verification. Approval is a simulated role, not enterprise identity/authentication. Audit retains the intervention.
- Initial verification is read-only. It is not falsely shown as a model-selected event. Each timeline entry uses actual selected action/reason, native result, changed state and resulting status. Model rationale can be wrong; it is not policy truth.
- Tickets live in Streamlit's current browser session, not a database. Scenario switches/new tickets create distinct state. No model call occurs simply by switching navigation or opening replay. Long runs finish before the page rerenders; use Step Through to narrate individual actions.

## Privacy and audit export

Use only invented merchant/invoice context. Do not enter real customers, contacts, account secrets or payment data. Input checks reject common email, long payment-number and key patterns; this is not a general-purpose anonymizer or proof that arbitrary text is non-sensitive. The JSON download contains the operator's synthetic complaint and the native state/actions, not API credentials or raw HTTP transport. Review before sharing. No full smoke traces or generated screenshots are committed with the UI.

## Tests

From the repository root after installing existing requirements:

```sh
.venv/bin/python -B -m pytest merchant-ui/tests -q -p no:cacheprovider
.venv/bin/python -B tools/judge_check.py --with-tests
```

Adapter tests use real native operations with mocked transport and labelled scripted decisions. Widget tests exercise real Streamlit forms, navigation and source controls. These are software checks, not AI performance. Minimal new local Qwen smoke attempts are reported separately in VALIDATION.md, without changing 16/20 held-out, 10/12 known diagnostic, 12/12 known rules baseline, historical 126 or the separate 75-test public subset.

If a Python tool environment injects packages from another interpreter through `PYTHONPATH`, clear that variable for the command; do not patch frozen source or mix native-extension installations to work around it.
