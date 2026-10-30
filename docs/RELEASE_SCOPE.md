# Repository Scope and Provenance

This repository contains a reduced, reviewable FlowOps software export, not the complete private development workspace. Its recorded demonstrations and validation materials are included for transparency; they should not be mistaken for fresh inference or unrestricted access to historical evidence.

## Included

- Native invoice engine, registered tool operations, verifier, source documentation and original test sources.
- `public-demo/app.py` with a reduced **known-diagnostic** saved replay.
- `evidence/heldout-replay.html` with selected recorded held-out cases `h_001`, `h_013` and `h_019`, including state transitions, rationales and result labels.
- Validation logs, source-provenance references, integrity records and the manifest for this repository's file contents.

## Not included

The full held-out dataset, private raw request/response traces, private grading fixtures, historical raw runs, real credentials, local virtual environments, personal workspace files, HUMAIN presentation slides and generated videos are not distributed in this repository.

The directory `presentation/invoice-ui-v1/` contains **application UI reference code**, not the HUMAIN slide presentation. It relies on historical dependencies omitted from this export. Use `public-demo/app.py` for the portable saved diagnostic interface.

## Reproducibility and evidence

The public test subset recorded **75 passes**. The historical native-suite **126 passes** are a separate result and cannot be completely rerun from this export because three fixture-dependent test modules require excluded evidence. See [setup](SETUP.md), [verification](VERIFICATION.md) and [evaluation](EVALUATION.md).

The reported post-freeze held-out result is **16/20**, from one synthetic run whose case author knew earlier weaknesses. The separate known diagnostic scored **10/12** for Qwen and **12/12** for the non-AI rules baseline. The three held-out records included here do not independently establish the complete 20-case aggregate.

`PUBLICATION_MANIFEST.json` inventories the files in this repository, excluding the manifest itself. `SOURCE_ALLOWLIST.json` records source provenance and selected sanitized derivatives. `provenance/BASELINE_STAGING_SHA256.json` describes an earlier 56-file export, **not** the current repository. Preserved historical freeze/integrity references may mention external files omitted from the export; they are not proof that those private files are present or verifiable here.

The original native application, its tests and selected recorded evaluation evidence remain unchanged. The merchant-facing UI is a separate addition, not a revised frozen engine.

## Merchant UI integration

`merchant-ui/` adds a thin native-session adapter, Streamlit product interface, new builder-authored demo scenarios, UI-specific tests and documentation. `.streamlit/config.toml` provides the local product theme. The original engine, verifier, evaluation scripts/cases, selected recordings and historical freeze manifests are pinned without alteration in `merchant-ui/FROZEN_SOURCE_SHA256.json`.

UI software checks and minimal new Qwen smoke attempts are separately reported in `merchant-ui/VALIDATION.md`. They do not replace or pool with historical model results. The UI sends complaint context in the operational objective, never expected grading outcomes. Full new smoke records and screenshots are retained locally outside this repository; only a concise non-personal validation summary is included. No slides, video, synthetic voice or new private historical traces are added.

## Licensing

No open-source license is currently provided. No third-party model weights are included or relicensed.
