# CA-07 Acceptance Contract — Posting Package Compiler

## Scope

CA-07 compiles the authoritative production contract, clip strategy, and explicit campaign posting fields into a deterministic, platform-scoped `posting_package`. It is a compiler only: it does not call an LLM, render, publish, mutate Buffer, or mutate D1.

## Identity and cache

The package identity is derived from:

- `campaign_id`
- `source_hash`
- `brain_id`
- `reconciliation_id`
- `production_contract_id`
- `clip_strategy_id`
- schema version

`posting_package_is_current()` rejects a package when any dependency changes. The sync worker requires a current package for CA-06+ envelopes while preserving readability of older CA-05 envelopes.

## Preservation guarantees

- Exact CTA, hashtags, handles, disclosures, caption, audio policy, subtitle delivery, native-tag requirements, and schedule intent are copied from authoritative structured inputs.
- Platform scopes remain separate; no platform-specific values are flattened.
- Missing, conflicting, unsupported, or provenance-invalid mandatory fields produce `blocked` and an observable issue.
- Optional unresolved fields produce `review` where appropriate and never become mandatory.
- Native or otherwise non-deterministic actions are represented as `manual_actions` / `manual_required`; the compiler never claims execution.
- No publication timestamp is invented.
- Every mandatory posting field must carry verified evidence IDs and the current source hash for `provenance_coverage=1.0`.
- Inputs are read-only and legacy `rules` remains in the normalized envelope.

## Status

- `ready`: all mandatory posting values and provenance are valid.
- `review`: only non-critical manual or optional items remain.
- `blocked`: identity, mandatory value, conflict, unsupported requirement, or provenance validation failed.

## Verification

```bash
python -m unittest -v tests.test_posting_package
python scripts/accept_ca07.py
python -m unittest discover -s tests -v
python -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python -m compileall -q core modules worker
python -m pip check
git diff --check
```

No Buffer publishing or manual D1 mutation is performed by CA-07 acceptance.
