# Audit — Approval, Data Model, API, and Frontend Workflow

**Scope.** This is a read-only audit of preview approval, scheduling/Buffer UI, D1 persistence, per-video/per-channel state, and the frontend state machine. Reviewed: `core/captioning.py`, `modules/clipping/review_queue.py`, `worker/run_job.py`, `cloudflare/api.js`, `web/app.js`, `web/styles.css`, `cloudflare/schema.sql`, and `docs/BUFFER_INTEGRATION.md`. No production code was changed, no Buffer post was sent, and no external mutation was performed.

## Executive summary

The repository has the skeleton of a human-review workflow: the worker creates up to two review previews, D1 records a preview status and event log, the UI can approve/reject/request a rerender, and Buffer attempts are recorded. The central approval invariant is not enforced, however. The Buffer endpoint accepts `pending_review` previews, the UI displays the Buffer action for every preview with a download URL, and the Buffer action omits the configured review token. Consequently, a deployment with the recommended `REVIEW_TOKEN` cannot upload from the UI, while a deployment without that token can schedule an unapproved preview. This is a **blocker** for a safe approval workflow.

The state model is also incomplete for scheduling operations. `previews` is the only per-video decision record; `buffer_uploads` is an append-only attempt log, not a per-video/per-channel state model. It does not retain the final caption, service, schedule/due time, current state, or an idempotency key. The UI exposes only Buffer's automatic queue mode; there is no explicit schedule time, per-channel result, retry, or reconciliation state. A rerender request changes a status but does not enqueue work or associate a new preview revision. Cancellation is not honored by the worker's final write path and can be overwritten by a late preview upload.

## State model observed

| Area | Current behavior | Target behavior |
|---|---|---|
| Job | `queued`, `processing`, `review`, `blocked`, `error`, `cancelled`; worker PATCH can write arbitrary status. | Server-owned transition rules, generation/claim fencing, and cancellation checks before every terminal write. |
| Video preview | One `previews` row per `job_id`/rank, with `pending_review` and review outcomes. No revision identity. | Immutable preview revisions with explicit artifact/version and decision history; a rerender creates a new revision rather than replacing a reviewed artifact. |
| Approval | Review endpoint maps `approve` to `approved_for_manual_post`; but Buffer accepts `pending_review` too. | Only an approved, current revision may enter a scheduling request. Rejected/expired/superseded revisions are terminal. |
| Channel/schedule | Browser selects Buffer channel IDs; backend calls `schedulingType: automatic`, `mode: addToQueue`; no explicit time. | Server validates channels and stores a schedule intent and per-channel delivery state, including Buffer due time/post ID. |
| Per-channel result | Each request inserts a `buffer_uploads` row with `queued`, `error`, or `preflight_error`. No current-state projection or idempotency. | One durable operation per preview/channel/caption revision, with attempts, current state, exact submitted payload, provider response, and retry/reconciliation. |
| Frontend | A card-local action set is derived from status, but Buffer action is independent of status; review actions have no in-flight lock. | A state-machine-driven UI that hides/blocks invalid actions, shows loading and partial results, and reflects server state after every mutation. |

## Findings

### B-01 — Buffer scheduling bypasses approval (**blocker**)

**Current behavior.** The Buffer endpoint permits both `pending_review` and `approved_for_manual_post` (`cloudflare/api.js:230-233`). The frontend renders `Upload ke Buffer` whenever `r.download_url` exists, before it renders the status-dependent review actions (`web/app.js:297-312`). Therefore a preview that has never been approved can be sent to Buffer. The documentation describes the action as a review-gated upload (`docs/BUFFER_INTEGRATION.md:17-23`), but the implementation does not enforce that contract.

**Impact.** A human can accidentally or intentionally queue an unreviewed clip. This defeats the repository's non-negotiable human gate (`AGENTS.md:15`) and makes the status/event log an unreliable control boundary.

