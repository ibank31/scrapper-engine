# Scrapper Engine — Active Agent Handoff

**Updated:** 26 September 2026  
**Repository:** `ibank31/scrapper-engine`  
**Branch:** `main`  
**Last implementation baseline:** `c1ef801367cba42fe12178088dec099c055afae9`

## Mission

Build a **campaign-agnostic Campaign Agent + Clipping Agent**.

Ryan Zofay is a regression fixture, never a special production case. Campaign differences belong in source evidence and normalized rules.

Human review is basic QC. The machine is responsible for understanding campaign rules, material requirements, platform requirements, compliance, and posting-package details.

## Current milestone

**CA-00 — Evidence Contract**

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
- generic CA-00 acceptance fixtures and cache/migration regression tests.

PR #28 is merged as `c1ef801367cba42fe12178088dec099c055afae9`.

This handoff snapshot is carried by documentation commit `3a65b1a8d05902c72a56852d59ca7124d26de6c8`.

## Production acceptance

Still **OPEN**.

Production D1 was checked directly for Ryan Zofay after the merge. The stored intelligence remains legacy `schema_version=1`.

Do not manually rewrite the row.

The remaining proof requires a real generic re-analysis that stores the new evidence contract. Gemini quota has previously exhausted after 503/429 responses, so corpus-wide migration is forbidden.

## Exact next action

When quota is available:

```
CLIPPER_CAMPAIGN_IDS=926e1b7f-1030-4333-a557-f99d9f891437
        ↓
targeted campaign-sync-ai
        ↓
verify D1 evidence contract
        ↓
controlled production E2E
```

Required evidence:

- `schema_version=2`;
- `source_hash`;
- `source_ledger`;
- `evidence_contract`;
- verified evidence for critical/mandatory rules;
- no silent loss of CTA, handles, hashtags, duration.

If Gemini remains unavailable, stay inside CA-00 with deterministic work. Do not begin CA-01.

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
- treat green CI as production proof.
