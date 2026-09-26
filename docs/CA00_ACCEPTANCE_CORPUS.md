# CA-00 Acceptance Corpus

The CA-00 regression corpus is intentionally campaign-agnostic. Fixture names describe rule shapes, not production campaigns.

| Fixture | Shape covered |
|---|---|
| document_only | rules that exist only in document/source text |
| platform_specific | platform-scoped handles and hashtags |
| restrictive_ambiguous | prohibited rules, disclosure, explicit ambiguity/manual review |
| conflicting_sources | current and legacy source values that require provenance |
| multilingual | multilingual source text and alternative language values |
| material_heavy | asset-source requirements, approved assets, and prohibitions |

## Acceptance invariant

Every fixture must satisfy:

- stable source fingerprint;
- 100% evidence verification for the fixture's declared evidence;
- 100% mandatory evidence coverage;
- deterministic evidence IDs;
- explicit rejection of invented evidence;
- no campaign-name-specific runtime behavior.

This corpus is contract proof only. It does not substitute for real production acceptance.

## Gemini dependency

Gemini-backed production re-analysis is intentionally deferred while the provider quota is exhausted. No fixture or production row is mutated to simulate a successful AI migration.

When quota resets, production acceptance should use the bounded `campaign_ids` workflow input and then verify the persisted evidence contract before controlled E2E.
