# Audit Subsystem 03 — Buffer Scheduling and Free-tier Feasibility

**Scope.** Read-only audit of the Buffer GraphQL integration, multi-channel posting, scheduling, platform limits, statuses, idempotency, and Free-plan capacity. No Buffer post was created and no external mutation was performed. Findings are grounded in the repository files supplied for review and cross-checked against Buffer's current public documentation.

## Executive summary

The implementation is a useful pilot path for a human-initiated Buffer queue action: it keeps the API key server-side, enumerates organizations/channels, performs a local caption-length preflight, calls Buffer's GraphQL `createPost` once per selected channel with `schedulingType: automatic` and `mode: addToQueue`, and records an attempt in D1. Buffer's documented semantics confirm that `addToQueue` selects the next available slot in the channel's posting schedule, so the current action is queueing rather than immediate publishing [Buffer Posts & Scheduling](https://developers.buffer.com/guides/posts-and-scheduling.html).

It is **not production-safe as a reliable scheduler or multi-channel delivery system**. The approval gate is bypassable because the Buffer route accepts `pending_review`; the backend trusts client-supplied channel metadata; there is no idempotency key or uniqueness constraint; there is no Buffer post reconciliation after creation; and a null/shape-incomplete GraphQL result can be recorded as successfully queued. A single multi-channel request can therefore create duplicates, produce partial success without an actionable retry model, or report local `queued` while the actual Buffer status is unknown. The Free plan is feasible for a small pilot—up to **3 channels and 10 scheduled posts per channel at a time**, with **3,000 API requests/month** according to the current [Buffer pricing page](https://buffer.com/pricing)—but the repository has no guard for those account limits and can attempt up to 10 channels per action.

## Findings

### B-01 — Buffer action bypasses the human approval gate (**blocker**)

**Current behavior.** `POST /api/previews/:id/buffer` allows both `pending_review` and `approved_for_manual_post` (`cloudflare/api.js:230-233`). The review transition itself maps `approve` to `approved_for_manual_post` (`cloudflare/api.js:467-486`), but the upload action does not require that state. The frontend renders an “Upload ke Buffer” button whenever a preview has a download URL, independently of review status (`web/app.js:297-312`), while the separate approval button is labeled “ACC upload manual.”

**Impact.** A reviewer can queue an unreviewed preview. This contradicts the stated workflow in `docs/BUFFER_INTEGRATION.md:19-23` and the repository's human-gated posting policy. It is a release-blocking control failure even though the action is user-confirmed in the browser.

**Target behavior.** Require exactly `approved_for_manual_post` server-side, and make the UI show the Buffer action only after that state. Treat the server transition, not button visibility or confirmation, as the control boundary.

### B-02 — No idempotency; repeated clicks/retries can create duplicate Buffer posts (**high**)

**Current behavior.** Every selected channel executes `createPost` with no idempotency token or client request ID (`cloudflare/api.js:237-258`). Each local record uses a fresh `crypto.randomUUID()` and `buffer_uploads` has no uniqueness constraint (`cloudflare/api.js:117-118`; `cloudflare/schema.sql:100-110`). The frontend disables the button only after the request starts (`web/app.js:265-275`), so browser retries, timeouts after Buffer accepted a post, double tabs, or an operator retry can create another post.

**Target behavior.** Add a durable per-preview/per-channel delivery key and unique constraint, e.g. `(preview_id, channel_id, caption/content revision)`; create an `attempting` record transactionally before the external call; on retry reconcile by the key or require explicit operator confirmation. Do not use a random local row ID as the idempotency key.

### B-03 — Local status is not Buffer status; no reconciliation exists (**high**)

**Current behavior.** A successful mutation is stored as local `status='queued'` with only `buffer_post_id` and `created_at` (`cloudflare/api.js:248-258`; `cloudflare/schema.sql:100-110`). The code returns `id`, `dueAt`, and `channelId` from GraphQL but does not persist `dueAt`; there is no query of Buffer `posts`, no status sync, and no route/UI for scheduled/sent/error state. Buffer documents a lifecycle of scheduled, sent, and error, and supports querying posts by channel/status [Buffer Posts & Scheduling](https://developers.buffer.com/guides/posts-and-scheduling.html).

**Target behavior.** Persist `due_at`, Buffer status, last error, observed timestamp, and response metadata. Add a controlled reconciliation job/endpoint that queries posts by organization/channel and maps Buffer `scheduled`, `sent`, and `error` into local states such as `scheduled`, `published`, `failed`, and `unknown`. Keep `queued` as a transient submission state only.

### B-04 — GraphQL success validation is incomplete (**high**)

**Current behavior.** The code throws only when `result.message && !result.post` (`cloudflare/api.js:247-251`). If `createPost` is null, has no `post`, or returns a success object without a non-empty ID, it still inserts `status='queued'` with a null post ID. GraphQL transport errors are handled by `bufferRequest` (`cloudflare/api.js:152-161`), but union-shape validation is not complete.

**Target behavior.** Accept success only when the union is `PostActionSuccess` and `post.id` is non-empty. Persist the raw/sanitized response and classify `MutationError`, malformed success, HTTP error, and timeout separately. A submission whose outcome is unknown must be `unknown`, never `queued`.

### B-05 — Multi-channel delivery is sequential and has no transactional outcome model (**high**)

**Current behavior.** The route loops through selected channel IDs and calls Buffer one at a time (`cloudflare/api.js:237-257`). It can create posts for the first channels and fail later channels. The response is HTTP 200 with `ok` based on whether any item is queued (`cloudflare/api.js:258`), and the frontend closes the modal and reports only the count of queued channels (`web/app.js:272-275`). Per-channel errors are not shown or made available for targeted retry.

**Target behavior.** Return an explicit batch outcome (`all_succeeded`, `partial`, `none`, `unknown`) with durable per-channel states. Keep successful IDs, display failed channels and reasons, and retry only failed/unknown deliveries after idempotency/reconciliation. Consider rate limiting and bounded concurrency only after the state model is safe.

### B-06 — Backend trusts client-supplied service metadata for platform limits (**high**)

**Current behavior.** The client sends `{id, service}` for selected channels (`web/app.js:266-272`). The backend finds the service from `body.channels`, not from a server-side Buffer channel lookup (`cloudflare/api.js:238-242`). A missing or falsified service falls through to the default 2,200-character limit (`cloudflare/api.js:164-173`). Channel IDs are also accepted without checking that they belong to the organizations returned by the authenticated Buffer account.

**Target behavior.** Resolve and cache channel ID → organization/name/service on the server, validate the selected IDs against that authoritative list, and derive limits from the server-side service and post type. Never use browser-provided service metadata for authorization or policy decisions.

### B-07 — Platform coverage and limits are assumptions, not a verified capability matrix (**high / assumption**)

**Current behavior.** `bufferTextLimit` contains X/Twitter, Threads, Bluesky, Pinterest, Instagram, TikTok, LinkedIn, Facebook, and YouTube limits (`cloudflare/api.js:164-173`). The implementation sends one generic video asset and one generic caption to every channel (`cloudflare/api.js:248`). It has no platform metadata for Instagram post type, Pinterest board, YouTube-specific fields, first comments, threads, disclosure, or official audio. Buffer's current API guide lists Instagram, Threads, LinkedIn, X, Facebook, Google Business Profiles, Mastodon, YouTube, Pinterest, and Bluesky as supported platforms; TikTok is not listed on that guide [Buffer Posts & Scheduling](https://developers.buffer.com/guides/posts-and-scheduling.html).

**Impact.** TikTok support and the numeric limits are not established by the repository's API contract. A conservative character limit is not a substitute for validating asset/post-type rules. The same caption/video payload may be valid for one channel and invalid or semantically wrong for another.

**Target behavior.** Maintain a versioned, tested capability matrix from Buffer's schema and account/channel data. Validate media, text, and required metadata per platform; either split payloads by channel or reject unsupported combinations before any mutation. Mark the listed TikTok path as unverified until Buffer confirms it for this API/account.

### B-08 — Scheduling is queue-based only; exact scheduling is not exposed (**medium**)

**Current behavior.** Every mutation hard-codes `schedulingType: automatic` and `mode: addToQueue` (`cloudflare/api.js:248`). The frontend describes this accurately as using the channel queue schedule (`web/app.js:256-262`), and Buffer documents that `addToQueue` selects the next available slot. There is no `customScheduled`/`dueAt` input, timezone field, or preview of the selected due time.

**Target behavior.** If the product requirement is queueing, expose the returned `dueAt` and clearly label the action “add to next channel queue slot.” If exact scheduling is required, add an explicit UTC `dueAt` flow using Buffer's documented `customScheduled` mode and validate timezone, past times, and account/channel schedule constraints.

### B-09 — Free-plan capacity is feasible only for a small pilot and is not enforced (**medium**)

**Current behavior.** The code accepts up to 10 distinct channel IDs (`cloudflare/api.js:233`), while the current Buffer Free plan allows up to 3 connected channels and 10 scheduled posts per channel at a time; scheduled slots refill after publication. The same pricing page lists 3,000 API requests/month and one API key. The repository has no account-plan discovery, scheduled-count guard, request-budget ledger, or user-facing capacity warning. `cloudflare/FREE_COST_POLICY.md:55-68` guards Cloudflare resources, not Buffer capacity.

**Feasibility calculation.** The Free plan provides at most 30 simultaneously scheduled posts across three channels. One clip sent to three channels consumes three channel slots and normally costs three `createPost` calls, plus channel/organization reads. At 10 clips/day × 3 channels, the 30-slot window fills quickly if publication schedules are sparse; it is not a monthly “10 posts” allowance because published slots refill. The 3,000-request monthly budget is ample for a low-volume pilot but can be consumed by retries, reconciliation, and repeated channel enumeration.

**Target behavior.** Treat the Free plan as an explicit account-level constraint: discover/record connected channel count, maintain a local scheduled-slot estimate, reserve slots before submitting, stop before mutation when capacity is uncertain, and show “N of 10 scheduled slots used” per channel. Do not promise Free-tier feasibility for more than three channels or 30 simultaneously queued posts.

### B-10 — Approved media retention can race with Buffer delivery (**medium / assumption**)

**Current behavior.** The documented policy says approved/final objects are retained only briefly (`cloudflare/FREE_COST_POLICY.md:42-53`), while cleanup deletes preview objects and rows older than 24 hours without consulting `buffer_uploads` (`cloudflare/api.js:260-275`). The Buffer post row records an ID but no asset-delivery or post status. The integration documentation correctly requires a public, stable media URL (`docs/BUFFER_INTEGRATION.md:15`), but the repository does not prove whether Buffer has durably ingested the asset before cleanup or whether a queued post can still fetch it later.

**Target behavior.** Define and test the Buffer asset lifecycle. Retain the source object until Buffer confirms ingestion/scheduled state, or use a Buffer-hosted upload path if documented and appropriate. Exclude active Buffer deliveries from cleanup and retain their external status/asset dependency until sent or terminal error.

### B-11 — Channel enumeration is unauthenticated at the application layer (**medium**)

**Current behavior.** `GET /api/buffer/channels` has no `reviewAuthorized` check (`cloudflare/api.js:218-225`), while `reviewAuthorized` permits all callers when `REVIEW_TOKEN` is unset (`cloudflare/api.js:146-149`). The API key remains server-side, but organization and channel names are exposed to any caller able to reach the endpoint.

**Target behavior.** Require the same authenticated reviewer/session boundary for channel enumeration and posting, preferably with Cloudflare Access/application auth. Do not treat keeping the API key secret as sufficient authorization.

## Gaps and assumptions

1. No Buffer account, channel set, queue schedule, plan state, or live API response was accessed; this audit intentionally made no Buffer mutation.
2. The repository does not specify the desired product semantics for “schedule”: next queue slot versus exact UTC time. Current code implements only the former.
3. Numeric platform limits in `bufferTextLimit` are repository assumptions. They need validation against Buffer's current schema and each network's post type; Buffer's public scheduling guide establishes the scheduling modes and lifecycle, not all of those numeric limits.
4. The current public Buffer guide's supported-platform list does not include TikTok. Whether a TikTok channel is available through this account/API version remains unverified.
5. It is unknown whether Buffer fully copies the video at `createPost` time. The retention recommendation therefore requires an integration test that observes asset availability through the scheduled lifecycle.
6. The supplied `captioning.py` has no Buffer-specific behavior; its caption cue generation is unrelated to outbound post scheduling (`core/captioning.py:41-71,82-118`).

## Phased recommendations

### Phase 0 — Do not enable production posting until controls are fixed

Make the server require `approved_for_manual_post`; authenticate channel enumeration; validate channel IDs and services server-side; reject malformed GraphQL success; and add an explicit “no mutation” dry-run/preflight endpoint for review. Keep the existing browser confirmation, but treat it as UX only. These changes address B-01, B-04, B-06, and B-11.

### Phase 1 — Make one deliberate submission reliable

Add a durable per-preview/per-channel idempotency key and unique index, persist `dueAt`, submission timestamps, response classification, and error details, and model `attempting`, `unknown`, `scheduled`, `published`, and `failed`. Return and display per-channel outcomes rather than closing on HTTP 200 partial failure. Add a server-side capability matrix and reject unsupported platform/media combinations. This addresses B-02, B-03, B-05, and B-07.

### Phase 2 — Make scheduling observable and Free-plan aware

Decide whether queue scheduling is sufficient. If yes, display Buffer's returned `dueAt`; if no, implement a validated `customScheduled` flow. Add a bounded reconciliation process using Buffer's documented post query, with request-budget accounting, backoff, and no duplicate creation on unknown outcomes. Track connected channels and scheduled slots per channel; enforce the Free-plan three-channel/10-scheduled-post-per-channel ceiling before mutation. This addresses B-08 and B-09.

### Phase 3 — Validate lifecycle and retention under a pilot account

Using a dedicated test account and only after the above controls exist, test one approved clip on one supported channel, then a multi-channel partial-failure case, queue publication, Buffer error state, and cleanup timing. Verify public media ingestion before deleting R2 objects. Keep the pilot within three channels and a deliberately low queue depth; upgrade only when measured queue capacity or API request volume requires it. This validates B-10 and the platform assumptions without relying on undocumented behavior.

## Overall disposition

**Current disposition: BLOCKED for production Buffer posting; CONDITIONALLY FEASIBLE for a low-volume, manually approved pilot after Phase 0 controls.** The GraphQL endpoint and basic queue mutation match Buffer's documented API shape, but local persistence currently proves only that an attempt was made—not that a unique, approved, correctly targeted post was scheduled or later published.
