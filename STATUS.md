# Scrapper Engine — Current Status

**Updated:** 26 September 2026  
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

PR #28 (**CA-00 acceptance hardening**) and PR #32 (**CA-00 campaign diversity + provenance hardening**) are merged to `main`. The latest verified functional code baseline is `465b2b6cf1d955e2c193aedba82a35937fa5a389`. Subsequent commits only narrow repository scope and update documentation/remove unrelated tooling.

CI status for the latest commit is not exposed by the current GitHub connector surface; the repository's existing CI baseline remains green from the prior verified runs. Cloudflare production deployment of the latest main commit completed successfully.

Production:
- last verified functional deployment: `99d49f6e-59cf-4204-8b6e-ce20ac683e3a`
- deployment code baseline: `8dd04a440651922b966d76ed37817e4959fc5aad`
- controlled CA-00 production acceptance was later verified against main code baseline `465b2b6cf1d955e2c193aedba82a35937fa5a389`
- deployment URL: https://105b16be.clipper-engine.pages.dev

## CA-00 status

**Implementation:** merged.  
**Deterministic acceptance hardening:** merged.  
**Controlled production acceptance:** **PASS**.

CA-00 sekarang ditutup. Jangan menambah fitur CA-00 lagi kecuali regression fix yang dibuktikan oleh test.

The prior Ryan production row may remain legacy until a future bounded re-analysis writes CA-01 brain data. Do not manually mutate D1 to simulate acceptance.

## Current acceptance coverage

Merged hardening proves, in generic fixtures:

- six campaign rule shapes are represented: document-only, platform-specific, restrictive/ambiguous, conflicting-source, multilingual, and material-heavy;
- stable source fingerprint;
- document-only source changes change fingerprint;
- mandatory evidence provenance;
- stable evidence IDs;
- fake evidence is rejected explicitly;
- legacy evidence-less cache is not reusable;
- valid evidence-contract cache is reusable;
- `CLIPPER_CAMPAIGN_IDS` scopes migration to requested campaigns;
- evidence ledger can retain declared source references, URL, source timestamp, extraction method, source priority, and character spans when supplied.

This is deterministic proof. It is not yet production proof.

## Known regression

Ryan Zofay historically lost CTA, platform-specific handles, and hashtags during AI normalization. Keep the fix generic: source-backed reconciliation and canonical brain preservation, never Ryan-specific branching.

Treat this strictly as regression evidence. Never add Ryan-specific runtime logic.

## Next exact slice

**CA-01 — Canonical Campaign Brain.**

Bounded implementation:

1. canonicalize AI output into campaign_brain;
2. prove preservation on the existing six-shape corpus;
3. persist the brain without changing downstream consumers;
4. invalidate evidence-only caches;
5. after merge, use the bounded Ryan workflow to verify production persistence.

Do not run a corpus-wide AI migration.

## Permanent rules

- AI interprets; deterministic code verifies/enforces.
- No silent rule loss.
- Ambiguity is explicit data.
- Campaign-specific behavior is never hardcoded by campaign name.
- Do not manually mutate production D1 to make acceptance green.
- Do not spend quota on full-corpus migration when targeted proof is sufficient.
- Buffer/provider mutation remains behind approval gates.
- Scope is clipping only. Affiliate/product-image work, unrelated scrapers, and personal automation do not belong in this repository.
- Local execution tooling is implementation detail, not a separate product workflow.
