# Architecture

`observe persisted state → planner selects action → authorize one action → execute trusted tool → independently verify → replan / approval / escalation / closure`

- `flowops/models.py`: native invoice state, exact integer cents, unit prices and quantities; optional actual split allocation; merchant lock and version.
- `flowops/invoices.py`: mechanical intake conversion. Expected outcome labels do not become operational instructions.
- `flowops/planner.py`: rules baseline, Ollama and hosted adapters. Rules are explicitly non-AI. Provider metadata is a claim, not certification.
- `flowops/engine.py`: state transitions, allowed-action feedback, proposal staging, single-use capabilities, approval gates, bounded execution, audit trail and fail-safe outcomes.
- `flowops/tools.py` and `fixer.py`: trusted operations and proposals. Stage does not mutate persisted invoice values; deploy rechecks the lock even after authorization.
- `flowops/verifier.py`: separate Decimal-based persisted-state verification. Closure requires fresh passing checks, no pending proposal, and appropriate approval. A correct invoice can close unchanged.
- `flowops/evaluation.py`: diagnostic recording and scoring, separate from business logic. Expected labels belong to scoring.
- `evaluation/heldout-v1/run.py`: preserved orchestration/reference source with first-attempt claims, overlap checks, recorder and freeze gates. Its private historical dependencies are not bundled.
- `presentation/invoice-ui-v1/`: preserved original presentation implementation, not runnable with this subset of historical evidence.
- `public-demo/`: new reduced offline presentation over explicit diagnostic derivatives. It imports only Streamlit/JSON/path handling, not engine/planner code. No executable replay or new outcomes are manufactured.

Code-separated workers/verifier do not imply independent authorship or third-party evaluation. In-memory simulated business state is not a deployed merchant backend.