**Target behavior.** The scheduling mutation must accept only the current preview revision in `approved_for_manual_post`, and the server must reject all other statuses. The UI should render the scheduling action only for that status; a rejected, superseded, expired, or `changes_requested` preview should not expose a send action.

**Recommendation.** First change the API allow-list to the approved state and add a server-side test for every status. Then make the UI action predicate identical to the server predicate. Treat the approval as consumed by a specific caption/artifact revision; if the caption is edited after approval, require re-approval or create a new approval revision.

### B-02 — Configured review token is not sent with Buffer upload (**blocker**)

**Current behavior.** Review mutations add `x-review-token` when configured (`web/app.js:240-246`), but the Buffer POST sends only `content-type` (`web/app.js:270-272`). The API protects `/api/previews/:id/buffer` with `reviewAuthorized` (`cloudflare/api.js:227-229`), and `reviewAuthorized` requires the header when `REVIEW_TOKEN` exists (`cloudflare/api.js:146-150`). The documented deployment guidance recommends `REVIEW_TOKEN` (`docs/BUFFER_INTEGRATION.md:25-31`).

**Impact.** In the recommended secured deployment, every Buffer upload from the shipped UI returns `401 review_unauthorized`. This is a deterministic broken path, not an environment-dependent provider failure.

**Target behavior.** The same review authorization mechanism must be applied consistently to review and scheduling mutations. The UI should include the token through the established configuration mechanism, or preferably use a same-origin authenticated session rather than exposing a long-lived token to JavaScript. The API must still enforce authorization independently.

**Recommendation.** Fix the request header and add an end-to-end contract test with `REVIEW_TOKEN` set. Do not solve this by disabling the token check. Consider a short-lived server-issued action token/session for production.

### H-03 — Rerender is a status mutation, not a workflow (**high**)

**Current behavior.** `request_rerender` maps to `changes_requested` (`cloudflare/api.js:467-478`), and the UI calls only `/api/previews/:id/review` (`web/app.js:235-255`). There is no API route that creates a rerender job, dispatches the worker, or attaches the reason to a new candidate. The worker's normal path creates previews once and posts them as `pending_review` (`worker/run_job.py:411-448`).

**Impact.** A reviewer can request a rerender, but nothing in the reviewed files will process that request. The preview can remain in `changes_requested` indefinitely. The apparent state transition gives a false sense of completion.

**Target behavior.** A rerender request should create a durable work item containing the reason, source preview/revision, and requested changes; dispatch or enqueue a worker; and produce a new immutable preview revision linked to the old one. The old revision should remain auditable and non-sendable.

**Recommendation.** Phase 1: add an explicit `rerender_requests`/job action endpoint and visible `queued/processing/failed` state. Phase 2: add revision lineage and worker fencing. Phase 3: allow approval only on the newly rendered revision.

### H-04 — Cancellation can be overwritten by late worker completion (**high**)

**Current behavior.** The cancel endpoint changes an active job to `cancelled` (`cloudflare/api.js:493-499`). The worker does not poll cancellation while processing and, after rendering/uploading, POSTs previews and unconditionally updates the job to `review` (`worker/run_job.py:443-448`; `cloudflare/api.js:501-508`). The generic worker PATCH also updates status without checking the current state (`cloudflare/api.js:546-550`).

**Impact.** A user-visible cancellation is not authoritative. A runner already in flight can resurrect a cancelled job, publish review artifacts after cancellation, or overwrite a newer terminal state. This also creates orphaned R2 objects because cleanup keys are not necessarily registered before the late write.

**Target behavior.** Cancellation must be a fenced terminal transition. Worker writes must include the claimed run/generation and conditional `WHERE status IN (...)`; preview creation must reject cancelled jobs. The worker should check cancellation before expensive stages and before every final mutation.

**Recommendation.** Add a job generation/claim token to all worker writes, make terminal transitions conditional, and return a conflict when a late runner loses the fence. Add tests for cancel-before-upload, cancel-during-render, and stale runner completion.

