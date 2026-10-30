# Security, privacy and publication boundary

This is a local-only staging artifact, not an approved public repository. No Git initialization, commit, publish, network installation, inference or private case reading is part of preparation.

## Application boundary

The model chooses registered actions, not actor identity, authorization, arbitrary code or approval. Runtime-issued single-use capabilities bind mutations to an authorized turn. Independent verification and human approval are separate gates. Merchant locks are authoritative at deployment and cannot be overridden by approval. This in-process Python boundary does not defend against an adversary controlling the Python process. Simulation is not a real payment integration or production security assessment.

## Explicit exclusions

No raw held-out inputs/cases/labels/traces, request or response envelopes, credentials, environment files, virtualenv, arbitrary personal paths, whole agent-state directory, external exam kit, historical raw runs, PDFs or slide decks. Only one explicitly inspected nonsecret native freeze manifest is retained under `.hermes/freezes/`; it is reference metadata, not a wholesale agent-state export.

Three known synthetic diagnostic files were inspected and checked against their original protected hashes. Only selected state/action/tool/check fields were extracted to `public-demo/diagnostic-replay.json`. Raw provider envelopes, prompts, audit reports, labels/oracles and full observations were excluded. Source hashes identify provenance without bundling original raw artifacts.

The staged source first-name references were replaced with `the project owner` in two explicitly logged derivatives; source files were not edited. Original UI/wrapper READMEs containing personal paths were excluded and replaced by these public instructions.

The retained initial failure log replaces local temporary-directory usernames with `local-user`. A reserved `.test` credential-in-URL fixture is deliberately retained unchanged as an adversarial regression test; it is synthetic, not a real account or email. Reserved example/test email domains are excluded from the email-finding category.

The local scan reports categories/counts and file paths only, never matching secret values. It checks personal paths/identifiers, common token/key forms, private-key headers, and high-risk credential assignments. This is a heuristic scan, not a guarantee; owner review remains necessary before any external publication. No license/ownership clearance is implied.
