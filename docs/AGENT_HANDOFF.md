# Scrapper Engine — Active Agent Handoff

**Updated:** 24 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Phase:** Phase 4 complete; Phase 5 not started

## Current product contract

The user selects a campaign in Worker Pages. The worker snapshots rules, gathers official assets, transcribes sources, classifies candidates for explicit audience tiers, selects one distinct Tier 1 and one distinct Tier 2 output, renders and validates the pair, and publishes previews to review. Reviewers edit captions only through immutable validated revisions. After approval, the user runs server-side Buffer preflight and sends the approved artifact to the next Buffer queue slot. Buffer operations are tracked per preview/channel, protected from duplicate creation, reconciled, and retained until terminal. The user submits manually to Whop; Whop submission remains outside the engine.

## Phase 4 completion

Phase 1 through Phase 3 remain complete. Phase 4 is complete through P4-C:

- **P4-A — Retention safety:** cleanup now evaluates preview status and delivery-operation dependencies before deleting objects or metadata. Planned, pending, attempting, unknown, scheduled, and unresolved operations retain media. Review and approval windows are status-aware. Every decision is written to `retention_events`. A media probe checks stable HTTPS, video content type, positive length, byte-range support, and reports artifact evidence.
- **P4-B — Recovery and capacity:** provider errors are classified into transient, throttled, permanent, unknown, and capacity classes. Retries are bounded to three attempts with deterministic jitter policy. Request-budget ledger and per-channel capacity guards run before mutation. Provider reconciliation maps scheduled, published, and failed states; missing provider objects become failed. Stuck attempting/unknown operations are exposed as server-side high-severity alerts.
- **P4-C — Rerender lineage:** a rerender request creates a new `pending_render` preview revision with `parent_preview_id`, revision number, and render revision, while preserving the parent. The previous preview is marked `changes_requested`, approval fields are cleared, and the new revision must re-enter rendering, caption validation, and review. Existing execution generation and claim fencing remain in place for stale workers.

## Operational and safety boundaries

No production Cloudflare deployment, D1 migration, Buffer mutation, provider smoke test, or Whop mutation was performed by this implementation session. The D1 schema and self-healing migrations require a separately authorized deployment. Provider request accounting and reconciliation are implemented server-side but must be tested against the actual Buffer GraphQL schema/account before production enablement.

Phase 4 does not implement known-good fixture staging, full staging failure-matrix execution, controlled pilot, or Whop automation. Those remain Phase 5 roadmap work.

## Verification baseline

```bash
python3 -m unittest discover -s tests -q   # 138 tests, OK
python3 -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python3 -m compileall -q core modules worker
python3 -m pip check
node --check cloudflare/api.js
node --check cloudflare/caption_compliance.js
node --check web/app.js
git diff --check
```

The existing subtitle tests still emit two unrelated `ResourceWarning` messages for unclosed fixture reads; they do not fail the suite. Gemini mock/retry diagnostics are expected in campaign-AI tests and do not indicate a production request.

## Next milestone

The next planned slice is **Phase 5 — acceptance and staging readiness**, beginning with P5-A. It must remain separate from Phase 4. Do not deploy D1 schema changes, enable provider mutations, or run a provider smoke test without a separately authorized deployment task.

## Relevant entry points

- `docs/IMPLEMENTATION_ROADMAP.md` — authoritative roadmap and acceptance gates.
- `docs/PHASE_1_COMPLETION_2026-09-24.md` — Phase 1 report.
- `docs/PHASE_2_COMPLETION_2026-09-24.md` — Phase 2 report.
- `docs/PHASE_3_COMPLETION_2026-09-24.md` — Phase 3 report.
- `docs/PHASE_4_COMPLETION_2026-09-24.md` — Phase 4 report.
- `STATUS.md` — current milestone and verification state.
- `core/retention_safety.py` — retention dependency and media reachability contract.
- `core/recovery_policy.py` — error classes, retry budget, jitter, capacity, and stuck alerts.
- `cloudflare/api.js` and `cloudflare/schema.sql` — cleanup evidence, request ledger, lineage, and operation recovery.

## Archived handoff

The superseded Phase 3 handoff is preserved at [`docs/archive/2026-09-24/AGENT_HANDOFF-PHASE3-2026-09-24.md`](archive/2026-09-24/AGENT_HANDOFF-PHASE3-2026-09-24.md).
