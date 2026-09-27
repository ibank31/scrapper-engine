# Scrapper Engine — Current Status

**Updated:** 27 September 2026
**Branch:** `main`
**Current direction:** Campaign Agent; clipping adalah vertical pertama
**Production:** Cloudflare Pages `clipper-engine`

## Mission

Build a **campaign-agnostic Campaign Agent**. Clipping adalah vertical pertama yang sedang dibuktikan production-grade; campaign intelligence, evidence, material intelligence, execution, compliance, review, publishing, outcome, dan learning adalah lapisan reusable.

```
campaign source → evidence → campaign brain → critic → reconciliation
→ production contract → material plan → clip strategy
→ render → compliance → simple human review → Buffer
```

Ryan Zofay is a regression case, not the product target.

## Latest verified repository state

Current merged `main`: `803997a3a3b221acd6c29e65b2a6003e7a7d9fb8` (CA-03 PR #48 plus generic CTA recovery PR #49). CA-00 → CA-02 historical acceptance remains recorded on `47ab5d11935fe74406ed210a2db122a3d02e5f2d`. No CA-00/CA-01/CA-02 implementation regression was found during this slice.

**Foundation chain verified:** CA-00 → CA-01 → CA-02 is executable, integrated, and has controlled production acceptance evidence. This proves the intelligence foundation, not the complete downstream Campaign Agent.

CA-01 production acceptance was verified by GitHub Actions run `36279279316`, including targeted Ryan re-analysis and persisted Campaign Brain verification. Do not claim that every production campaign has been migrated.

## CA-00 status

**PASS / CLOSED.** Do not add CA-00 features except regression fixes backed by evidence.

Evidence Contract is implemented and exercised through deterministic evidence/provenance logic, campaign-diversity fixtures, cache invalidation, and bounded production acceptance. Production migration remains targeted, not global.

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

### CA-02 verified execution chain

```
source → evidence → campaign_brain → campaign_critic → persisted AI result
```

Controlled production acceptance run `36284355791` on main SHA `47ab5d1` successfully verified persisted critic/Brain identity and source-hash linkage, legacy compatibility, and zero critical findings without Buffer or publishing mutation.

Observed production result: `CRITIC_STATUS=review`, `CRITIC_FINDINGS=7`, with `CRITICAL=0`. These warnings are observable review signals and remain intentionally unresolved for CA-03. They are not silent repairs.

The same merged SHA passed tests run `36284355788` and phase5-acceptance run `36284355798`.

### CA-02 verification baseline

- six-shape clean corpus: zero critic findings;
- seeded negative tests: all ten required detection categories;
- focused CA-01/CA-02 tests: **52 passed**;
- full repository suite: **230 passed**;
- compile, dependency, and diff checks passed in the recorded verification run.

These counts are accepted only where recorded by the CA-02 verification evidence; do not extrapolate them into a claim of complete production correctness.

## Next exact slice

**CA-03 — Rule Reconciliation: PASS / CLOSED** (merged PRs #48 and #49; main SHA `803997a3a3b221acd6c29e65b2a6003e7a7d9fb8`).

`normalize_ai_result()` persists `campaign_reconciliation` beside Brain and Critic; stale/mismatched cache identities are rejected. The follow-up makes annotated CTA values undergo the same deterministic source-evidence recovery as flat CTA values. **246 local tests passed**; Python compile, dependency, and diff checks passed. Main-branch tests (`36287752375`) and phase-5 acceptance (`36287752363`) passed.

Final bounded production run `36287752424` passed on merged main: reconciliation `review`, 40 rules, two Critic findings retained (one unresolved), 34 verified evidence items, zero unverified evidence, 100% evidence coverage, CTA preserved, and legacy compatibility. `CLIPPER_AUTO_QUEUE=0`; no Buffer publishing mutation or manual D1 edit. Several intervening provider reruns failed strict pre-existing evidence/CTA assertions; acceptance criteria were not weakened. The final main run passed after the generic annotation recovery fix.

CA-03 preserves evidence IDs/source references, stable rule/conflict links, requirement semantics, and scoped variants. No-precedence ambiguity remains explicit, evidence-only missing rules are reconstructed as quoted source text, and unsupported inference is not promoted. CA-02 remains detection-only. See `docs/CA03_ACCEPTANCE_CONTRACT.md`. Next phase is CA-04 Production Contract Compiler; it was not started in this task.

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
