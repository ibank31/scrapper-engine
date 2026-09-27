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

**PASS / CLOSED.** Evidence ledger, source fingerprinting, provenance, cache invalidation, targeted migration, and controlled production acceptance are complete. Production migration is bounded, not global.

### CA-01 — Canonical Campaign Brain

**PASS / CLOSED.** Merged implementation covers canonical `campaign_brain`, deterministic `brain_id`, source hash, structured rules, requirement semantics, evidence linkage, scope, variants/conflicts, compatibility projection, six-shape corpus acceptance, and bounded Ryan persistence.

Production acceptance: GitHub Actions run `36279279316`, successful `targeted-acceptance` job.

Do not cite the historical **219 tests** claim as independently verified from CI artifacts. The CA-01 preservation gate also maps critical preservation to mandatory preservation; this remains an accepted baseline limitation.

### CA-02 — Campaign Critic

**PASS / CLOSED.**

The critic is deterministic and read-only. It compares source/evidence against the canonical Brain and does not reconcile or mutate it. CA-03 owns conflict resolution.

Implemented in `core/campaign_critic.py` with integration in `normalize_ai_result` as `campaign_critic`.

The ten required detection categories are covered, findings are deterministic and serializable, and seeded negative cases verify the defect classes while legitimate variants/scopes/conflicts are protected from false duplicate/contradiction classification.

## Verified CA-00 → CA-02 chain

The foundation is now proven as an executable chain, not merely three isolated milestones:

```
source
  ↓
CA-00 Evidence
  ↓
CA-01 Campaign Brain
  ↓
CA-02 Campaign Critic
  ↓
persisted AI intelligence
```

Controlled acceptance run `36284355791` on SHA `47ab5d1` verified persisted `campaign_critic`, Brain/critic identity and source-hash linkage, legacy compatibility, and zero critical findings without Buffer/publishing mutation.

Observed result: `CRITIC_STATUS=review`, `CRITIC_FINDINGS=7`, `CRITICAL=0`. The seven warnings are intentionally left for CA-03 reconciliation. This is a successful detection gate, not proof that all campaign semantics are already resolved.

The same SHA passed tests run `36284355788` and phase5-acceptance run `36284355798`.

## Verification baseline

- focused CA-01/CA-02 tests: **52 passed**;
- full repository suite: **230 passed**;
- compile/dependency/diff checks passed in the recorded verification run;
- six-shape clean corpus produces no critic findings;
- seeded negative tests cover all ten required categories;
- Brain remains unchanged by critique.

## Exact next slice

**CA-03 — Rule Reconciliation.**

CA-03 may consume the seven warning findings and must preserve evidence provenance. It owns deterministic reconciliation, explicit conflict state, and resolution provenance. It must not silently overwrite source-backed facts and must not be implemented as an extension of CA-02.

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
- modify rendering, subtitles, Buffer publishing, or material downloader architecture during CA-03.
