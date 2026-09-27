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

CA-00, CA-01, and CA-02 implementation are merged on `main` at `47ab5d11935fe74406ed210a2db122a3d02e5f2d`.

CA-01 production acceptance was verified by GitHub Actions run `36279279316`, including targeted Ryan re-analysis and persisted Campaign Brain verification. Do not claim that every production campaign has been migrated.

## CA-00 status

**PASS / CLOSED.** Do not add CA-00 features except regression fixes backed by evidence.

## CA-01 status

**PASS / CLOSED.** The canonical Brain, deterministic identity, source-backed rule/evidence linkage, structured requirements, scope, variants/conflicts, compatibility projection, six-shape corpus, and bounded Ryan persistence are accepted.

Audit limitations retained from the CA-01 handoff:

- Do not cite the historical **219 tests** claim as independently verified from CI artifacts.
- `critical_rule_preservation` currently derives from mandatory preservation; platform scope is exercised through targeted checks. This is accepted CA-01 baseline behavior, not a claim that those metrics are conceptually identical.

## CA-02 status

**PASS / CLOSED.**

The deterministic Campaign Critic now:

- compares source/evidence against the canonical Brain without mutating it;
- emits stable, serializable findings with `finding_id`, severity, category, rule/evidence links, and status;
- detects missing rules, duplicates, contradictions, unsupported inference, scope mismatch, lost values, wrong CTA/handle/hashtag, and missing material requirements;
- preserves legitimate variants and unresolved conflicts as non-duplicate/non-contradictory cases;
- is exposed as `campaign_critic` beside the authoritative `campaign_brain` and legacy compatibility projection.

Local CA-02 verification:

- six-shape corpus: clean Brain produces zero critic findings;
- seeded negative tests cover all ten required detection categories;
- focused CA-01/CA-02 tests: **52 passed**;
- full repository suite: **230 passed**;
- `py_compile`, `compileall`, `pip check`, and `git diff --check`: passed.

Controlled production acceptance passed in GitHub Actions run `36284355791` on the merged main SHA. The `targeted-acceptance` job verified persisted critic/Brain identity and source-hash linkage, legacy compatibility, and zero critical findings without Buffer or publishing mutation.

Observed production result: `CRITIC_STATUS=review`, `CRITIC_FINDINGS=7`, with `CRITICAL=0`. The seven warnings are observable review signals, not silent repairs or execution blockers; their detailed reconciliation remains CA-03 scope.

The same merged SHA also passed `tests` run `36284355788` and `phase5-acceptance` run `36284355798`.

## Next exact slice

**CA-03 — Rule Reconciliation.**

CA-03 owns resolution of conflicts; CA-02 must remain detection-only.

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
