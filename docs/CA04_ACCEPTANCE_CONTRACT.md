# CA-04 Acceptance Contract — Production Contract Compiler

## Purpose

CA-04 compiles canonical CA-03 reconciliation into a deterministic, source-traceable execution contract. It is a compiler boundary, not a new AI analyzer. CA-01 and CA-03 remain responsible for semantic interpretation and reconciliation; CA-05 onward may consume the compiled requirements.

```text
campaign → evidence → brain → critic → reconciliation → production_contract
```

## Input

`compile_production_contract(reconciliation)` consumes the schema-versioned CA-03 object, including:

- `campaign_id`, `source_hash`, `brain_id`, `critic_id`, `reconciliation_id`;
- reconciled `rules`;
- rule `requirement_level`, `interpretation_type`, `scope`, and `resolution`;
- `evidence_ids`, `source_references`, and Brain rule IDs;
- unresolved `findings`, `conflicts`, and `integrity_errors`.

No legacy `ai_rules.rules` decision is used as semantic input.

## Output schema

The normalized intelligence payload now contains `production_contract` beside `campaign_brain`, `campaign_critic`, and `campaign_reconciliation`:

```json
{
  "schema_version": 1,
  "contract_id": "production-contract-v1:<sha256>",
  "campaign_id": "...",
  "source_hash": "...",
  "brain_id": "...",
  "critic_id": "...",
  "reconciliation_id": "...",
  "status": "ready|review|blocked",
  "production": {"requirements": []},
  "material": {"requirements": [], "asset_requirements": []},
  "clip": {"requirements": []},
  "posting": {"requirements": []},
  "compliance": {"checks": []},
  "dependencies": ["material", "clip", "production", "compliance", "posting"],
  "issues": [],
  "summary": {}
}
```

Every compiled requirement contains `field`, `value` or `constraint`, `required` (`true`, `false`, or `null` for unknown), `scope`, and `provenance`. Provenance retains the reconciliation rule ID, Brain rule IDs, evidence IDs, source references, requirement level, interpretation type, resolution, and scope.

## Compilation policy

- **Duration**: `min_duration_seconds` and `max_duration_seconds` become one `duration_seconds` constraint with deterministic `min`/`max` values.
- **Material**: material requirements are compiled only. Asset URLs or references are never treated as resolved; CA-05 owns material resolution.
- **Clip**: constraints describe what a valid candidate must satisfy; no clip is selected.
- **Posting**: exact CTA, hashtag, and handle values are copied from reconciled rules. Platform-scoped values remain platform-scoped.
- **Compliance**: checks are generated as requirements; CA-08 owns final compliance execution.
- **Semantics**: mandatory, optional, and unknown remain distinct. Explicit, inferred, conflicting, ambiguous, unsupported, and manual-required interpretation states remain in provenance.
- **No invention**: fields absent from reconciliation are not promoted to mandatory values. Empty domain containers are structural envelopes, not inferred requirements.

## Identity and determinism

`contract_id` is SHA-256-derived from exactly `campaign_id`, `source_hash`, `brain_id`, `reconciliation_id`, and schema version. It uses no timestamp, UUID, or random value. Equal input produces equal complete output; changing source or reconciliation identity changes the contract identity.

## Status and issues

- `ready`: no integrity failure, critical unresolved issue, or unresolved mandatory execution requirement.
- `review`: non-critical unresolved issue or review state from reconciliation remains observable.
- `blocked`: invalid identity/schema, critical unresolved finding/conflict, or unresolved mandatory requirement.

Issues are deterministic and include `issue_id`, severity, type, rule/finding ID, evidence IDs, reason, and `manual_required` resolution.

## Scope propagation

Platform, language, and audience scopes are copied from reconciliation. Posting values with platform scopes are grouped under the corresponding platform rather than collapsed into a global rule. CA-04 does not resolve scope conflicts.

## Legacy compatibility and persistence

The existing `ai_rules.rules` projection remains in the normalized payload for current consumers. CA-04 is additive and uses the existing serialized `ai_rules_json` envelope; no D1 schema migration is required. Cache reuse now requires a schema-valid production contract whose campaign, source, Brain, and reconciliation identities match the cached intelligence. Missing or mismatched contracts are stale and are recomputed.

## Acceptance tests

`tests/test_production_contract.py` covers:

- deterministic identity and identity sensitivity;
- all five contract domains;
- duration compilation;
- mandatory/optional/unknown and interpretation preservation;
- evidence and source provenance;
- platform-scoped posting values;
- unresolved critical status;
- integrity blocking;
- input immutability;
- normalized chain integration and legacy projection.

Regression tests cover CA-00 through CA-03. The bounded workflow is:

```text
python scripts/accept_ca04.py
```

It runs a synthetic campaign through normalization, serializes/reloads the intelligence envelope as the persistence boundary, verifies identity linkage and evidence coverage, and asserts no Buffer or manual D1 mutation. It does not call a provider or mutate external production systems.

## Known limitations

- The compiler does not perform semantic interpretation or infer missing values.
- It does not resolve assets, select clips, render media, execute compliance, queue jobs, or publish to Buffer.
- The local acceptance workflow proves the serialized persistence contract; an external production deployment still requires the existing bounded worker/API acceptance procedure.
- Arbitrary prose remains an opaque reconciled value unless CA-03 already supplied structured semantics.
