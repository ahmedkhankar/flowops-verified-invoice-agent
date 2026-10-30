# Final public-candidate scope

Local preparation only. No repository has been initialised, committed, created remotely or published.

## Included
- Existing reviewed application/core, original tests, requirements, technical documentation and known diagnostic derivative.
- `evidence/heldout-replay.html`: only selected h_001, h_013 and h_019 display records; amounts, state transitions, proposals, outcomes, model rationales, expected-outcome labels and source hashes are visible. Saved execution only; no new inference or dispatch.
- New publication inventory, security review and SHA-256 manifest.

## Excluded
All HUMAIN presentation PDFs, editable slides, notes, slide images/build assets and demo video. Also credentials, environments, private full model requests/responses/traces, private grading fixtures and unrelated personal/reference material. The `presentation/invoice-ui-v1` directory contains application UI reference source, not submission slides. The portable public viewer is `public-demo/app.py`; that original reference UI cannot start with omitted integrity dependencies.

## Evidence and tests
75 self-contained public tests passed in the verified baseline; 126 is a historical full native-suite pass, not reproducible as a whole from this export. Three unchanged fixture-dependent modules are excluded from the clean subset. Original failure logs remain. The HTML is three examples, not independent proof of the 16/20 aggregate. Supplier knew prior weaknesses; single-run, supplier-attested post-freeze testing is not blind independent certification. The separate diagnostic remains 10/12; rules achieved 12/12 on that known diagnostic. No new inference or evaluation was run.

## Integrity and provenance
`PUBLICATION_MANIFEST.json` inventories this complete candidate, excluding itself. `provenance/BASELINE_STAGING_SHA256.json` preserves the previous snapshot only: its original paths/hashes do not describe this amended tree. `SOURCE_ALLOWLIST.json` and the native/wrapper/UI freezes remain unchanged historical references, not regenerated public-copy guarantees. Original engine/tests, included diagnostic data and approved HTML bytes match their source versions.

The only baseline document edits are README.md, docs/EVALUATION.md and docs/VERIFICATION.md. The baseline staging inventory is relocated, not rewritten. New technical documents do not contain portal answers, presentation notes or video assets.

## Licensing
No licence has been added. MIT is a recommendation only, pending owner approval of rights and terms. No model weights are included or relicensed.

## Reproduce
Use docs/SETUP.md for the portable diagnostic Streamlit viewer, deterministic CLI and 75-test subset. Open evidence/heldout-replay.html directly for selected held-out saved execution; it requires no server or model runtime. Do not run exposed evaluations again to claim unseen performance.
