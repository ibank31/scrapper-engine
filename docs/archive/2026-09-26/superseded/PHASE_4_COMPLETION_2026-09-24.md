# Scrapper Engine — Phase 4 Completion Report

**Date:** 24 September 2026
**Scope:** P4-A through P4-C
**Status:** Complete locally; production deployment and provider mutation intentionally not performed

## Outcome

Phase 4 makes cleanup and recovery dependency-aware and preserves rerender lineage. Media cannot be deleted solely because a preview is old when a provider operation may still need it. Provider failure classes are explicit and bounded. Rerender requests no longer overwrite the only review record; they create a new lineage revision and invalidate prior approval.

```text
Preview/artifact → retention dependency evaluation → evidence
Provider operation → classified failure → bounded retry or reconciliation
Rerender request → new pending revision → caption validation → review
```

## Slice results

| Slice | Result |
|---|---|
| P4-A — Retention safety | `core/retention_safety.py` defines active versus terminal delivery dependencies and a media reachability contract. Cleanup uses status-aware review windows and delivery operation state, retains active dependencies, writes `retention_events`, deletes dependent rows in safe order, and reports retained/deleted counts. `/api/previews/:id/media-probe` checks HTTPS, video content type, content length, and byte-range behavior without provider mutation. |
| P4-B — Recovery and capacity | `core/recovery_policy.py` classifies provider failures, caps retries, produces deterministic jitter, checks channel capacity and request budget, and identifies stuck operations. Buffer requests are recorded in `provider_request_ledger`; preflight guards the conservative three-channel and ten-active-operation limits; retry requires transient/throttled class and fewer than three attempts; alerts expose stale attempting/unknown operations. |
| P4-C — Rerender lineage | Preview schema carries parent ID, revision number, render revision, and superseded timestamp. A `request_rerender` action creates a `pending_render` child, preserves the parent, clears approval provenance, and writes the parent review event. Existing job execution-generation and claim-token fences remain the stale-worker boundary. |

## Retention contract

Cleanup scans the policy window, evaluates every candidate preview against delivery operations, retains previews with `pending_review`, `changes_requested`, `pending_render`, or active provider dependencies, and records the reason. Only deletable previews have objects removed. Caption revisions, delivery operations, preview events, and previews are removed in dependency order; retention evidence remains available for audit. Jobs referenced by retained previews are not deleted.

The media probe is deliberately non-mutating. It sends a byte-range request to the public preview URL and records response status, content type, length, range support, URL, artifact hash, failures, and timestamp. It is a reachability contract, not proof of Buffer ingestion.

## Recovery contract

A transient or throttled provider failure may be retried only within a bounded attempt budget. Timeouts and ambiguous transport failures remain `unknown` to prevent duplicate provider posts. Reconciliation is required before replaying unknown outcomes. Provider deletion during reconciliation becomes a terminal local `failed` state. Stuck operations are visible through an authenticated alert endpoint rather than relying only on an open browser.

## Rerender contract

Rerender is lineage-preserving and approval-invalidating. The parent remains as historical evidence with `superseded_at`; the child has a new ID and render revision but no artifact or approval until a worker produces and validates it. This avoids pretending that an old artifact is a newly rendered artifact.

## Provider and deployment safety

No production Buffer post, D1 migration, Cloudflare deployment, provider smoke test, or Whop mutation was executed. The schema changes require a separately authorized deployment and smoke test. The Buffer GraphQL reconciliation query and media lifecycle still require a staging or mock-backed acceptance run before production use.

## Verification

```text
138 Python tests: OK
Python compilation and compileall: OK
pip check: OK
Node syntax checks for Cloudflare and Worker Pages: OK
git diff --check: OK
```

New fixtures cover active and terminal retention decisions, media reachability failures, retry classification and jitter determinism, capacity/request-budget exhaustion, stuck alerts, cleanup evidence, provider-deletion reconciliation, and rerender approval invalidation. Existing subtitle tests continue to emit two non-failing unclosed-file `ResourceWarning` messages.

## Explicit non-goals

Phase 4 does not provide a checked-in legal end-to-end fixture, staging failure matrix, production deployment, controlled pilot, provider ingestion proof, or Whop automation. These are Phase 5 work.

## Next phase

The next roadmap work is **Phase 5**, beginning with P5-A known-good fixture. It must start as a separate bounded task after this Phase 4 commit and documentation review.
