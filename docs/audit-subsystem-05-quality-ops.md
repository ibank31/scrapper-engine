# Audit Subsystem 05 — End-to-End Quality Gates and Operational Risks

**Scope.** This audit covers the path from asset intake and rendered-clip validation through human review and the Buffer queue mutation. It focuses on tests, validations, media reachability, timezones, retries, monitoring, and acceptance criteria. No production code was modified and no Buffer post or other external mutation was sent.

## Executive conclusion

The repository has useful deterministic unit coverage and several good safety mechanisms: source preflight, technical media validation, human review states, stage-event telemetry, atomic job claiming, and conservative Buffer caption-length checks. The local suite passed **87 tests** with `CLIPPER_SEMANTIC_ENABLED=false`; this is evidence for isolated Python behavior only.

The end-to-end path is **not ready for production Buffer scheduling acceptance**. The main blockers are the absence of a non-mutating integration test that proves a scheduled Buffer asset can fetch the public media URL, the absence of idempotency and reconciliation for the per-channel Buffer mutation, and an approval boundary that accepts `pending_review` as well as an approved state. A 24-hour cleanup job can also delete the media object while a queued Buffer post may still depend on it. These are operational correctness risks rather than merely missing UI polish.

## Severity scale

* **Blocker:** production acceptance cannot be granted without resolving it or explicitly accepting a documented exception.
* **High:** likely to cause an incorrect schedule, duplicate schedule, lost artifact, or unbounded recovery failure.
* **Medium:** materially weakens detection, diagnosis, or consistency but has a practical manual workaround.
* **Low:** limited impact or maintainability issue.
* **Assumption:** behavior or provider semantics are not proven by repository evidence and require an integration check or product decision.

## Findings

### QO-01 — Blocker — No end-to-end acceptance gate proves the Buffer media contract

**Current behavior.** The CI workflow runs Python unit tests, a semantic fixture, and JavaScript syntax checks only (`.github/workflows/tests.yml:22-36`). The suite contains no Cloudflare/D1 API integration test, no R2-to-public-URL test, and no Buffer GraphQL contract test. The Buffer endpoint constructs a URL and sends it directly to Buffer (`cloudflare/api.js:176-181`, `247-248`), but does not probe the object, verify `200`/range behavior, or verify the returned asset is the intended preview. The `/media` route is public and returns the R2 object (`cloudflare/api.js:205-213`), but reachability is assumed rather than tested.

**Target behavior.** A pre-release acceptance test should use a fake Buffer endpoint and a test object store or deployed staging object. It should prove that the exact URL sent in `assets[].video.url` is HTTPS, public without reviewer credentials, returns the expected video content type, supports the fetch pattern needed by the provider, and remains available through the scheduled-post retention window. The test must not create a real Buffer post.

**Recommendation.** Make this a Phase 0 release gate. Add a contract test for the GraphQL payload, a media URL probe in staging, and a negative test for missing/expired/unreachable media. Record the tested artifact key, content hash, URL, and probe result in the job evidence.

### QO-02 — High — Buffer scheduling is not idempotent or safely retryable

**Current behavior.** One request loops over selected channels and calls `createPost` once per channel (`cloudflare/api.js:233-258`). There is no operation ID from the browser, no unique per-preview/per-channel key, no provider idempotency key, and no durable `attempting` or `unknown` state. `buffer_uploads` stores only a generated row ID, preview/channel IDs, provider post ID, status, error, and timestamp (`cloudflare/schema.sql:100-110`). A browser retry, proxy retry, or client timeout after Buffer accepted the post can create a duplicate. The UI closes the modal after an HTTP-success response and reports only the count of queued channels (`web/app.js:265-275`), even when individual channels failed.

**Target behavior.** Every preview/channel submission needs a stable operation identity, a state machine such as `pending → attempting → scheduled|unknown|failed`, the exact request payload, provider ID, provider `dueAt`, and bounded retry/reconciliation rules. An unknown result must never be blindly recreated.

**Recommendation.** Phase 0: add a unique operation key and make repeated submissions return the existing result. Phase 1: persist per-channel attempts and display scheduled, failed, and unknown outcomes separately. Retry only known-safe failures; reconcile unknown results through the provider API before creating another post.

### QO-03 — High — The Buffer endpoint bypasses the completed-review gate

**Current behavior.** The mutation permits both `pending_review` and `approved_for_manual_post` (`cloudflare/api.js:230-232`). The UI renders an Upload button for any preview with a download URL, independently of status (`web/app.js:303-312`). Browser confirmation is useful, but it is not an approval-state control. The repository’s review transition supports explicit approval (`cloudflare/api.js:467-486`), yet the scheduling endpoint can be reached before it.

