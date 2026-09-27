# Scrapper Engine — Active Agent Handoff

**Updated:** 27 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Latest main SHA:** `b0180f1d96644f3d114c4860be4ba744b76e70b0`

## Mission

Build a **campaign-agnostic Campaign Agent**. Clipping is the first execution vertical. Campaign discovery, evidence, material acquisition, strategy, execution, compliance, review, publishing, and outcome learning are reusable layers.

Ryan Zofay is a regression fixture, never a special production case.

## Closed milestones

### CA-00 — Evidence Contract

**PASS / CLOSED.**

Evidence ledger, source fingerprinting, provenance, cache invalidation, targeted migration, and controlled production acceptance are complete.

### CA-01 — Canonical Campaign Brain

**PASS / CLOSED.**

Merged implementation covers:

- canonical `campaign_brain`;
- deterministic `brain_id`;
- source hash;
- structured rule records;
- mandatory / optional / unknown requirements;
- evidence IDs and source references;
- platform/language/audience scope;
- variants and unresolved conflicts;
- legacy `ai_rules.rules` compatibility projection;
- six-shape deterministic corpus acceptance;
- bounded Ryan production persistence.

CA-01 production acceptance: GitHub Actions run `36279279316`.

Successful job:
`targeted-acceptance`

Successful steps:
- Targeted Ryan production re-analysis
- Verify persisted acceptance contract

## Important audit note

Do not cite **219 tests passed** as independently verified from this agent session. The available GitHub connector does not expose the complete CI test artifact/count. The repository's CA-01 test definitions and bounded production acceptance are verified, but the exact aggregate test count remains unverified.

Also note that the current preservation gate maps `critical_rule_preservation` to mandatory preservation and has targeted platform-scope checks. That is an acceptable CA-01 baseline, but not proof that the two metrics are conceptually independent. Future hardening should make that distinction explicit.

## Exact next slice

**CA-02 — Campaign Critic**

Before implementation:

1. define critic hypothesis;
2. define seeded findings from the existing golden corpus;
3. define severity contract: CRITICAL / WARNING / AMBIGUITY / INFO;
4. define acceptance metrics;
5. add regression fixtures/tests;
6. implement the smallest critic slice;
7. run deterministic tests;
8. run controlled E2E only where required;
9. document evidence;
10. stop at the CA-02 gate.

Do not reopen CA-00 or CA-01 unless a regression is proven.

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
- revive obsolete Termux/product-image workflows; repository scope is clipping only.
