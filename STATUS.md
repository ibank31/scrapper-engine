# Scrapper Engine — Current Status

**Updated:** 26 September 2026  
**Branch:** `main`  
**Current direction:** AI Agent untuk clipping campaign  
**Production:** Cloudflare Pages `clipper-engine`

## Mission

Build a **campaign-agnostic AI Clipping Agent**. Campaign discovery/intake/evidence/material intelligence adalah bagian dari pipeline clipping, bukan produk terpisah.

```
campaign source → evidence → campaign brain → critic
→ production contract → material plan → clip strategy
→ render → compliance → simple human review → Buffer
```

Ryan Zofay is a regression case, not the product target.

## Latest verified repository state

PR #28 (**CA-00 acceptance hardening**) and PR #32 (**CA-00 campaign diversity + provenance hardening**) are merged to `main`. The latest main commit is `3a7bd0b257a2986d07335803ae36230431705fcf`.

CI status for the latest commit is not exposed by the current GitHub connector surface; the repository's existing CI baseline remains green from the prior verified runs. Cloudflare production deployment of the latest main commit completed successfully.

Production:
- deployment: `105b16be` (success)
- deployment commit: `3a7bd0b257a2986d07335803ae36230431705fcf`
- deployment URL: https://105b16be.clipper-engine.pages.dev

## CA-00 status

**Implementation:** merged.  
**Deterministic acceptance hardening:** merged.  
**Controlled production acceptance:** **PASS**.

CA-00 sekarang ditutup. Jangan menambah fitur CA-00 lagi kecuali regression fix yang dibuktikan oleh test.

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

Ryan Zofay historically lost CTA, platform-specific handles, and hashtags during AI normalization.

Treat this strictly as regression evidence. Never add Ryan-specific runtime logic.

## Next exact slice

**CA-01 — Canonical Campaign Brain.**

When Gemini quota is available:

1. run targeted migration for campaign `926e1b7f-1030-4333-a557-f99d9f891437`;
2. verify D1 contains evidence-contract `schema_version=2`;
3. verify CTA, hashtags, platform handles, duration, and provenance are represented without silent loss;
4. run controlled production E2E;
5. if E2E finds a new valid bug: STOP and fix only that bug.

CA-00 production evidence-contract proof sudah terbukti melalui controlled OpenRouter fallback E2E. CA-01 menjadi milestone aktif berikutnya.

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
