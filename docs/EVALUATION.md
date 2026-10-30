# Evaluation and evidence boundaries

See the top-level README for the supplied held-out 16/20, subgroup denominators, four unnecessary approvals and 77-call counters. The known diagnostic 10/12 is separate. No new inference was authorized or performed while staging; software/UI checks are not new model-performance evidence. A separate ChatGPT author knew earlier weaknesses; post-freeze authorship and non-exposure are supplier attestations, not independent certification.

## Preserved manifests are not public verification receipts

- `.hermes/freezes/invoice-v2.json`: original native freeze, including references to external diagnostic cases and validation metadata not bundled here.
- `versions/invoice-v2/historical-integrity.json`: original historical dependency map; many historical source/run files are intentionally absent.
- `presentation/invoice-ui-v1/protected-files.json`: original broad historical/source/diagnostic integrity scope; excluded evidence is not recreated, redigested or silently marked verified.
- Original UI `release.json` and `release-sha256.txt`: provenance/reference only. No claim that the original release is complete in this export.
- `evaluation/heldout-v1/freeze.json`: wrapper freeze whose original README/validation dependencies are excluded. Wrapper source and tests are reference material, not a self-contained runnable held-out release.

**Full wrapper `verify_integrity`, original UI integrity startup and native diagnostic runner cannot verify the full original scope from this staged tree.** Do not bypass these guards, regenerate freezes or fabricate missing artifacts. Excluding historical data is intentional. No wrapper inference or full wrapper test pass is claimed. Original native source/core tests remain reference-preserved, with documented public-copy sanitizations only.

`SOURCE_ALLOWLIST.json` records source SHA-256 and staged SHA-256 separately. `PUBLICATION_MANIFEST.json` verifies this final public candidate; the prior snapshot manifest is archived under `provenance/BASELINE_STAGING_SHA256.json`; it is not the engine freeze, a model digest, an attestation of private run contents, or a substitute for original full verification.

## Public reproduction limits

The functional offline CLI runs the included synthetic demo cases. Fresh synthetic native smoke checks cover repair, lock escalation without mutation, and unchanged closure. The public saved UI replays only three redacted known diagnostic examples and preserves a failure. It does not re-run the planner, reproduce held-out inference, or prove held-out aggregates.

Three original test modules require excluded external/historical fixtures; do not run unqualified recursive pytest over versions/presentation/wrapper in one process. Separate same-named engine imports by fresh processes. Future benchmark work would need explicit approval, a new clearly scoped release/protocol, supplied private prerequisites and truthful provenance; preparation here grants none of those permissions.

## Approved selected held-out display

`evidence/heldout-replay.html` is a separately approved local publication candidate containing three selected saved examples, their values, actions, rationales, expected-outcome labels and source hashes. It is not the full private exam, raw model transport or complete traces. The three examples do not independently prove the 20-case aggregate. This HTML is read-only with embedded records and no network requests. External publication still requires explicit owner authorisation.