**Target behavior.** Buffer scheduling must require the approved terminal state, with the approval bound to the exact preview artifact and final caption. Pending, rejected, changed, cancelled, or superseded previews must be rejected server-side.

**Recommendation.** Phase 0 blocker fix: accept only `approved_for_manual_post` and hide/disable scheduling for other states. Add an integration test for every invalid state and a race test where approval and scheduling happen concurrently.

### QO-04 — High — Edited captions are checked only for presence and length, not campaign compliance

**Current behavior.** The review queue deterministically drafts handles, links, mandatory-rule summaries, and hashtags (`modules/clipping/review_queue.py:38-63`), and the UI allows the reviewer to replace the caption (`web/app.js:260-272`). The Buffer endpoint checks only non-empty text and a service-dependent length limit (`cloudflare/api.js:235-245`). It does not re-check mandatory phrases, required handles, CTA URLs, prohibited terms, disclosures, or whether the edited text still matches the approved caption/rules snapshot. The exact final text is not stored in `buffer_uploads` (`cloudflare/schema.sql:100-110`).

**Target behavior.** Server-side preflight must evaluate the submitted final text against the campaign plan and selected channel capabilities. Approval must be invalidated when the text changes, or the changed text must be re-approved. Each attempt must preserve the exact submitted text and compliance result.

**Recommendation.** Phase 0: add a caption hash to approval and compare it at scheduling. Phase 1: persist final text, structured checks, rules hash, and channel service for every attempt. Add tests for removed handles, altered CTA, prohibited terms, Unicode length, and partial channel selection.

### QO-05 — High — Cleanup can remove media still needed by Buffer

**Current behavior.** The scheduled cleanup selects all previews older than 24 hours and deletes their video, review video, and thumbnail objects (`cloudflare/api.js:260-274`). It does not join against `buffer_uploads`, does not distinguish queued/scheduled posts from terminal outcomes, and does not retain provider `dueAt` or lifecycle state. The documented integration requires a direct stable public media URL (`docs/BUFFER_INTEGRATION.md:15-23`), but the retention policy does not establish that Buffer has ingested or copied the object before deletion.

**Target behavior.** Media must remain available until each provider delivery reaches a confirmed terminal state, or the integration must use a provider-hosted upload path with a documented ownership guarantee. Cleanup must be dependency-aware and auditable.

**Recommendation.** Phase 0: disable deletion of any preview with a non-terminal Buffer upload. Phase 1: add `scheduled`, `published`, `failed`, `unknown`, and expiry fields, then make cleanup retain active dependencies and report skipped deletions. Add a staging lifecycle test that verifies availability after queueing and after the retention cutoff.

### QO-06 — High — Transient failures have inconsistent retry and recovery semantics

**Current behavior.** The worker’s generic API request performs one request with a fixed 60-second timeout and no retry/backoff (`worker/run_job.py:34-40`). R2 upload also performs one 180-second request (`worker/run_job.py:95-102`). A failure updates the job to `error` and re-raises (`worker/run_job.py:449-452`). The workflow has a 55-minute hard timeout but no automatic retry strategy (`.github/workflows/clipper-worker.yml:18-28`). Direct media download has three attempts (`modules/reward_campaign/intake.py:93-98`), while the shared byte fetch defaults to one attempt (`core/fetch.py:40-58`); the caller overrides it to three, so this behavior is not uniform across callers.

**Target behavior.** Classify failures as transient, permanent, or unknown. Use bounded exponential backoff with jitter for safe reads and uploads, an operation-level retry budget, and idempotent recovery for mutations. A runner timeout must leave a recoverable state rather than requiring a manual guess.

**Recommendation.** Phase 1: add retry wrappers for API/R2 operations with request IDs and bounded budgets. Keep Buffer mutation retries behind idempotency/reconciliation; do not replay an unknown `createPost`. Add fault-injection tests for timeout, 429, 5xx, connection reset, and response lost after provider acceptance.

### QO-07 — High — Terminal job states are not protected against stale workers

**Current behavior.** Cancellation changes a queued or processing job to `cancelled` (`cloudflare/api.js:493-499`), but the worker’s generic PATCH updates status without a compare-and-swap or terminal-state guard (`cloudflare/api.js:546-550`). A stale worker can therefore write progress or `review` after cancellation. The preview-upload endpoint inserts/replaces previews and unconditionally sets the job to `review` (`cloudflare/api.js:501-508`). Stale recovery only protects the claim lease and runner death evidence (`cloudflare/api.js:386-413`); it does not fence an old run ID from later writes.

**Target behavior.** Every write must be fenced by job ID, run ID/claim token, and allowed state transition. A cancelled, superseded, or terminal job cannot accept previews or become review-ready.