### H-05 — No per-video/per-channel scheduling state or idempotency (**high**)

**Current behavior.** The schema has a preview row (`cloudflare/schema.sql:56-74`) and an append-only `buffer_uploads` table (`cloudflare/schema.sql:100-110`). The Buffer handler inserts one row per attempted channel (`cloudflare/api.js:233-258`), but there is no unique key for `(preview, channel, caption/artifact revision)`, no `updated_at`, no final text, no channel service, no requested schedule, no provider status, and no retry/reconciliation fields. The API always invokes Buffer with `schedulingType: automatic` and `mode: addToQueue` (`cloudflare/api.js:247-252`).

**Impact.** A second click, browser retry, or page reload can create duplicate Buffer posts. The system cannot answer the current state of a video on a particular channel, distinguish a failed attempt from a later successful attempt, or prove what caption was actually submitted. There is no explicit schedule timestamp to reconcile against Buffer.

**Target behavior.** Introduce a schedule operation keyed by preview revision and channel, with a unique idempotency key. Store `requested_at`, `requested_by`, exact final caption/text hash, channel service, schedule mode/time, provider post ID, provider due time, current state, last error, attempt count, and timestamps. Expose a current per-channel projection plus attempt history.

**Recommendation.** Add a migration before enabling retries. Make the mutation idempotent: return the existing operation for the same key, and never blindly issue a second provider mutation. Persist the provider response before returning success where possible; add reconciliation for timeout/unknown outcomes.

### H-06 — Approval is not bound to the caption that is scheduled (**high**)

**Current behavior.** The review record stores only `caption_draft` (`cloudflare/schema.sql:64-72`). The UI lets the operator edit caption text in the Buffer modal (`web/app.js:262-272`), and the backend sends the edited text but does not persist it in `buffer_uploads` (`cloudflare/api.js:235-255`; `cloudflare/schema.sql:100-110`). Approval itself records only status/reason/actor/time (`cloudflare/api.js:482-486`).

**Impact.** The approved content and the submitted content can differ without a new approval event. After the fact, the system cannot reconstruct the exact text, hashtags, or caption revision sent per channel.

**Target behavior.** Approval must cover an immutable artifact and exact caption revision, or caption editing must transition the preview back to `changes_requested`/`pending_review`. Each provider operation must retain the exact submitted text and a content hash.

**Recommendation.** Make caption editing a saved revision with an explicit “save and re-approve” path. Reject a Buffer request whose caption hash differs from the approved hash unless the user performs a fresh approval.

### H-07 — Preview ingestion can overwrite a reviewed decision (**high**)

**Current behavior.** Worker preview ingestion uses `INSERT OR REPLACE` with a deterministic ID (`cloudflare/api.js:501-506`; IDs are built as `job_id-rank` in `worker/run_job.py:437`). `REPLACE` is destructive in SQLite semantics: a retried ingestion can replace a row and reset `status` to `pending_review`, while review metadata is omitted from the insert. There is no preview revision or compare-and-swap guard.

**Impact.** A retry or duplicate worker run can erase an approval/rejection and replace its artifact. Existing `preview_events` are not version-bound, so the audit trail can become detached from the currently displayed file.

**Target behavior.** Preview records should be immutable by revision, or ingestion should use a guarded upsert that refuses to overwrite a reviewed row. Artifact keys and content hashes should be versioned.

**Recommendation.** Replace `INSERT OR REPLACE` with an explicit insert-once/immutable-revision strategy. If compatibility requires upsert, include a run ID and reject updates when the current row is no longer `pending_review`.

### H-08 — Review event transition is race-prone (**high**)

**Current behavior.** The API reads the current status, then batches an unconditional event insert with an `UPDATE ... WHERE status IN (...)` (`cloudflare/api.js:475-485`). It does not inspect the update row count. Two concurrent requests can both read the same status, one can win the update while both events are recorded, and the response can report success for a request that did not perform the transition.

