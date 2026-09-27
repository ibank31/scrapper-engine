# Scrapper Engine — Active Agent Handoff

**Updated:** 27 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Latest main SHA:** `47ab5d11935fe74406ed210a2db122a3d02e5f2d`

## Mission

Build a **campaign-agnostic Campaign Agent**. Clipping is the first execution vertical. Campaign discovery, evidence, material acquisition, strategy, execution, compliance, review, publishing, and outcome learning are reusable layers.

Ryan Zofay is a regression fixture, never a special production case.

## Closed milestones

### CA-00 — Evidence Contract

**PASS / CLOSED.** Evidence ledger, source fingerprinting, provenance, cache invalidation, targeted migration, and controlled production acceptance are complete.

### CA-01 — Canonical Campaign Brain

**PASS / CLOSED.** Merged implementation covers canonical `campaign_brain`, deterministic `brain_id`, source hash, structured rules, requirement semantics, evidence linkage, scope, variants/conflicts, compatibility projection, six-shape corpus acceptance, and bounded Ryan persistence.

Production acceptance: GitHub Actions run `36279279316`, successful `targeted-acceptance` job.

Do not cite the historical **219 tests** claim as independently verified from CI artifacts. The CA-01 preservation gate also maps critical preservation to mandatory preservation; this remains an accepted baseline limitation.

## Closed milestone

### CA-02 — Campaign Critic

**PASS / CLOSED.**

The critic is deterministic and read-only. It compares source/evidence against the canonical Brain and does not reconcile or mutate it. CA-03 owns conflict resolution.

Implemented in `core/campaign_critic.py` with minimal integration in `normalize_ai_result` as `campaign_critic`.

Required detection categories are covered:

1. missing rule;
2. duplicate rule;
3. contradiction;
4. unsupported inference;
5. platform scope mismatch;
6. lost value;
7. wrong CTA;
8. wrong handle;
9. wrong hashtag;
10. missing material requirement.

Findings are stable and serializable with deterministic `finding_id`, exact severity (`CRITICAL`, `WARNING`, `AMBIGUITY`, `INFO`), category, rule path, Brain rule IDs, evidence IDs, source references, reason, and `status=open`.

## Verification baseline

- focused CA-01/CA-02 tests: **52 passed**;
- full repository suite: **230 passed**;
- `python3 -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py`: passed;
- `python3 -m compileall -q core modules worker`: passed;
- `python3 -m pip check`: passed;
- `git diff --check`: passed;
- six-shape clean corpus produces no critic findings;
- seeded negative tests cover all ten required categories;
- Brain remains byte-for-byte unchanged by critique.

Controlled production acceptance passed in GitHub Actions run `36284355791` on the merged main SHA. The `targeted-acceptance` job verified persisted `campaign_critic`, Brain/critic identity and source-hash linkage, legacy compatibility, and zero critical findings without Buffer or publishing mutation.

Observed production result: `CRITIC_STATUS=review`, `CRITIC_FINDINGS=7`, `CRITICAL=0`. Warnings remain observable review signals and are not silently reconciled; resolution belongs to CA-03.

The same merged SHA passed `tests` run `36284355788` and `phase5-acceptance` run `36284355798`.

## Exact next slice

**CA-03 — Rule Reconciliation.**

CA-03 may consume the seven warning findings, but must not be started as part of the CA-02 closeout.

## Do not

- hard-code Ryan Zofay or any campaign;
- invent campaign rules;
- let the critic mutate or silently repair the Brain;
- resolve conflicts in CA-02;
- manually mutate D1 to bypass acceptance;
- rerun full AI migration when targeted migration is sufficient;
- spend premium AI calls on deterministic work;
- treat green CI as production proof;
- add unrelated product/affiliate automation;
- modify rendering, subtitles, Buffer publishing, or material downloader architecture.
