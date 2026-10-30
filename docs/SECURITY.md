# Security and Privacy

FlowOps is a **local research prototype** for simulated merchant invoice operations. It does not connect to real payment providers, POS systems, merchant accounts, or live customer data. This document describes the controls implemented and their limitations; it is **not a production security certification**.

## Operational safeguards

- The Qwen planner can select registered operations but cannot grant itself authorization, choose arbitrary code or override merchant invoice locks.
- Trusted Python code validates requested actions. Runtime-issued, single-use capabilities bind permitted mutations to an authorized action.
- Proposed invoice corrections are staged before deployment; deployment rechecks permissions and locks before changing persisted values.
- A separate Decimal-based verifier inspects persisted invoice state before successful closure. Unsupported changes result in review or escalation rather than fabricated success.
- Read-only saved-replay demonstrations never invoke Qwen or dispatch business operations.

## Privacy and included data

The repository contains synthetic invoice examples, a reduced diagnostic replay and a selected read-only held-out HTML viewer. The held-out viewer intentionally exposes three examples (`h_001`, `h_013`, `h_019`), including invoice values, action sequences, model rationales, outcomes and source hashes. These are recorded evaluation disclosures, not real customer transactions.

Private full model traces, raw held-out grading fixtures, complete request/response envelopes, credentials, `.env` files, local virtual environments, presentation slides and demo videos are not part of this package. Some historical integrity metadata and sanitized test logs remain to document provenance and validation boundaries. See [repository scope](RELEASE_SCOPE.md) and [evaluation limitations](EVALUATION.md).

A static scan found no obvious real credentials or personal contact details in the packaged files. Static inspection cannot guarantee the absence of every disclosure. A reserved `.test` example in a security regression test is synthetic, not a live credential.

## Threat-model limitations

The authorization boundary operates **inside a Python process**; it does not protect against an attacker who controls that process or the host machine. The application has not been assessed for real payments, multi-tenant authorization, production deployment or adversarial network environments. Testing and results apply to the described synthetic setting only.

## Access and licensing

Access to the repository is governed by GitHub permissions. No open-source license has been added; repository access does not itself grant a general right to redistribute the code.