**Impact.** The final status and event history can disagree; duplicate approvals or conflicting reject/approve decisions are possible under double-clicks, multiple tabs, or retries.

**Target behavior.** Use an atomic compare-and-swap transition and write the event only when the update changes exactly one row, ideally in a transaction with an operation/idempotency key. Return `409` for a lost race.

**Recommendation.** Add transition tests with concurrent approve/reject requests. Add an operation ID to the client mutation and make it replay-safe.

### M-09 — The UI does not model per-channel results or partial failure (**medium**)

**Current behavior.** The backend returns one result per channel, including `queued`, `preflight_error`, or `error` (`cloudflare/api.js:237-258`). The frontend counts only queued results, closes the modal, and shows “N channel berhasil” (`web/app.js:272-275`). It does not render failed channels, provider IDs, due times, or a retry action. A HTTP-200 response with zero queued channels is treated as a completed interaction.

**Impact.** Reviewers cannot tell which channels were scheduled or why one failed, and they may retry the whole set, increasing duplicate risk.

**Target behavior.** Keep the modal/card open for partial failure and show a per-channel state table with safe retry of only failed/unknown operations. Refresh the server projection after mutation.

**Recommendation.** Return and display an operation summary. Make `0 queued` an error state. Add explicit `queued`, `preflight_error`, `provider_error`, and `unknown` UI states.

### M-10 — “Scheduling UI” is queue-only, not scheduling-time aware (**medium**)

**Current behavior.** The modal says the video will use the channel's schedule and offers only channel checkboxes and caption editing (`web/app.js:260-272`). The request hard-codes Buffer automatic queue mode (`cloudflare/api.js:247-248`); the returned `dueAt` is not stored or displayed (`cloudflare/api.js:248-252`; `cloudflare/schema.sql:100-110`).

**Impact.** The operator cannot choose or verify a time, timezone, or per-channel schedule. The system cannot show whether Buffer accepted the intended schedule, only that a create call returned a post.

**Target behavior.** Either clearly name this as “Add to Buffer queue” and expose the provider due time, or implement an explicit schedule mode with validated timestamp/timezone and persisted intent. Do not imply that a selected time exists when it does not.

**Recommendation.** Phase 1: rename copy to queue mode and display provider `dueAt`. Phase 2: add schedule mode, timezone handling, validation, and persisted schedule intent only if the Buffer API contract supports it.

### M-11 — Channel identity and service used for preflight are client supplied (**medium**)

**Current behavior.** The browser sends selected IDs plus `{id, service}` objects (`web/app.js:265-272`). The backend finds the service in `body.channels` and applies the length limit before calling Buffer (`cloudflare/api.js:239-243`). It does not verify that the IDs belong to the authenticated Buffer account or that the supplied service matches the provider channel.

**Impact.** A stale or manipulated browser payload can apply the wrong text limit. Channel authorization/ownership is delegated to the provider mutation, while the local audit record accepts arbitrary channel IDs.

**Target behavior.** Resolve channel metadata server-side from the Buffer account and validate every requested channel before any mutation. Persist the authoritative service/name and reject unknown channels before creating local attempts.

**Recommendation.** Do not trust `body.channels` for policy. Cache or query an authorized channel directory server-side, then use that metadata for limits and audit fields.

### M-12 — Review and preview data endpoints are broadly exposed unless deployment configuration is perfect (**medium**) 

**Current behavior.** CORS permits all origins (`cloudflare/api.js:1-5`). Campaigns, jobs, and preview listing routes have no review or worker authorization (`cloudflare/api.js:293-317`, `440-458`). `reviewAuthorized` returns `true` when `REVIEW_TOKEN` is absent (`cloudflare/api.js:146-150`). The direct `/media/...` route is unauthenticated and publicly cacheable (`cloudflare/api.js:205-213`), while signed `/api/files` URLs are optional (`cloudflare/api.js:192-198`, `517-545`).

