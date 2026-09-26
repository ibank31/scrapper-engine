# Scrapper Engine — Active Agent Handoff

**Updated:** 26 September 2026  
**Repository:** `ibank31/scrapper-engine`  
**Branch:** `main`

## Mission

Build a **campaign-agnostic Campaign Agent + Clipping Agent**.

Never create special production logic for Ryan Zofay or another named campaign. Campaign differences belong in source evidence and normalized rules.

The human reviewer is basic quality control. The machine should understand campaign rules, material requirements, platform requirements, compliance, and posting-package details.

## Source of truth

Read in this order:

1. `STATUS.md`
2. `docs/CAMPAIGN_AGENT_ROADMAP.md`
3. `docs/DECISION_LOG.md`
4. subsystem docs when changing that subsystem

Historical reports are archived and are not current contracts.

## Current milestone

**CA-00 Evidence Contract**

Implementation is merged. Production acceptance is still open.

Implemented:

- source document extraction;
- deterministic source fingerprint;
- evidence ledger;
- stable evidence IDs;
- AI quote verification;
- evidence contract;
- legacy AI-cache invalidation;
- live AI normalization source binding.

## Production findings

Legacy campaign rows without the current evidence contract are stale.

Do not manually rewrite D1. Re-analysis must use the generic campaign intelligence pipeline.

A full legacy migration hit Gemini 503 high-demand responses followed by 429 quota exhaustion. Do not repeatedly retry the entire corpus. Use `CLIPPER_CAMPAIGN_IDS` for targeted migration when quota is available.

Campaign sync now sends Bearer authentication and retains the worker-token header for compatibility.

## Architecture

```
SOURCE
  ↓
EVIDENCE
  ↓
CAMPAIGN BRAIN
  ↓
CRITIC
  ↓
RULE RECONCILIATION
  ↓
PRODUCTION CONTRACT
  ↓
MATERIAL INTELLIGENCE
  ↓
CLIP STRATEGY
  ↓
RENDER
  ↓
COMPLIANCE
  ↓
HUMAN QC
  ↓
BUFFER
```

AI is reasoning. Code is enforcement.

## Known regression

Ryan Zofay historically lost CTA, platform-specific handles, and hashtags during normalization.

This is a regression fixture, not a special case.

## Latest commits

- evidence contract: `26225e0ddec35799a74645186a62a02fb960ee84`
- cache invalidation: `de5f3413455b641b468b5975957abdecf315136a`
- sync auth/targeted migration: `4b85b6f9c1621f4aae82b6e76370d96802eaf34d`

## Next bounded slice

**CA-00 acceptance hardening.**

Add generic fixtures for explicit rules, document-only rules, platform handles, hashtags, CTA, duration, prohibited content, and ambiguity.

Measure critical and mandatory rule preservation.

Do not move to CA-01 until evidence coverage is measurable.

## Verification protocol

1. targeted tests;
2. full deterministic regression;
3. semantic fixture;
4. Node syntax checks;
5. diff check;
6. controlled E2E only when the changed contract requires it;
7. production verification only after CI passes.

If E2E finds a valid bug:

**STOP → preserve evidence → fix only that bug → retest.**

## Do not

- hard-code campaign behavior;
- invent campaign rules;
- treat AI uncertainty as confidence;
- mutate D1 manually to make tests pass;
- rerun the full corpus when targeted migration is enough;
- spend premium AI calls on deterministic extraction;
- claim unverified provider/native capabilities;
- treat a green local suite as production proof.

## Human review contract

The UI should answer:

- Is the clip compliant?
- Is it relevant?
- Is anything uncertain?
- What does the reviewer actually need to check?

Raw internal labels are not enough.
