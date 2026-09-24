# Scrapper Engine — Active Agent Handoff

**Updated:** 24 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Phase:** Phase 2 complete; Phase 3 not started

## Current product contract

The user selects a campaign in Worker Pages. The worker snapshots campaign rules, downloads official materials, transcribes sources, classifies candidates for explicit audience targets, selects one distinct Tier 1 and one distinct Tier 2 output, renders and validates the pair, and publishes previews to review. Reviewers can edit captions only through immutable validated revisions. After human approval, the user sends the approved revision and artifact to Buffer; after upload, the user submits manually to Whop. Whop submission remains outside the engine.

## Phase 2 completion

Phase 1 remains complete through P1-E. Phase 2 is complete through P2-E:

- **P2-A:** Compiled plans now contain versioned provider-neutral Instagram, TikTok, and YouTube profiles with required/suggested handles, hashtags, disclosures, CTA, phrases, prohibited terms, caption limits, subtitle mode, sound policy, schedule capability, and rule evidence. Document-only requirements normalize to all applicable platforms.
- **P2-B:** Caption revisions are immutable records with exact text, structured fields, platform, revision number, editor, character-count method, payload hash, rules hash, and platform-profile version. The API persists revision history and approval consumes the current revision ID/hash.
- **P2-C:** Python and Cloudflare validators return field-level failures for mandatory fields, prohibited terms, length, rules hash, handles, hashtags, disclosures, CTA, and phrases. Caption save, approval, and Buffer preflight use the same deterministic compliance contract. Compliance failure happens before any Buffer provider request.
- **P2-D:** Subtitle delivery is explicit: `burned_in`, `native_caption_file`, `none`, or `manual_required`. Typography, safe area, cue limits, language, transcript availability, compliance, and artifact hash are persisted in render evidence and review metadata. Missing transcripts are never silently considered compliant.
- **P2-E:** Sound and native tags are normalized with platform, policy, source/track ID, evidence, native tags, and one of `verified`, `unsupported`, `manual_required`, or `failed`. Local metadata and Buffer queue operations cannot manufacture `verified` status.

## Operational and safety boundaries

No provider mutation behavior was changed by Phase 2. Buffer remains a post-approval queue action and now has a deterministic preflight before the first provider request. No production Cloudflare deployment, D1 migration, Buffer mutation, or Whop mutation was performed by this implementation session. D1 schema and self-healing migrations must be deployed and smoke-tested separately.

Phase 2 does not implement exact timestamp scheduling, provider reconciliation, native platform audio verification, or Whop automation. `verified` sound status requires provider evidence from a later integration slice.

## Verification baseline

```bash
python3 -m unittest discover -s tests -q   # 123 tests, OK
python3 -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python3 -m compileall -q core modules worker
python3 -m pip check
node --check cloudflare/caption_compliance.js
node --check cloudflare/api.js
node --check web/app.js
git diff --check
```

The existing subtitle tests still emit two unrelated `ResourceWarning` messages for unclosed fixture reads; they do not fail the suite. Gemini mock/retry diagnostics are expected in campaign-AI tests and do not indicate a production request.

## Next milestone

The next planned slice is **Phase 3 — operational provider integrations**, beginning with the roadmap-defined P3-A slice. It must remain separate from Phase 2. Do not perform a production Cloudflare deployment, Buffer migration, or provider smoke test without an explicit deployment task.

## Relevant entry points

- `docs/IMPLEMENTATION_ROADMAP.md` — authoritative roadmap and acceptance gates.
- `docs/PHASE_1_COMPLETION_2026-09-24.md` — Phase 1 report.
- `docs/PHASE_2_COMPLETION_2026-09-24.md` — Phase 2 report.
- `STATUS.md` — current milestone and verification state.
- `core/platform_profiles.py` — P2-A profiles.
- `core/caption_revisions.py` and `core/caption_compliance.py` — P2-B/P2-C contracts.
- `core/subtitle_delivery.py` — P2-D profile and artifact evidence.
- `core/sound_tags.py` — P2-E normalization.
- `cloudflare/api.js` and `cloudflare/caption_compliance.js` — API persistence, approval, and provider preflight.
- `modules/clipping/render.py` and `modules/clipping/review_queue.py` — delivery metadata generation.

## Archived handoff

The superseded Phase 1 handoff is preserved at [`docs/archive/2026-09-24/AGENT_HANDOFF-PHASE1-2026-09-24.md`](archive/2026-09-24/AGENT_HANDOFF-PHASE1-2026-09-24.md).