**Recommendation.** Phase 0: add conditional updates requiring the active claim token/run ID and reject writes to terminal states. Phase 1: add a transition table and concurrent cancellation/stale-worker integration tests.

### QO-08 — Medium — Validation can produce an empty “review” job without a valid preview

**Current behavior.** Validation is executed with `check=False` and its JSON is loaded afterward (`worker/run_job.py:394-400`). The all-fail guard runs only when `results` is non-empty (`worker/run_job.py:408-410`). If validation emits no results, `review_queue` skips rendered files without a matching validation result (`modules/clipping/review_queue.py:103-120`), while the API later marks the job `review` with the number of submitted previews, including zero (`cloudflare/api.js:501-508`).

**Target behavior.** Missing, malformed, or empty validation output is a hard job failure. A review-ready job must contain at least one preview with a valid validation record and an accessible artifact.

**Recommendation.** Phase 0: validate the validation schema and require `results` to cover every rendered clip. Block on empty coverage. Add tests for validator exit failure, malformed JSON, missing path, and zero-result output.

### QO-09 — Medium — Quality gates distinguish technical failure from manual review, but acceptance is not enforced at scheduling

**Current behavior.** The validator checks dimensions, codecs, audio, frame rate, duration, relevance, and editorial warnings (`modules/clipping/validate.py:41-103`). Mid-thought starts, incomplete sentences, watermark, native sound, handle, and CTA issues become `needs_review` rather than a blocking failure (`modules/clipping/validate.py:72-93`). This is appropriate for human review, but the Buffer endpoint does not require that the reviewer completed those checklist items; it only checks preview status and caption length (`cloudflare/api.js:230-245`). The review checklist is persisted as JSON but there is no completion state (`cloudflare/schema.sql:65-71`).

**Target behavior.** Separate machine-pass, human-required, and human-completed criteria. Scheduling must reject unresolved blocking checklist items such as official audio, native handles, watermark, or CTA when the campaign marks them mandatory.

**Recommendation.** Phase 1: model checklist item IDs, requiredness, completion, and evidence. Bind the approval to a completed checklist snapshot. Preserve a manual-native-post state when Buffer cannot perform a required native platform action.

### QO-10 — Medium — Monitoring records events but does not reliably alert or surface telemetry loss

**Current behavior.** The worker writes stage events with UTC timestamps and bounded error details, but deliberately swallows telemetry request failures (`worker/run_job.py:47-58`). The API stores stage events (`cloudflare/api.js:415-426`), and the UI polls jobs every five seconds and marks stale jobs using fixed client-side thresholds (`web/app.js:169-173`, `279-287`). Preview-load failures are silently ignored (`web/app.js:226-234`), and there is no health endpoint, alert sink, stage-duration alert, retry-budget alert, or notification for a stuck/unknown Buffer operation. The “connected · polling 5s” label is static UI copy (`web/app.js:340`).

**Target behavior.** Monitoring must distinguish “no event,” “telemetry delivery failed,” “worker failed,” and “provider outcome unknown.” Operators need server-side alerts for stale claims, repeated failures, queue age, missing preview coverage, media probe failures, and Buffer partial/unknown outcomes.

**Recommendation.** Phase 1: add durable operation correlation IDs and metrics for each stage and Buffer channel. Alert from server-side data, not only an open browser. Make telemetry loss visible in the job record and retain a bounded event history.

### QO-11 — Medium — Timezone and scheduling semantics are underspecified and not displayed

**Current behavior.** Internal timestamps are UTC ISO strings (`cloudflare/api.js:10`; `worker/run_job.py:47-54`). The cleanup workflow comments that `30 17 * * *` is 00:30 Jakarta (`.github/workflows/preview-cleanup.yml:3-6`), which is deterministic for Jakarta but not encoded as a timezone setting. Buffer scheduling hard-codes queue mode (`cloudflare/api.js:247-248`); the UI says it uses the channel schedule (`web/app.js:260-262`), but does not display the provider’s returned `dueAt`. The schema has no scheduled-intent timezone or due-time field (`cloudflare/schema.sql:100-110`).

**Target behavior.** Explicitly call the action “Add to Buffer queue” unless exact scheduling is implemented. Persist provider `dueAt` and the channel timezone when available. If exact scheduling is required, accept an IANA timezone and validated timestamp, then show both the requested instant and provider-resolved instant.

**Recommendation.** Phase 0: document that the current contract is next queue slot, not exact time, and display returned `dueAt`. Phase 1: add timezone-aware scheduling only after confirming the provider API semantics and adding boundary tests around UTC day changes and daylight-saving zones.

### QO-12 — Low — Input and artifact schemas are permissive at the review boundary

