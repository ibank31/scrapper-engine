# Scrapper Engine — Active Agent Handoff

**Updated:** 26 September 2026  
**Repository:** `ibank31/scrapper-engine`  
**Branch:** `main`  
**Last implementation baseline:** `465b2b6cf1d955e2c193aedba82a35937fa5a389`

## Mission

Build a **campaign-agnostic AI Clipping Agent**. Campaign discovery, evidence, material acquisition, clip selection, rendering, compliance, review, and publishing gates all exist to serve clipping.

Ryan Zofay is a regression fixture, never a special production case. Campaign differences belong in source evidence and normalized rules.

Human review is basic QC. The machine is responsible for understanding campaign rules, material requirements, platform requirements, compliance, and posting-package details.

## Current milestone

**CA-01 — Canonical Campaign Brain**

### Completed and merged

- source document extraction;
- deterministic source fingerprint;
- evidence ledger;
- stable evidence IDs;
- AI quote verification;
- evidence-aware AI normalization;
- legacy AI-cache invalidation;
- Bearer campaign-sync authentication;
- targeted migration support;
- generic CA-00 acceptance fixtures and cache/migration regression tests;
- six-shape campaign diversity corpus;
- evidence provenance metadata: declared URLs, timestamps when supplied, extraction method, source priority, and character spans;
- bounded `campaign_ids` input exposed in `campaign-sync-ai`.

PR #28 is merged as `c1ef801367cba42fe12178088dec099c055afae9`.

This handoff snapshot is carried by documentation commit `3a65b1a8d05902c72a56852d59ca7124d26de6c8`.

## CA-00 production acceptance

**PASS.** Controlled production acceptance proved the generic AI router fallback path with evidence contract preservation.

Production D1 was checked directly for Ryan Zofay after the merge. The stored intelligence remains legacy `schema_version=1`.

Do not manually rewrite the row.

The remaining proof requires real generic re-analysis that stores the new evidence contract. Gemini quota is currently exhausted after 503/429 responses, so corpus-wide migration is forbidden.

## Exact next action

Begin CA-01 as one bounded slice. Do not reopen CA-00 except for a regression proven by a failing fixture or production acceptance test.

CA-00 acceptance evidence:

- `schema_version=2`;
- `source_hash`;
- `source_ledger`;
- verified evidence;
- `evidence_contract`;
- CTA retained;
- platform handles retained;
- hashtags retained;
- controlled production acceptance `PASS`.

## Verification baseline

Latest merged CI is represented by the post-merge Actions runs for `3a65b1a8d05902c72a56852d59ca7124d26de6c8`.

Current production deployment is tied to the same `main` commit through Cloudflare Pages.

A previous controlled E2E reached two rendered/validated review previews without Buffer mutation. Its intelligence failure remains the canonical rule-loss regression.

## Operating protocol

```
PLAN → EXECUTE → VERIFY → DOCUMENT → CONTINUE
```

If E2E finds a new valid bug:

```
STOP
preserve evidence
add regression
fix root cause
verify
document
repeat E2E
```

## Do not

- hard-code Ryan Zofay or any campaign;
- invent campaign rules;
- trust valid JSON as proof of correct intelligence;
- manually mutate D1 to bypass acceptance;
- rerun full AI migration when targeted migration is sufficient;
- spend premium AI calls on deterministic work;
- treat green CI as production proof;
- add unrelated product/affiliate automation to this repository;
- revive obsolete Termux/product-image workflows; the repository scope is clipping only.
