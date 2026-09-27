# CA-05 Acceptance Contract — Material Intelligence

## Hypothesis

A deterministic compiler can turn the CA-04 Material Contract into a provenance-preserving Material Plan without inventing assets, silently substituting material, collapsing platform scope, or calling an LLM.

## Architecture and persistence

```text
campaign source
  → evidence contract
  → campaign_brain
  → campaign_critic
  → campaign_reconciliation
  → production_contract
  → material_plan
  → persisted ai_rules_json
```

`material_plan` is additive inside the existing serialized intelligence envelope. `ai_rules.rules` remains available for legacy consumers. No D1 schema migration, provider call, Buffer mutation, download, or publishing path is introduced.

## Material plan schema

`compile_material_plan(production_contract, candidates=[])` returns:

- `schema_version`, `material_plan_id`, `campaign_id`, `source_hash`, `brain_id`, `reconciliation_id`, and `production_contract_id`;
- deterministic `status`: `ready`, `review`, or `blocked`;
- `requirements` with stable IDs, category, role, required semantics, interpretation state, scope, constraints, resolution status, and provenance;
- `assets` with deterministic fingerprint/asset identity, lifecycle status, source URL/type, scope, content hash, and provenance;
- `acquisition_plan` with explicit strategy, priority, required state, verification policy, and fallback policy;
- `fallbacks` only for explicit CA-04 fallback material; they never activate automatically;
- `constraints`, `issues`, and deterministic `summary` counts.

## Semantics and lifecycle

Requirement levels remain `mandatory`, `optional`, or `unknown`. Interpretation states remain `explicit`, `inferred`, `conflicting`, `ambiguous`, `unsupported`, or `manual_required`. Unknown is never promoted to mandatory; inferred is never rewritten to explicit.

Asset states are explicit: `required`, `discovered`, `candidate`, `verified`, `acquired`, `ready`, `rejected`, `missing`, `unresolved`, and `blocked`. A URL is not an acquired asset. A verified candidate is not claimed to be acquired or execution-ready.

A missing mandatory requirement creates a critical issue and `blocked` status. Non-critical uncertainty remains `review`. A verified candidate can resolve the requirement to `ready` without changing the candidate's lifecycle state. Unresolved mandatory ambiguity blocks unless CA-03 already carries a resolved lineage record.

## Provenance and scope

Each material requirement links to:

```text
material requirement
  → production contract requirement
  → reconciliation rule
  → Brain rule
  → evidence IDs
  → source references
  → source hash
```

Platform, language, and audience scope remains on both requirements and assets. Platform-specific requirements are not collapsed into global material.

## Deduplication

Asset identity is deterministic. Explicit `fingerprint`, content hash, checksum, or URL identity is used where available; otherwise a stable campaign/identity fingerprint is derived. Repeated discovery of the same fingerprint creates one logical asset and increments deterministic duplicate accounting. Random IDs are never canonical identity.

## Cache policy

`material_plan_is_current()` requires matching:

- campaign ID;
- source hash;
- Brain ID;
- reconciliation ID;
- production contract ID;
- material plan schema version and plan identity;
- list-shaped requirements and assets.

Changing any canonical dependency invalidates reuse. The sync cache gate rejects missing or mismatched CA-05 material intelligence.

## Bounded acceptance

`scripts/accept_ca05.py` runs the normalized campaign intelligence chain through CA-04 and CA-05 using a local fixture and no provider. It verifies:

- `MATERIAL_PLAN_PRESENT=true`;
- identity linkage and provenance coverage;
- missing mandatory material blocks;
- a verified candidate yields a ready plan without faking acquisition;
- explicit fallback remains explicit and does not substitute for the primary asset;
- cache invalidation on source and contract identity changes;
- input serialization and legacy rules compatibility;
- `BUFFER_PUBLISHING_MUTATION=NONE`;
- `MANUAL_D1_MUTATION=NONE`.

## Test matrix

`tests/test_material_intelligence.py` covers schema/identity, simple mandatory material, missing mandatory blocking, verified lifecycle, optional and unknown semantics, platform scope, explicit fallback, duplicate fingerprints, provenance, immutability, determinism, stale cache, and normalized-chain integration.

## Deliberate limitations

CA-05 does not download assets, verify external content, acquire material, choose clips, compile posting, execute final compliance, render, queue, publish, or call an LLM. Those boundaries remain for later milestones and existing downstream components.
