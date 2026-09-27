# Scrapper Engine — Active Agent Handoff

**Updated:** 27 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `feat/ca06-clip-strategy`
**Latest merged SHA:** `14d49cfbabde15634bfe278bbb739022279dc65c` (CA-05 PR #52; PRs #48 and #49 are historical CA-03)

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

## CA-03 — Rule Reconciliation (PASS / CLOSED)

`campaign_reconciliation` is emitted beside Brain/Critic in normalized and persisted intelligence. The cache gate requires the reconciliation contract and matching Brain/Critic/source/campaign identities. The legacy rules projection remains unchanged. Follow-up PR #49 ensures CTA rule annotations use the same deterministic source-evidence recovery as the flat CTA projection.

Local verification: **246 tests passed**; `py_compile`, `compileall`, `pip check`, and `git diff --check` passed. Main test run `36287752375` and phase-5 run `36287752363` passed. Final bounded production acceptance run `36287752424` passed on main: reconciliation `review`, 40 rules, two Critic findings preserved (one unresolved), 34 verified evidence items, zero unverified, full coverage, CTA and legacy compatibility, and no Buffer mutation. Several earlier provider reruns failed strict evidence/CTA assertions; the final successful run kept all gates unchanged and involved no manual D1 changes.

See `docs/CA03_ACCEPTANCE_CONTRACT.md` for schema, policy, and gates. Unresolved findings remain observable; campaign behavior is not hard-coded.

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


## CA-04 — Production Contract Compiler (PASS / CLOSED)

CA-04 merged in PR #51 at main SHA `deee8cd4ca3373732b33851e9339aa6e43557bd2`. `core/production_contract.py` compiles CA-03 reconciliation deterministically into five domains and preserves requirement semantics, scope, and evidence provenance. Normalization persists `production_contract` in the existing intelligence envelope; the cache gate validates its identity linkage. CI run `36289080543` and phase5 acceptance run `36289078676` succeeded. See `docs/CA04_ACCEPTANCE_CONTRACT.md` and `scripts/accept_ca04.py`.

## CA-05 — Material Intelligence (PASS / CLOSED)

CA-05 is PASS / CLOSED in merged PR #52 at main SHA `14d49cfbabde15634bfe278bbb739022279dc65c`. It consumes the CA-04 Material Contract and builds a deterministic, evidence-backed Material Plan while preserving scope, provenance, explicit fallback policy, asset identity, lifecycle state, and cache linkage. Local bounded acceptance passed with 264 tests and verified missing mandatory material → `blocked`, verified candidate → `ready`, provenance coverage `1.0`, legacy compatibility, and no Buffer/D1 mutation.

## CA-06 — Campaign-aware Clip Strategy (PASS / CLOSED)

CA-06 consumed the Production Contract and Material Plan and emitted additive `clip_strategy` persistence. PR #53 merged at main SHA `ce3ae8f2116e34ec8f8e702f8deb4cc45bcc76bb`. The compiler is deterministic and read-only: it preserves platform/duration constraints and evidence lineage, selects only usable material, keeps timestamp uncertainty explicit, and never silently activates fallbacks. PR checks, Cloudflare Pages, post-merge tests, phase5 acceptance, and Ryan acceptance passed. Limitation: segment localization without structured timestamps remains downstream/manual review. No renderer, publisher, Buffer mutation, D1 migration, or CA-07 work was included. Stop at CA-06; the next agent receives a CA-07 handoff.
