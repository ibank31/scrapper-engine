# CA-01 Acceptance Contract

## Hypothesis

A campaign can be converted from verified source evidence plus AI interpretation into a canonical Campaign Brain without losing source-backed rules or breaking existing clipping consumers.

## Scope

CA-01A canonical schema, CA-01B deterministic preservation gate, CA-01C persistence and compatibility.

Reuse the existing six-shape corpus:

- document-only
- platform-specific
- restrictive/ambiguous
- conflicting-sources
- multilingual
- material-heavy

No second corpus is introduced.

## Acceptance metrics

- critical rule preservation: 100%
- mandatory rule preservation: 100%
- silent rule loss: 0
- false mandatory assignment: 0
- supported canonical rules without evidence: 0
- platform scope preservation: 100%
- multilingual variants preserved
- conflicting sources preserved without resolution
- unavailable AI does not create false boolean facts
- deterministic brain_id for identical source and meaning
- legacy ai_rules.rules remains available to current downstream consumers
- rule_annotations is an optional exception channel, not an output-size requirement for every rule
- evidence-only cache is stale

## Production gate

After merge, a bounded Ryan re-analysis must persist and verify campaign_brain. This is one targeted proof, not a corpus-wide migration.

A controlled E2E remains the final gate because unit tests do not prove D1 persistence or full pipeline compatibility.