**Current behavior.** `review_queue` treats every validation status other than `fail` as `pending_review` (`modules/clipping/review_queue.py:113-120`) and catches thumbnail generation errors while still emitting a review item (`modules/clipping/review_queue.py:122-140`). Caption cue generation coerces missing or malformed word times to zero/default values (`core/captioning.py:23-37`, `41-58`) without a schema or monotonicity check.

**Target behavior.** Validate artifact and validation schemas before review. Reject unknown statuses and invalid timestamp intervals, or mark them explicitly as `artifact_invalid` rather than presenting them as reviewable.

**Recommendation.** Phase 2: add JSON schemas and property-based tests for malformed timestamps, empty cues, overlapping cues, missing thumbnails, and unknown validation statuses. Keep a human-review fallback only when the artifact is demonstrably playable and the exception is visible.

## Test and acceptance coverage summary

The current deterministic suite covers campaign rules, source/intake helpers, candidate selection, rendering helpers, semantic ranking, review-queue formatting, worker claiming, and diagnostic text. It does not cover the production boundary that matters most here: Cloudflare route behavior, D1 transitions, R2 object reachability, Buffer channel authorization, Buffer partial results, Buffer retries, cleanup versus queued posts, timezone display, or cancellation races. JavaScript syntax checks are not behavioral tests (`.github/workflows/tests.yml:22-36`).

The minimum acceptance set before enabling production scheduling should be:

1. **Artifact gate:** every submitted preview has a playable object, expected dimensions/codecs/audio, complete validation coverage, and a tested public media URL.
2. **Approval gate:** only an approved preview revision with an unchanged caption/rules/artifact hash can schedule.
3. **Channel gate:** channel IDs and services are resolved server-side and validated against the authenticated Buffer account.
4. **Mutation gate:** per-channel idempotency, explicit attempt state, provider response capture, and safe unknown-result reconciliation are present.
5. **Retention gate:** cleanup cannot delete media referenced by an active Buffer operation.
6. **Operational gate:** stale claims, missing stage events, partial Buffer failures, and unreachable media produce durable alerts and operator-visible states.
7. **Timezone gate:** queue-versus-exact-time semantics are explicit, and provider `dueAt` is persisted and displayed.

## Phased implementation plan

### Phase 0 — Block unsafe scheduling

Require `approved_for_manual_post`; add final-caption and artifact hashes; reject empty or schema-invalid validation; resolve Buffer channel metadata server-side; run a staging media reachability probe; fence writes by active run/claim; and suspend cleanup for previews with non-terminal Buffer operations. Add non-mutating integration tests for these controls.

### Phase 1 — Make scheduling durable and diagnosable

Introduce a per-preview/per-channel operation table with a unique idempotency key, exact payload, service, caption, rules hash, artifact key/hash, attempt count, provider post ID, `dueAt`, state, and error classification. Add safe retries and reconciliation, partial-result UI, server-side alerts, and retention-aware cleanup. Expand CI to run API/D1/R2 contract tests using provider mocks.

### Phase 2 — Complete the operational contract

Add explicit checklist completion and evidence, provider lifecycle reconciliation, timezone-aware exact scheduling if required, JSON schemas and malformed-input/property tests, and a staging soak test covering queueing, media retention, provider acceptance, cleanup, and terminal delivery outcomes. Define measurable SLOs for queue age, job completion, preview availability, and unknown Buffer outcomes.

## Assumptions and evidence gaps

1. This audit did not call Buffer, GitHub Actions, Cloudflare, or any external API. Provider deduplication, media-ingestion timing, account permissions, queue capacity, and exact `dueAt` semantics remain unverified.
2. The public `/media` route appears intentional because Buffer requires a stable public HTTPS asset URL (`docs/BUFFER_INTEGRATION.md:15`), but the repository does not separate provider-delivery media from reviewer-only media or provide a threat-model/retention contract.
3. The current UI and documentation describe Buffer queue insertion, not immediate publication (`docs/BUFFER_INTEGRATION.md:17-23`). The product decision whether “schedule” means next queue slot or an exact time is not encoded in the data model.
4. The passing 87-test result is a local deterministic baseline; it does not establish that the deployed Cloudflare bindings, GitHub token configuration, R2 route, or Buffer secret are correctly configured.

## References

[1]: https://developers.buffer.com/guides/posts-and-scheduling.html "Buffer Posts and Scheduling documentation"
[2]: https://developers.buffer.com/guides/hosting-media.html "Buffer Hosting Media documentation"
[3]: https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#workflow_dispatch "GitHub workflow_dispatch documentation"

Repository evidence is cited inline using file paths and line ranges so findings remain reviewable against the checked-out source.
