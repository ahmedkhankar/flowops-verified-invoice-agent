# FlowOps | Judge quickstart and reproducibility

**Challenge:** Autonomous Enterprise (HUMAIN Future AI Builders)
**Scope:** Simulated merchant invoices only. No POS/payment connectivity, real merchant/customer records, or production claim.

## Choose a verification path

| Path | Time/requirements | What it establishes | What it does **not** establish |
| --- | --- | --- | --- |
| **A. Read-only review** | Browser, no installation | View the saved Qwen decision sequence for `h_001`, `h_013`, `h_019` | Fresh inference or full 20-case accuracy |
| **B. Offline check** | Python 3.11+; no install | Verify packaged file hashes; run the rules-based CLI on six synthetic cases | Model-based performance |
| **C. Software tests** | Python 3.11+, pytest and Streamlit installed | Re-run the self-contained test subset, including dashboard tests | Historical full 126-test suite or held-out model run |

### A. Review recorded model decisions (no installation)

Download [`evidence/heldout-replay.html`](evidence/heldout-replay.html) from GitHub using **Download raw file**, then open the downloaded file in a web browser. GitHub's code viewer itself will not run the interactive HTML. The file is self-contained and read-only.

- **h_001:** incorrect invoice total; observe proposed staging (no persisted mutation), deployment, independent verification and verified closure.
- **h_013:** locked invoice; verify that the stored value and version remain unchanged while the agent escalates.
- **h_019:** already correct invoice; observe the unnecessary approval request, counted as a failure.

These are selected **recorded** Qwen actions, not new inference. The separate Streamlit saved diagnostic viewer (`public-demo/app.py`) concerns known diagnostic examples, not the 20-case held-out run.

### B. Run a no-download local check

In a Terminal at the repository root:

```bash
python3 -B tools/judge_check.py
```

This performs a SHA-256 inventory check and runs the built-in **rules-based** synthetic CLI in a subprocess. It is intentionally offline and never starts Ollama or changes invoices outside the simulator. A passing rules check is *not* evidence of Qwen's performance.

### C. Run the self-contained software tests

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r versions/invoice-v2/requirements.txt
.venv/bin/python -B tools/judge_check.py --with-tests
```

The script checks the inventory, runs the rules CLI and then invokes the documented test subset. The previously recorded fully provisioned result was **75 passes**. If `streamlit` is absent, its dashboard test module is skipped; a smaller pass count must **not** be reported as 75. The dependencies are bounded version ranges, not a cross-platform lockfile. Installation requires access to Python package repositories; once installed, these checks need no model server.

Optional read-only Streamlit diagnostic viewer:

```bash
.venv/bin/python -m streamlit run public-demo/app.py --server.address 127.0.0.1 --server.port 8513 --browser.gatherUsageStats false
```

Open `http://127.0.0.1:8513`. It intentionally displays a reduced replay and **does not** call the model or change business data.

## Reported performance and provenance

| Evaluation | Correct outcomes | Details |
| --- | --- | --- |
| First post-freeze **synthetic held-out** Qwen run | **16/20 (80%)** | 12/12 repairs; 4/4 locked escalations; **0/4** already-correct unchanged closures |
| Separate **known** diagnostic | **10/12** | Not held-out; not mixed with the 20-case score |
| Rules baseline on known diagnostic | **12/12** | Different decision mechanism; not evidence that the AI outperforms rules |

20-case run: **77 recorded Qwen model calls**, 0 tool failures, 1 rejected action, 0 invalid closures, 0 runtime stops, 4 unnecessary approval requests. The cases were authored in a separate ChatGPT conversation after the implementation freeze, by an author aware of earlier weaknesses; independence is supplier-attested, not blinded or independently certified. The complete private cases/raw traces are not shipped here. Therefore **the exact 16/20 result cannot be freshly reproduced from this privacy-limited repository**. This limitation must remain visible in judging.

## Technical boundaries

- The agent chooses a *registered action*; trusted Python tools enforce authorization and business locks.
- Corrections are first staged; deployment independently checks permissions and invoice locks.
- A separate Decimal-based verifier examines persisted state before a case may close.
- `versions/invoice-v2/` contains the engine. Selected original historical wrappers and manifests are references whose omitted fixtures prevent full historical re-execution.
- No model weights are included. Running fresh `qwen3:4b-instruct` inference requires a separate local Ollama installation/model and should be treated as a **new** experiment, not a reproduction of the frozen 20-case run.

## How this maps to HUMAIN's six criteria

| Criterion | Evidence to inspect |
| --- | --- |
| Task Performance | 16/20 aggregate, separate subgroup denominators, selected correct and failed recorded cases |
| Robustness & Adaptation | Authoritative locks, rejection of unauthorized action, staged deployment, independent persisted-state checks |
| Evaluation & Iteration | Recorded 0/3 → 3/3 diagnostic engineering iteration; 10/12 known Qwen diagnostic versus 12/12 rules baseline; honest held-out limitations |
| Technical Judgment & Creativity | Small local Qwen planner + policy-constrained Python actions + separate verifier; no pretended real payment integration |
| Engineering Quality | SHA-256-checked repository inventory, self-contained software checks and transparent exclusions |
| Communication | This quickstart, README, selected interactive replay, slides and narrated demonstration submitted separately |

**Access:** A private repository requires GitHub authorization to view or clone. If you can see these files as an invited judge, this file grants no additional permissions. Ask the project submitter for access before evaluating the source.
