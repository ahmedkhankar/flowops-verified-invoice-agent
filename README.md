# FlowOps — Native Invoice v2

**Local-only sanitized repository staging. Nothing has been published, initialized as Git, or committed. External publication requires owner approval.**

A simulated merchant-operations workflow: a planner selects permitted actions; trusted tools propose and deploy corrections; a separate Decimal verifier checks persisted invoice values before closure. No real POS or payment access.

## Selected held-out evidence

Open [the self-contained held-out viewer](evidence/heldout-replay.html) in a browser. It displays only h_001 repair, h_013 locked escalation and h_019 unnecessary-approval failure. It never calls a model or executes tools. Its saved values, rationales, expected outcomes and source hashes are a selected disclosure, not full private raw traces. See [publication scope](docs/RELEASE_SCOPE.md).

## Start here

- [Setup and commands](docs/SETUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security and privacy](docs/SECURITY.md)
- [Evaluation and evidence boundaries](docs/EVALUATION.md)
- [Staging verification](docs/VERIFICATION.md)

The native source is under `versions/invoice-v2/`. A safe saved diagnostic replay is `public-demo/app.py`: it reads a deliberately reduced derivative of three protected synthetic diagnostic records, never constructs a planner and never executes tools. Original presentation source remains at `presentation/invoice-ui-v1/` for reference, but its full private/historical integrity dependencies are absent. **Use the public-demo entry point, not that original presentation app.**

## Reported results — preserve the denominators

| Evaluation | Correct outcomes | Repair | Locked model escalation | Unchanged closure |
|---|---:|---:|---:|---:|
| Supplier-attested post-freeze held-out, single run | **16/20** | 12/12 | 4/4 | **0/4** |
| Separate known diagnostic set | **10/12** | Not combined with held-out | Not combined | Not combined |

Held-out run: **77 model calls; 0 tool failures; 1 rejected tool action; 0 invalid closures; 0 runtime stops; 4 unnecessary human-approval requests.** These four reviews are failures of autonomous unchanged closure, not successful resolutions. Requested model: `qwen3:4b-instruct`, temperature 0, thinking disabled, rules fallback off. Provider-reported model identity is not independent execution attestation.

The held-out cases were authored after freeze by a **separate ChatGPT conversation whose author was aware of prior weaknesses**. Independence is supplier-attested, not externally certified. One synthetic run is not certification, general accuracy, measured productivity savings, production readiness, or evidence that the model outperforms rules. The known diagnostic set remains diagnostic, not unseen.

These aggregate results were supplied for the release; staging did not rerun inference or independently recompute held-out outcomes from private evidence. Full private held-out inputs, grading fixtures, raw model requests/responses and complete traces remain excluded. The added HTML discloses only selected display records, including their expected-outcome labels. Those three examples do not independently substantiate the complete 20-case aggregate. The Streamlit public-demo viewer still shows only known diagnostic examples.

## Integrity is scoped honestly

`SOURCE_ALLOWLIST.json` records explicit source files, source/staged SHA-256 and documented sanitization or exclusions. `PUBLICATION_MANIFEST.json` inventories this final candidate. `provenance/BASELINE_STAGING_SHA256.json` is the unchanged prior 56-file snapshot, not a checksum manifest for this amended tree. Neither is a replacement for the original freeze. Historical integrity manifests and wrapper source are retained as reference, not rewritten to make missing private evidence appear verified. Full original wrapper/native diagnostic verification **will not work in this reduced tree**; see the evaluation document.

No license has been invented. Owner must review licensing, third-party rights, and all external contents before publication.
