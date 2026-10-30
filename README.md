# FlowOps — Autonomous Merchant Invoice Operations

FlowOps is an AI-agent prototype I built to investigate merchant invoice discrepancies, execute authorized corrections and verify the persisted result before closing a case. It runs on **synthetic data**, with no connection to real POS, payment or merchant systems.

## How it works

1. **Inspect:** Read invoice line prices, quantities, VAT, stored totals and lock status.
2. **Decide:** A locally served Qwen3 4B planner selects from registered actions. It does not decide its own permissions.
3. **Execute:** Trusted Python tools calculate exact corrections, stage proposed changes and enforce authorization and invoice locks at deployment.
4. **Verify:** A separate Decimal-based verifier checks persisted invoice state before closure. Unsupported or locked cases escalate instead of silently changing data.

The application uses **Python, Ollama, Qwen3 (`qwen3:4b-instruct`) and Streamlit**. The model configuration for the reported live evaluation was temperature 0, thinking disabled and rules fallback off.

## Recorded demonstrations

- **[Held-out case viewer](evidence/heldout-replay.html):** A self-contained HTML file showing three selected recorded Qwen executions: `h_001` (verified repair), `h_013` (locked escalation), and `h_019` (unnecessary human-approval request). Download the HTML file and open it locally to use its interactive replay; GitHub's normal file view shows the source.
- **[Saved diagnostic viewer](public-demo/app.py):** A read-only Streamlit interface for three *known diagnostic* examples. It does not invoke the model or execute business tools. See [setup instructions](docs/SETUP.md).

These views replay recorded evidence; they are **not fresh model inference**. The original application source lives under [`versions/invoice-v2/`](versions/invoice-v2/). Reference UI source is also retained under `presentation/invoice-ui-v1/`, but it requires omitted historical dependencies and is not the portable demo entry point.

## Evaluation

| Evaluation | Correct outcomes | Breakdown |
| --- | ---: | --- |
| Post-freeze synthetic held-out set, first recorded run | **16/20 (80%)** | 12/12 invoice repairs; 4/4 locked escalations; 0/4 already-correct closures |
| Separate, previously known diagnostic set | **10/12** | Diagnostic only; not combined with held-out results |
| Rules baseline on that known diagnostic set | **12/12** | Non-AI baseline; not directly comparable with the held-out result |

The 20-case run recorded **77 model calls**, **0 tool failures**, **1 rejected tool action**, **0 invalid closures**, and **4 unnecessary human-approval requests**. All four already-correct invoice cases failed autonomous unchanged closure. A successful escalation is not a completed repair.

The held-out cases were written after the implementation freeze in a separate ChatGPT conversation; their author was aware of earlier weaknesses. This was not independently blinded or externally certified testing. The repository includes three selected records, **not** the full 20-case traces or a self-contained reproduction of the aggregate score. Results on synthetic cases do not establish production readiness, general reliability or measured business savings.

## Documentation

- [Setup and reproducible public checks](docs/SETUP.md)
- [System architecture](docs/ARCHITECTURE.md)
- [Security and privacy boundaries](docs/SECURITY.md)
- [Evaluation methodology and limitations](docs/EVALUATION.md)
- [Validation evidence](docs/VERIFICATION.md)
- [Repository scope and provenance](docs/RELEASE_SCOPE.md)

**Testing:** 75 self-contained public-export tests passed in the recorded validation. A separate historical native suite reported 126 passes, but that complete suite cannot be reproduced from this deliberately reduced repository. See the testing documentation for the exact exclusions.

**License:** No open-source license is currently provided. Model weights and private evaluation fixtures are not included.
