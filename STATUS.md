# Scrapper Engine — Current Status

**Updated:** 26 September 2026  
**Branch:** `main`  
**Current direction:** Campaign Agent Evolution  
**Production:** Cloudflare Pages `clipper-engine`

## Mission

Build a **campaign-agnostic Campaign Agent + Clipping Agent**.

```
campaign source → evidence → campaign brain → critic
→ production contract → material plan → clip strategy
→ render → compliance → simple human review → Buffer
```

Ryan Zofay is a regression case, not the product target.

## Latest verified repository state

PR #28 (**CA-00 acceptance hardening**) is merged to `main` as `c1ef801367cba42fe12178088dec099c055afae9`.

CI runs associated with this merge:
- tests: run 280, completed / success
- phase5-acceptance: run 106, in_progress

Production:
- deployment: `a6eb49da` (success)
- deployment commit: `3a65b1a8d05902c72a56852d59ca7124d26de6c8`
- deployment URL: https://a6eb49da.clipper-engine.pages.dev

## CA-00 status

**Implementation:** merged.  
**Deterministic acceptance hardening:** merged.  
**Production acceptance gate:** **OPEN**.

The production D1 row for Ryan Zofay was re-read after the merge and still contains legacy `ai_rules_json.schema_version=1`. It has not been manually rewritten.

CA-00 therefore is **not** declared complete yet. The remaining proof is a real campaign re-analysis through the generic AI path that persists:

- `schema_version=2`;
- `source_hash`;
- `source_ledger`;
- verified evidence;
- `evidence_contract`.

Gemini previously returned 503 high-demand responses followed by 429 quota exhaustion. Do not rerun a corpus-wide migration.

## Current acceptance coverage

Merged hardening proves, in generic fixtures:

- stable source fingerprint;
- document-only source changes change fingerprint;
- mandatory evidence provenance;
- stable evidence IDs;
- fake evidence is rejected explicitly;
- legacy evidence-less cache is not reusable;
- valid evidence-contract cache is reusable;
- `CLIPPER_CAMPAIGN_IDS` scopes migration to requested campaigns.

This is deterministic proof. It is not yet production proof.

## Known regression

Ryan Zofay historically lost CTA, platform-specific handles, and hashtags during AI normalization.

Treat this strictly as regression evidence. Never add Ryan-specific runtime logic.

## Next exact slice

**CA-00 production acceptance.**

When Gemini quota is available:

1. run targeted migration for campaign `926e1b7f-1030-4333-a557-f99d9f891437`;
2. verify D1 contains evidence-contract `schema_version=2`;
3. verify CTA, hashtags, platform handles, duration, and provenance are represented without silent loss;
4. run controlled production E2E;
5. if E2E finds a new valid bug: STOP and fix only that bug.

While Gemini remains unavailable, continue only deterministic CA-00 hardening or documentation cleanup. Do not start CA-01.

## Permanent rules

- AI interprets; deterministic code verifies/enforces.
- No silent rule loss.
- Ambiguity is explicit data.
- Campaign-specific behavior is never hardcoded by campaign name.
- Do not manually mutate production D1 to make acceptance green.
- Do not spend quota on full-corpus migration when one campaign is sufficient.
- Buffer/provider mutation remains behind approval gates.
