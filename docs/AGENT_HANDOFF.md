# Scrapper Engine — Active Agent Handoff

**Updated:** 24 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Phase:** Phase 1 complete; Phase 2 not started

## Current product contract

The user selects a campaign in Worker Pages. The worker snapshots the campaign rules, downloads official materials, transcribes the sources, classifies eligible candidates for the explicit audience targets, selects one materially distinct Tier 1 output and one materially distinct Tier 2 output, renders and validates the pair as an all-or-nothing unit, and publishes the resulting previews to the review dashboard. The user manually approves previews, sends approved media to Buffer, waits for the scheduled upload, and submits manually to Whop. Whop submission is outside the engine.

## Phase 1 completion

Phase 1 is complete through P1-E:

- **P1-A:** Compiled plans carry a versioned two-output contract with `expected_count=2`, `tier_1=1`, `tier_2=1`, duration bounds, and a distinctness profile.
- **P1-B:** Candidates carry stable identity, normalized source identity, source/transcript/rules hashes, classifier version, tier evidence, and selection rationale. Audience tiers are explicit campaign audience targets; missing or ambiguous rules produce `unknown`, never a guessed tier.
- **P1-C:** A pure selection gate requires one eligible Tier 1 and one eligible Tier 2 candidate and records bounded near-miss diagnostics. Failure blocks before any render attempt.
- **P1-D:** Rendering requires exactly two artifacts and validation requires exactly two non-failing records. Missing renders, malformed validation, or one failed validation blocks the pair before review.
- **P1-E:** D1, manifest, API, and Worker Pages review UI expose the output contract, tier, candidate ID, source identity, artifact hash, and pairwise distinctness evidence.

The implementation is committed in the current Phase 1 commits, with the latest Phase 1 slice pending final commit after documentation verification.

## Operational and safety boundaries

Buffer remains a post-approval queue action. The engine does not schedule Whop submissions and does not publish without human approval. No production Cloudflare deployment, D1 migration, Buffer mutation, or Whop mutation was performed by the Phase 1 implementation session. Cloudflare code includes self-healing schema definitions, but deployment must be handled as a separate explicit action.

The current Buffer queue semantics remain “add to the channel queue”; exact timestamp scheduling is not part of Phase 1. Platform captions, subtitle profiles, sound/native tags, delivery operations, reconciliation, retention, and recovery remain Phase 2–4 work.

## Verification baseline

The completed Phase 1 tree passed:

```bash
python3 -m unittest discover -s tests -q   # 110 tests, OK
python3 -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python3 -m compileall -q core modules worker
python3 -m pip check
node --check cloudflare/api.js
node --check web/app.js
git diff --check
```

The existing subtitle tests still emit two unrelated `ResourceWarning` messages for unclosed fixture reads; they do not fail the suite.

## Next milestone

The next planned slice is **P2-A — platform rule profiles**. It must remain separate from Phase 1 and must not be started implicitly. P2-A covers versioned Instagram/TikTok/YouTube rule profiles and capability types; it must not change provider mutation behavior.

## Relevant entry points

- `docs/IMPLEMENTATION_ROADMAP.md` — authoritative roadmap and slice acceptance contracts.
- `docs/PHASE_1_COMPLETION_2026-09-24.md` — Phase 1 implementation and acceptance report.
- `STATUS.md` — current milestone and verification state.
- `core/output_contract.py` — P1-A contract construction and validation.
- `core/candidate_identity.py` — P1-B identity, audience classification, and source evidence.
- `core/output_selection.py` — P1-C exact pair selection and distinctness evidence.
- `core/output_gate.py` — P1-D aggregate render/validation gate.
- `worker/run_job.py` — worker orchestration and review manifest construction.
- `cloudflare/api.js` and `cloudflare/schema.sql` — P1-E persistence/API contract.
- `web/app.js` — dashboard contract visibility.

## Archived handoff

The superseded P1-B handoff is preserved at [`docs/archive/2026-09-24/AGENT_HANDOFF-P1B-2026-09-24.md`](archive/2026-09-24/AGENT_HANDOFF-P1B-2026-09-24.md).
