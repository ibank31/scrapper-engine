# Scrapper Engine — Phase 3 Completion Report

**Date:** 24 September 2026
**Scope:** P3-A through P3-D
**Status:** Complete locally; provider deployment and mutation intentionally not performed

## Outcome

Phase 3 turns the approved Buffer action into an observable, idempotent, per-channel delivery workflow. The product contract is deliberately queue-based: the engine adds approved posts to the provider's next queue slot and displays provider-resolved `dueAt` when returned. It does not claim exact timestamp scheduling because that provider capability is not verified in the repository contract.

```text
Approved preview → server channel resolution → no-mutation preflight
→ stable per-channel operation → Buffer mutation
→ scheduled / unknown / failed outcome → reconciliation or targeted retry
```

## Slice results

| Slice | Result |
|---|---|
| P3-A — Schedule semantics | `core/schedule_semantics.py` defines `next_queue_slot`, `schedule-capability-v1`, the Buffer `automatic/addToQueue` mode, and IANA local-to-UTC conversion. DST and invalid-zone tests are included. |
| P3-B — Delivery operation model | `core/delivery_operations.py` defines stable operation keys, canonical payload hashes, safe transitions, and operation payloads. D1 persists the operation identity, exact payload evidence, intent, state, retry class, provider response, dueAt, and timestamps. |
| P3-C — Channel and mutation hardening | Buffer channels are enumerated server-side behind review authorization. Client-supplied service metadata is ignored. Preflight resolves selected IDs against authoritative channels, applies server-side limits, and does not call `createPost`. Mutation requires approved provenance, validates provider post ID and schedule evidence, and classifies malformed/timeout results as `unknown`. |
| P3-D — Operations UI | Preview responses include operation rows. Worker Pages displays channel, state, schedule timezone/local-UTC evidence, provider dueAt, error, and controls for failed-operation retry and unknown-operation reconciliation. Batch responses distinguish `all_succeeded`, `partial`, `none`, and `unknown`. |

## State and idempotency contract

Each operation is uniquely identified by preview ID, channel ID, schedule revision, and caption revision. The stable key is persisted as the primary key and a composite uniqueness constraint is also present. A scheduled or published operation is returned idempotently instead of creating another provider post. An `attempting` or `unknown` operation is not replayed automatically. A failed operation can be explicitly reset to pending by an operator; an unknown operation must be reconciled first.

Provider success is accepted only when the response contains a non-empty post ID and schedule evidence (`dueAt` or channel evidence). A response without these fields is `unknown`, even if the transport request succeeded. Partial multi-channel results remain visible per channel and cannot become a global success.

## Provider and deployment safety

No production Buffer post, D1 migration, Cloudflare deployment, or Whop mutation was executed. The implementation adds self-healing D1 migration statements, but these require a separately authorized deployment and smoke test. The reconciliation query is server-side and must be verified against the actual Buffer GraphQL schema/account before production use.

## Verification

```text
131 Python tests: OK
Python compilation and compileall: OK
pip check: OK
Node syntax checks for Cloudflare and Worker Pages: OK
git diff --check: OK
```

The suite includes IANA/DST fixtures, stable operation keys, payload hash changes, unsafe transition rejection, server-side channel-resolution assertions, no-mutation preflight assertions, malformed provider-success checks, duplicate protection, partial/unknown outcome checks, and operations UI assertions. Existing subtitle tests continue to emit two non-failing unclosed-file `ResourceWarning` messages.

## Explicit non-goals

Phase 3 does not implement retention dependency safety, provider request budgets, bounded jitter retry policy, stuck-operation alerts, rerender lineage, staging acceptance workflows, or Whop automation. These remain later roadmap work.

## Next phase

The next roadmap work is **Phase 4**, beginning with P4-A retention safety. It must start as a separate bounded task after this Phase 3 commit and documentation review.
