# Scrapper Engine — Active Agent Handoff

**Updated:** 25 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Phase:** Phase 5 local acceptance complete; controlled pilot not executed

## Current product contract

The user selects a campaign in Worker Pages. The worker snapshots rules, gathers official assets, transcribes sources, classifies candidates for explicit audience tiers, selects one distinct Tier 1 and one distinct Tier 2 output, renders and validates the pair, and publishes previews to review. Reviewers edit captions only through immutable validated revisions. After approval, the user runs server-side Buffer preflight and sends the approved artifact to the next Buffer queue slot. Buffer operations are tracked per preview/channel, protected from duplicate creation, reconciled, and retained until terminal. The user submits manually to Whop; Whop submission remains outside the engine.

## Phase 5 completion status

Phase 1 through Phase 4 remain complete. Phase 5 acceptance work is complete locally through P5-B and the P5-C evidence contract:

- **P5-A — Known-good fixture:** `scripts/run_known_good_fixture.py` creates a synthetic legal 38-second 9:16 MP4, generated word-timestamp transcript, campaign plan with explicit 15–30 second rules, two audience-tier expectations, distinct candidate pair, rendered subtitle artifacts, technical/editorial validation, and pending review manifest. It performs the complete intake → transcript → candidate → selection → render → validation → review-manifest trace.
- **P5-B — Staging readiness:** `core/staging_matrix.py` and `scripts/run_staging_failure_matrix.py` cover approval failure, caption failure, unsupported field, duplicate click, timeout, partial result, cleanup dependency, and stale worker. The matrix is local-mock only and hard-fails when provider mutation is enabled.
- **P5-C — Controlled pilot evidence:** `core/pilot_evidence.py` defines the required job/run/rules/source/operation/provider/due-time/terminal/rollback evidence and requires human confirmation immediately before mutation. The contract is ready, but no controlled pilot was executed.

## Verification baseline

```bash
python3 -m unittest discover -s tests -q   # 142 tests, OK
python3 scripts/run_known_good_fixture.py --out /tmp/scrapper-known-good-trace
python3 scripts/run_staging_failure_matrix.py --out /tmp/phase5-failure-matrix.json
python3 -m py_compile core/*.py modules/*/*.py worker/*.py scripts/*.py tests/*.py
python3 -m compileall -q core modules worker
python3 -m pip check
node --check cloudflare/api.js
node --check cloudflare/caption_compliance.js
node --check web/app.js
git diff --check
```

The existing subtitle tests still emit two unrelated `ResourceWarning` messages for unclosed fixture reads; they do not fail the suite. Gemini mock/retry diagnostics are expected in campaign-AI tests and do not indicate a production request.

## 25 September 2026 — progressive intake hardening

The Drive/YouTube intake path was hardened after a controlled run exhausted the GitHub runner disk while attempting to download an entire Drive folder. The current implementation is metadata-first: Drive folders are enumerated completely before download, per-asset manifest rows are retained, assets are cheaply ranked from metadata, distinct top-level sources receive fair download opportunities, and download count/byte/disk budgets are enforced.

Current worker defaults are 8 downloaded assets, 2 GiB cumulative download budget, 1 GiB disk safety margin, and 6 sources for deep transcription/selection. Discovery is not capped by the deep-analysis limit. Drive downloads and YouTube/direct downloads use guarded temporary files where applicable; disk/quota limits produce deferred states rather than filling the runner.

The worker consumes only manifest-confirmed completed video files for preflight/deep analysis, and deletes non-selected raw source files after final pair selection to reduce render-stage disk pressure. `source_manifest` now represents top-level references, while `asset_manifest` represents individual assets.

The repository test workflow was executed through temporary PR #7 against this implementation. Result: **154 tests passed**, semantic fixture evaluation passed, and both Cloudflare/Worker Pages JavaScript syntax checks passed. The PR was closed after verification. The live controlled Backyard Breaks intake probe is still not executed from this agent because the GitHub connector exposes workflow read/re-run operations but not workflow_dispatch; therefore no claim is made that the production Drive folder has returned an exact 65-asset runtime count yet.

## Safety boundary

No production Cloudflare deployment, D1 migration, Buffer mutation, provider smoke test, staging-provider mutation, or Whop mutation was performed. The new workflow is non-production and sets provider mutation off. The controlled pilot remains blocked until a dedicated low-volume account, staging evidence, exact rollback procedure, and explicit human confirmation immediately before the first provider mutation are available.

Do not enable broad automation in the same task as the first pilot. Stop after pilot evidence is complete.

## Relevant entry points

- `docs/IMPLEMENTATION_ROADMAP.md` — authoritative roadmap and acceptance gates.
- `docs/PHASE_5_COMPLETION_2026-09-24.md` — Phase 5 report.
- `scripts/run_known_good_fixture.py` — local legal end-to-end trace.
- `scripts/run_staging_failure_matrix.py` — provider-off failure matrix.
- `core/pilot_evidence.py` — controlled-pilot evidence gate.
- `.github/workflows/phase5-acceptance.yml` — non-production CI workflow.
- `STATUS.md` — current milestone and verification state.

## Archived handoff

The superseded Phase 4 handoff is preserved at [`docs/archive/2026-09-24/AGENT_HANDOFF-PHASE4-2026-09-24.md`](archive/2026-09-24/AGENT_HANDOFF-PHASE4-2026-09-24.md).