**Impact.** Without a token/session and restrictive origin policy, anyone who can reach the Pages URL can enumerate workflow data, view preview metadata, and invoke review/Buffer mutations. Public media may be intentional for Buffer, but the distinction between public delivery media and reviewer-only artifacts is not enforced in this code.

**Target behavior.** Separate public provider media from private review artifacts, require authenticated reviewer identity for mutations and sensitive reads, and restrict origins. If public media is necessary, expose only immutable, non-sensitive artifact keys and document that decision.

**Recommendation.** Make `REVIEW_TOKEN`/session mandatory in production, protect sensitive GET routes, restrict CORS to the deployed UI origin, and add authorization tests. Keep a separate explicitly public media origin/path for provider fetches.

### M-13 — Frontend action state has no in-flight lock or authoritative refresh (**medium**)

**Current behavior.** Review buttons are bound directly after every render (`web/app.js:317-326`), with no disabled/in-flight state. The Buffer button disables only after confirmation and only inside the modal (`web/app.js:265-275`). Review success mutates the local object then calls `loadJobs`, which clears and reloads all reviews (`web/app.js:247-252`, `214-224`).

**Impact.** Rapid clicks or multiple tabs can issue duplicate/conflicting review mutations. Users see optimistic success before a fresh server projection and may act on stale cards.

**Target behavior.** Represent each mutation as `idle → submitting → succeeded/failed`, disable all relevant actions while submitting, and refresh the affected preview plus event/channel operation state after completion.

**Recommendation.** Add a stable preview-ID action controller rather than relying only on card index, use server responses as the source of truth, and preserve/display errors without silently replacing the review list.

### L-14 — Rules summary is stored as text despite an identifier name (**low**)

**Current behavior.** `caption_metadata` builds a concatenated human-readable rules string and calls it `rules_summary_id` (`modules/clipping/review_queue.py:38-63`). It is persisted as such in the preview row (`cloudflare/schema.sql:66-72`) and displayed by the UI (`web/app.js:307-308`).

**Impact.** The name suggests a stable rules/version identifier, but it cannot be used to prove which plan/rules snapshot produced the approval. Text can change without a comparable hash.

**Target behavior.** Store a stable `rules_hash`/plan snapshot reference separately from the display summary.

**Recommendation.** Rename the display field and add a real immutable rules/plan hash to the job, preview revision, approval, and schedule operation.

## Additional assumptions and gaps

1. **Buffer provider semantics.** The repository documentation explicitly says `automatic`/`addToQueue` uses the channel's Buffer queue (`docs/BUFFER_INTEGRATION.md:17-23`). This audit did not call Buffer, so provider-side deduplication, due-time guarantees, and channel-level permissions remain unverified.
2. **Public media is partly intentional.** The documentation requires a direct public stable HTTPS URL for Buffer (`docs/BUFFER_INTEGRATION.md:15`), so the unauthenticated `/media` path may be a deliberate provider integration tradeoff. It should nevertheless be isolated from reviewer-only assets and covered by a threat model.
3. **No explicit platform-specific caption/sound state is modeled.** Caption generation is deterministic (`modules/clipping/review_queue.py:38-63`) and the Buffer request sends one text/one video asset to each channel (`cloudflare/api.js:247-248`). Native sound, tagging, or platform-specific variants are not represented in the approval state. This is outside the direct scheduling mutation but matters to what “approved” means.
4. **`core/captioning.py` is artifact generation only.** It creates SRT/ASS cues (`core/captioning.py:41-71`, `82-118`) and contains no approval or persistence state; no defect in this file alone establishes that a captioned artifact was approved.
5. **No repository evidence shows a background reconciler for Buffer.** The only provider-side operation in the reviewed files is the synchronous `createPost` call and local insert (`cloudflare/api.js:247-258`).

