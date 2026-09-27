# Scrapper Engine — Current Status

**Updated:** 27 September 2026
**Branch:** `main`
**Current direction:** Campaign Agent; clipping adalah vertical pertama
**Production:** Cloudflare Pages `clipper-engine`

## Mission

Build a **campaign-agnostic Campaign Agent**. Clipping adalah vertical pertama yang sedang dibuktikan production-grade; campaign intelligence, evidence, material intelligence, execution, compliance, review, publishing, outcome, dan learning adalah lapisan reusable.

```
campaign source → evidence → campaign brain → critic
→ production contract → material plan → clip strategy
→ render → compliance → simple human review → Buffer
```

Ryan Zofay is a regression case, not the product target.

## Latest verified repository state

CA-00 and CA-01 implementation are merged on `main`.

**Latest main SHA:** `b0180f1d96644f3d114c4860be4ba744b76e70b0`

CA-01 implementation spans PR #38–#44 and includes the canonical Campaign Brain, deterministic identity, source-backed rule/evidence linkage, structured mandatory/optional requirements, platform/language scope, variants/conflicts, and legacy compatibility projection.

The bounded CA-01 production acceptance was verified by GitHub Actions run `36279279316`. Its `targeted-acceptance` job completed successfully, including both:
- Targeted Ryan production re-analysis
- Verify persisted acceptance contract

The acceptance run proved persisted `schema_version=2`, canonical `campaign_brain` presence, matching source hashes, brain identity, evidence coverage, CTA preservation, and legacy handles/hashtags compatibility.

## CA-00 status

**PASS.** CA-00 is closed. Do not add CA-00 features except regression fixes backed by evidence.

## CA-01 status

**PASS.**

Verified acceptance gates:

- canonical `campaign_brain`;
- deterministic `brain_id`;
- source fingerprint / `source_hash`;
- structured rule records;
- mandatory / optional / unknown semantics;
- direct evidence linkage;
- platform and language scope;
- conflict / variant preservation;
- unavailable-AI protection against false boolean facts;
- legacy `ai_rules.rules` compatibility projection;
- existing six-shape corpus acceptance;
- bounded Ryan production persistence acceptance.

CA-01 production acceptance is a targeted proof, not a claim that every production campaign has already been migrated.

## CA-01 audit finding

The implementation is accepted, but the acceptance evidence has two documentation/test-quality limitations:

1. `STATUS.md` and `docs/AGENT_HANDOFF.md` previously described CA-01 as the next unfinished milestone. That was stale and has now been corrected.
2. The repository does not currently expose an authoritative CI artifact proving the exact claimed total of **219 tests** through the available connector. Do not repeat that number as independently verified. The CA-01-specific tests and production acceptance are verified from repository/workflow definitions and the successful bounded run.

The acceptance contract also lists critical-rule preservation and platform-scope preservation as metrics. Current deterministic evaluation derives critical preservation from mandatory preservation and exercises platform scope through targeted fixtures. This is sufficient for the existing CA-01 gate, but these metrics should be made independently explicit in a future hardening change rather than silently assuming they are identical.

## Next exact slice

**CA-02 — Campaign Critic.**

Do not begin CA-02 implementation in the same documentation patch. CA-01 is closed; the next engineering slice must define its hypothesis, seeded critic findings, acceptance metrics, and regression tests before implementation.

## Permanent rules

- AI interprets; deterministic code verifies/enforces.
- No silent rule loss.
- Ambiguity is explicit data.
- Campaign-specific behavior is never hardcoded by campaign name.
- Do not manually mutate production D1 to make acceptance green.
- Do not spend quota on full-corpus migration when targeted proof is sufficient.
- Buffer/provider mutation remains behind approval gates.
- Scope is clipping only.
- Local execution tooling is implementation detail, not a separate product workflow.
