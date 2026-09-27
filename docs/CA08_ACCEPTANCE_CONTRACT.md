# CA-08 Acceptance Contract — Final Campaign Compliance Gate

## Scope

CA-08 is the final deterministic verification layer before human review. It evaluates the existing campaign intelligence chain:

```
campaign source
  → evidence contract
  → campaign_brain
  → campaign_critic
  → campaign_reconciliation
  → production_contract
  → material_plan
  → clip_strategy
  → posting_package
  → compliance_gate
```

It does not add new campaign policy. It verifies that policy already established upstream remains current, provenance-backed, platform-scoped, and executable without silently changing meaning.

CA-08 is read-only. It never calls an LLM, downloads assets, renders media, queues jobs, publishes to Buffer, mutates D1, or mutates any upstream object.

## Contract

`compile_compliance_gate(...)` returns:

- `schema_version` and deterministic `compliance_gate_id`;
- campaign/source/Brain/Critic/Reconciliation/Production/Material/Clip/Posting identity;
- deterministic status: `ready`, `review`, or `blocked`;
- named checks for identity, provenance, requirement preservation, platform scope, content restrictions, material readiness, posting, and upstream status;
- observable deterministic issues with stage, field, severity, and references;
- summary counts.

## Identity and freshness

The gate rejects:

- missing or invalid required stage artifacts;
- mismatched campaign IDs;
- stale or mismatched source hashes;
- mismatched Brain, Critic, Reconciliation, Production, Material, Clip, or Posting identities;
- broken downstream dependency IDs;
- a cached gate that is not byte-for-byte equivalent to the current deterministic result.

`compliance_gate_is_current()` recomputes the gate from the same upstream artifacts. Any dependency identity or relevant state change therefore invalidates the cached result.

## Provenance

Mandatory requirements must retain current verified evidence IDs.

The gate checks provenance across:

- Brain rules;
- Reconciliation rules/findings;
- Production Contract requirements;
- Material Plan requirements;
- Clip Strategy selected segments;
- Posting Package items.

Mandatory `unsupported`, `ambiguous`, `conflicting`, or `manual_required` interpretations remain blocking unless upstream resolution is explicitly marked resolved.

Unverified evidence is observable and blocking. The gate never invents evidence, source references, values, or policy.

## Requirement preservation

The gate verifies:

- Reconciliation rules still reference existing Brain rule IDs;
- Material Plan requirements still bind to the deterministic Production Contract requirement identity;
- Material Plan provenance still references an existing Reconciliation rule;
- Clip Strategy segments reference existing Material Plan requirements;
- mandatory Production Contract posting requirements are preserved in the Posting Package with value, scope, requirement level, provenance, and rule lineage intact;
- content restrictions declared in the Production Contract remain present in Clip Strategy constraints.

Optional requirements may be absent without becoming blocking.

## Platform scope

Publication platform scope is derived from the existing Production Contract posting scope and Clip Strategy scope. The Posting Package must expose every required platform and must not silently flatten platform-specific posting values.

Material acquisition scope is not treated as publication scope by this gate.

## Material readiness

If the Material Plan is blocked, the final gate is blocked.

Any selected Clip Strategy segment must reference an existing Material Plan asset whose lifecycle state is one of:

- `verified`
- `acquired`
- `ready`

A selected segment never makes a candidate asset execution-ready by implication.

## Status semantics

- `ready`: no critical issues and no warnings remain.
- `review`: no critical issues, but non-critical warnings or unresolved review items remain.
- `blocked`: any identity, provenance, mandatory-preservation, restriction, material-readiness, or other critical failure exists.

## Persistence and compatibility

The normalized intelligence envelope stores `compliance_gate` additively beside the existing Brain, Critic, Reconciliation, Production Contract, Material Plan, Clip Strategy, Posting Package, and legacy `rules` projection.

The sync worker validates a cached CA-08 gate when present. Older CA-07 envelopes without `compliance_gate` remain readable so CA-08 does not silently trigger a global migration or provider spend.

A bounded CA-08 migration may be performed later and must be explicitly targeted.

## Verification

```bash
python -m unittest -v tests.test_compliance_gate
python scripts/accept_ca08.py
python -m unittest discover -s tests -v
python -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python -m compileall -q core modules worker
python -m pip check
git diff --check
```

No Buffer publishing mutation and no manual D1 mutation are permitted during CA-08 acceptance.
