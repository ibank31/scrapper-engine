# Scrapper Engine — Active Agent Handoff

**Updated:** 24 September 2026
**Repository:** `ibank31/scrapper-engine`
**Branch:** `main`
**Phase:** Phase 3 complete; Phase 4 not started

## Current product contract

The user selects a campaign in Worker Pages. The worker snapshots rules, gathers official assets, transcribes sources, classifies candidates for explicit audience tiers, selects one distinct Tier 1 and one distinct Tier 2 output, renders and validates the pair, and publishes previews to review. Reviewers edit captions only through immutable validated revisions. After approval, the user runs a server-side Buffer preflight and sends the approved artifact to the next Buffer queue slot. Buffer operations are tracked per preview/channel. The user submits manually to Whop; Whop submission remains outside the engine.

## Phase 3 completion

Phase 1 and Phase 2 remain complete. Phase 3 is complete through P3-D:

- **P3-A — Schedule semantics:** the product contract is explicitly `next_queue_slot`, not exact timestamp scheduling. Buffer capability is versioned as `schedule-capability-v1`; exact timezone-aware provider scheduling remains unverified. Pure IANA timezone conversion emits canonical UTC instants for intent evidence and includes DST fixtures.
- **P3-B — Delivery operation model:** `delivery_operations` is keyed by preview, channel, schedule revision, and caption revision through a stable operation key. Exact payload hash, schedule intent, provider state, retry class, attempt count, provider ID, dueAt, response, and errors are persisted. Unsafe state transitions and duplicate operation keys are rejected by the pure contract and D1 uniqueness.
- **P3-C — Channel and mutation hardening:** channel IDs and service metadata are resolved server-side from authenticated Buffer account data. The no-mutation preflight rejects unknown channels and unsupported caption lengths before `createPost`. Mutation requires exact approval provenance, accepts only valid provider post IDs plus schedule evidence, and maps malformed or thrown outcomes to `unknown`, never false `scheduled`.
- **P3-D — Operations UI:** Worker Pages displays per-channel operation state, local/UTC intent evidence, provider dueAt, errors, retryability, and reconciliation controls. Partial and unknown outcomes are not summarized as global success. Failed operations can be retried; unknown operations require reconciliation first.

## Operational and safety boundaries

No production Cloudflare deployment, D1 migration, Buffer mutation, or Whop mutation was performed by this implementation session. Provider calls remain an external operational boundary. The preflight performs authenticated channel discovery and deterministic checks but does not call `createPost`. Unknown provider outcomes are not replayed automatically.

The current schedule semantics intentionally say **next queue slot**. The engine does not claim exact UTC scheduling. Provider reconciliation uses a server-side provider lookup and must be tested against the account's actual Buffer GraphQL schema before production enablement.

Phase 3 does not implement retention safety, lifecycle retry budgets, stale-operation alerts, rerender lineage, staging workflows, or Whop automation. Those remain Phase 4/5 roadmap work.

## Verification baseline

```bash
python3 -m unittest discover -s tests -q   # 131 tests, OK
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

The next planned slice is **Phase 4 — retention safety and recovery**, beginning with P4-A. It must remain separate from Phase 3. Do not deploy D1 schema changes, enable provider mutations, or run a provider smoke test without a separately authorized deployment task.

## Relevant entry points

- `docs/IMPLEMENTATION_ROADMAP.md` — authoritative roadmap and acceptance gates.
- `docs/PHASE_1_COMPLETION_2026-09-24.md` — Phase 1 report.
- `docs/PHASE_2_COMPLETION_2026-09-24.md` — Phase 2 report.
- `docs/PHASE_3_COMPLETION_2026-09-24.md` — Phase 3 report.
- `STATUS.md` — current milestone and verification state.
- `core/schedule_semantics.py` — P3-A schedule contract.
- `core/delivery_operations.py` — P3-B operation identity and state machine.
- `cloudflare/api.js` and `cloudflare/schema.sql` — P3-C API hardening and D1 operations.
- `web/app.js` and `web/styles.css` — P3-D per-channel operations UI.

## Archived handoff

The superseded Phase 2 handoff is preserved at [`docs/archive/2026-09-24/AGENT_HANDOFF-PHASE2-2026-09-24.md`](archive/2026-09-24/AGENT_HANDOFF-PHASE2-2026-09-24.md).
