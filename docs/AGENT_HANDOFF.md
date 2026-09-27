# Scrapper Engine — Active Agent Handoff

**Updated:** 27 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `feat/ca02-campaign-critic`
**CA-01 main baseline:** `b0180f1d96644f3d114c4860be4ba744b76e70b0`

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

## Current milestone

### CA-02 — Campaign Critic

**Implementation complete; production acceptance pending merge.**

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

The controlled workflow has been extended to persist and verify `campaign_critic` for the bounded Ryan acceptance. It will assert Brain/critic identity and source-hash linkage and reject critical findings. No production acceptance claim is made until that merged workflow completes.

## Exact next action

1. Commit and push CA-02 implementation and documentation.
2. Open/merge the bounded CA-02 pull request without Buffer or publishing mutation.
3. Verify the controlled Ryan workflow and persisted critic result.
4. If it passes, close CA-02 and begin **CA-03 — Rule Reconciliation**.

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