## Phased recommendations

### Phase 0 — Restore the safety boundary before deployment

1. Require `approved_for_manual_post` in the Buffer endpoint; hide/disable the Buffer action for every other status.
2. Send and verify review authorization on Buffer mutations; add a secured-path integration test.
3. Add a server-side caption/artifact approval hash check and persist the exact submitted caption.
4. Make review transitions atomic compare-and-swap operations and return `409` on a lost race.
5. Prevent cancelled/stale jobs from inserting previews or changing a terminal job to `review`.

### Phase 1 — Make operations auditable and retry-safe

1. Replace destructive preview upsert with immutable preview revisions or guarded insert-once behavior.
2. Add a per-preview/per-channel schedule operation with unique idempotency key, authoritative channel metadata, exact payload, provider post ID/due time, attempt count, current state, and errors.
3. Display per-channel results, partial failures, provider due times, and retry-only-failed controls.
4. Make `REVIEW_TOKEN`/reviewer authentication mandatory for production sensitive reads and writes; restrict CORS.

### Phase 2 — Complete the workflow state machine

1. Implement rerender as a real queued worker action with reason, lineage, progress, and a new preview revision.
2. Add job generation/claim fencing and cancellation checkpoints at every worker terminal write.
3. Decide whether the product supports queue-only scheduling or explicit scheduling. If queue-only, rename UI copy and surface Buffer's resulting due time; if explicit, add timezone-aware schedule intent and validation.
4. Add event/state contract tests covering every preview status, concurrent decisions, duplicate schedule requests, provider timeout, partial channel failure, cancellation races, and rerender lineage.

## Verification cases to add

| Case | Expected result |
|---|---|
| Buffer request for `pending_review` | `409`; no provider call; no upload operation marked queued. |
| Buffer request with configured review token but missing header | `401`; UI includes the header in the valid path. |
| Approve and reject concurrently | Exactly one state transition/event; loser receives `409`. |
| Same preview/channel/caption request retried | Same operation returned; no second Buffer post. |
| Caption edited after approval | Re-approval required, or request rejected by hash mismatch. |
| One of three channels fails | Two successes and one visible failure; retry targets only the failed operation. |
| Cancel while worker is rendering | No late preview insertion or `review` resurrection. |
| Request rerender | Durable queued work appears and a new revision is eventually linked to the old preview. |
| Worker retries preview ingestion | Existing reviewed revision is not replaced or reset. |

## Conclusion

The current implementation is suitable as a prototype review display and Buffer queue experiment, but it is not yet a dependable approval-and-scheduling subsystem. The two immediate blockers are the approval bypass and the missing review token on the Buffer request. After those are fixed, the highest-value work is to introduce immutable preview/caption revisions, an idempotent per-channel operation model, cancellation/run fencing, and a real rerender workflow. Until then, “approved” is not a reliable prerequisite for scheduling and the database cannot provide a complete per-video/per-channel audit trail.

## Source index

- [`cloudflare/api.js`](../cloudflare/api.js) — API routes, authorization, review transitions, preview ingestion, Buffer mutation, media delivery.
- [`cloudflare/schema.sql`](../cloudflare/schema.sql) — campaigns, jobs, previews, preview events, and Buffer upload tables.
- [`worker/run_job.py`](../worker/run_job.py) — validation, review queue creation, artifact upload, preview/job final writes.
- [`modules/clipping/review_queue.py`](../modules/clipping/review_queue.py) — review artifact payload, caption draft, checklist, and validation status.
- [`web/app.js`](../web/app.js) — frontend job/review state, approval actions, Buffer modal, polling.
- [`docs/BUFFER_INTEGRATION.md`](../docs/BUFFER_INTEGRATION.md) — intended Buffer integration contract and deployment settings.
- [`AGENTS.md`](../AGENTS.md) — repository safety rule that auto-publish remains disabled and humans approve final previews.
