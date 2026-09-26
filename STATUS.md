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

## Production baseline

Latest production deployment after PR #27:

- commit: `4b85b6f9c1621f4aae82b6e76370d96802eaf34d`
- deployment: `375dc195`
- status: success
- D1: `ee8299d2-84e5-433b-b02f-553dcd4aea73`
- R2: `clipper-engine-previews`

## Latest engineering

- CA-00 evidence contract: `26225e0ddec35799a74645186a62a02fb960ee84`
- legacy cache fencing: `de5f3413455b641b468b5975957abdecf315136a`
- campaign sync auth + targeted migration: `4b85b6f9c1621f4aae82b6e76370d96802eaf34d`

The engine now has source fingerprinting, evidence ledgers, evidence IDs, quote verification, evidence-aware AI normalization, stale-cache detection, Bearer campaign-sync authentication, and targeted migration support.

## Current blockers

1. CA-00 production acceptance is not closed until a real campaign is persisted with the new evidence contract.
2. Gemini broad migration hit 503 high-demand responses followed by 429 quota exhaustion.
3. AI routing/cost governance must become bounded before broad legacy migration.

The quota issue does **not** block deterministic engineering.

## Current campaign intelligence state

Ryan Zofay still has legacy `ai_rules_json.schema_version=1`.

Its historical failure is:

- CTA lost;
- platform-specific handles lost;
- hashtags lost.

Do not patch that row manually. Re-analysis must use the generic campaign intelligence path.

## Primary roadmap

`docs/CAMPAIGN_AGENT_ROADMAP.md`

```
CA-00 Evidence Contract
→ CA-01 Campaign Brain
→ CA-02 Campaign Critic
→ CA-03 Rule Reconciliation
→ CA-04 Production Contract
→ CA-05 Material Intelligence
→ CA-06 Clip Strategy
→ CA-07 Posting Package
→ CA-08 Compliance Gate
→ CA-09 Indonesian Human Review
→ CA-10 Campaign Memory
→ CA-11 Self Evaluation
→ CA-12 Adaptive AI Router
→ CA-13 Cost Governor
→ CA-14 Economic Learning
```

Current priority: **CA-00 → CA-04**.

## Permanent engineering rules

- Campaign-specific behavior comes from evidence/data, never campaign-name branches.
- AI reasons; deterministic code enforces.
- No silent rule loss.
- Ambiguity is explicit data.
- Do not spend AI quota on deterministic work.
- Do not rerun valid cached analysis.
- Do not migrate the whole corpus when targeted migration is sufficient.
- Human review is basic QC, not campaign translation/compliance work.
- If E2E finds a valid bug: stop, preserve evidence, fix only that bug.
- Buffer/provider mutation remains behind approval gates.

## Verification

PR #27 CI passed:

- deterministic regression;
- semantic golden fixture;
- artifact upload;
- Node syntax checks.

The latest controlled production E2E reached two rendered/validated review previews without Buffer mutation.

## Current documents

- `STATUS.md` — current truth.
- `docs/AGENT_HANDOFF.md` — operational handoff.
- `docs/CAMPAIGN_AGENT_ROADMAP.md` — primary roadmap.
- `docs/DECISION_LOG.md` — architecture decisions.
- `docs/CAMPAIGN_MATERIAL_INTELLIGENCE.md` — material contract.
- `docs/BUFFER_INTEGRATION.md` — Buffer contract.
- `docs/SEMANTIC_CLIPPING_LOCAL.md` — local semantic ranker.

Historical reports are under `docs/archive/`.

## Next exact slice

**CA-00 acceptance hardening.**

Build generic campaign fixtures and prove:

- stable source fingerprint;
- document-only rules retained;
- critical/mandatory rules have provenance;
- zero silent rule loss;
- legacy cache is stale;
- valid cache is reusable;
- targeted migration isolates one campaign.

Do not move to CA-01 until this gate is measurable.
