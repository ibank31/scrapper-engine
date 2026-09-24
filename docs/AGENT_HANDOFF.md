# Scrapper Engine — Active Agent Handoff

**Updated:** 24 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Base commit:** `0f1f069` — split the remaining roadmap into bounded phases

## Documentation policy

This file is the active handoff. Superseded handoffs are archived under `docs/archive/` with their original date. Update this file and `STATUS.md` whenever a roadmap slice is completed or a new slice begins.

## Current product contract

The system starts from a user-selected campaign, snapshots campaign rules, downloads official campaign materials, transcribes source media, finds complete moments, renders vertical previews, validates them against campaign rules, and places reviewable previews in the dashboard. Publishing remains manual. `plan.json` and its `source_of_truth` fields are authoritative.

## Current implementation state

Phase 0 provenance, approval, and execution fencing is complete in commit `0b6e019`.

P1-A — Output contract foundation is implemented in the current working tree and verified locally. Compiled plans now carry a versioned `output_contract` with exactly two outputs, one `tier_1`, one `tier_2`, duration bounds, and a distinctness profile. Pure validators return `blocked_invalid_output_contract` for malformed contracts. No candidate classification, selection gate, rendering change, provider mutation, or delivery change is included.

P1-B is the next bounded slice: candidate identity and tiers. It must add deterministic candidate identity and classification only, preserve candidate counts reaching review, and retain duplicate-source evidence before source-count truncation. **P1-B is currently blocked:** the repository audit documents that the business semantics and evidence requirements for clip-level Tier 1 and Tier 2 are undefined. The existing `EN/Tier-1` campaign metadata flag is not a candidate tier and must not be used as one. Do not implement a classifier until the business owner supplies the taxonomy, evidence, and handling for unclassifiable candidates.

## Active validation baseline

```bash
python3 -m unittest discover -s tests -q
python3 -m py_compile core/*.py modules/*/*.py worker/*.py
python3 -m compileall -q core modules worker
python3 -m pip check
git diff --check
```

The P1-A working tree verification completed with **95 tests passing**. The focused P1-A suite contains 11 tests.

## Slice boundaries

- Execute one roadmap slice per session.
- Do not start P1-C or later work while implementing P1-B.
- Do not infer Tier 1/Tier 2 from campaign metadata, audience flags, rank, score, source order, or any other proxy.
- If the P1-B business taxonomy is still missing, document the dependency and stop rather than implementing a guessed classifier.
- Do not modify Buffer, Instagram, TikTok, YouTube delivery, scheduling, captions, subtitles, audio tags, or production provider state for P1-B.
- Update this handoff and `STATUS.md` before stopping after each slice.
- Archive superseded documentation rather than silently leaving contradictory active instructions.

## Relevant entry points

- `docs/IMPLEMENTATION_ROADMAP.md` — authoritative slice definitions and acceptance gates.
- `STATUS.md` — current milestone and verification state.
- `core/campaign_rules.py` — compiled campaign plan.
- `core/output_contract.py` — P1-A contract construction and validation.
- `core/clip_candidates.py` — candidate generation and deterministic ranking.
- `modules/clipping/select.py` — candidate artifact writer.
- `worker/run_job.py` — worker stage orchestration; do not broaden scope without a slice requirement.

## Archived handoff

The superseded 23 September handoff is preserved at [`docs/archive/2026-09-24/AGENT_HANDOFF-2026-09-23.md`](archive/2026-09-24/AGENT_HANDOFF-2026-09-23.md).
