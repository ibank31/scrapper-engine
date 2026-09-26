# Scrapper Engine — Decision Log

## 2026-09-26 — Campaign-agnostic architecture

Campaign-specific behavior is data/evidence, never campaign-name branching.

Ryan Zofay is a regression fixture, not an engine specialization.

## 2026-09-26 — Evidence before intelligence

Source facts receive stable evidence identity before AI interpretation.

Reason: explicit CTA, handles, hashtags, and other rules were previously lost during normalization.

Invariant: critical and mandatory rules must remain traceable to source evidence.

## 2026-09-26 — Legacy AI cache is stale without evidence contract

A matching `rules_hash` alone does not make an AI result reusable.

Current cache requires schema version, source hash, source ledger, evidence contract, and material policy.

## 2026-09-26 — Targeted migration

Legacy intelligence migration supports `CLIPPER_CAMPAIGN_IDS`.

Reason: full-corpus reanalysis can exhaust AI quota and is unnecessary for validating a single campaign or fixture.

## 2026-09-26 — AI quota is an operational dependency

Full migration encountered Gemini 503 high-demand responses followed by 429 quota exhaustion.

Decision: do not repeatedly retry the entire corpus. Future routing must be bounded and quota-aware.

## 2026-09-26 — Historical documents remain auditable

Superseded phase reports and audits are archived rather than deleted from Git history.

Reason: historical evidence is useful, but current agents must not mistake it for the active contract.
