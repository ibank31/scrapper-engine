# End-to-End Workflow Implementation Roadmap

**Target workflow:** campaign → immutable rules → exactly two materially distinct finished clips (Tier 1 and Tier 2) → preview → human approval → two timezone-aware schedules → each clip to Instagram, TikTok, and YouTube → stop.

**Explicitly out of scope:** Whop links, submission, payout, and downstream campaign reporting.

**Operating constraint:** This roadmap is an implementation plan only. The audit did not modify production code and did not send external requests.

## Delivery strategy

Implement the workflow as a sequence of enforceable contracts rather than as a larger best-effort pipeline. Every stage must persist the evidence needed by the next stage. A later stage must not infer success from a count, browser state, or provider HTTP response. The order below is intentional: provenance and state fencing come before output selection; output invariants and caption compliance come before approval; approval and idempotency come before provider mutation; reconciliation and retention come before declaring completion.

Use feature flags for each phase. Keep publication disabled until the Phase 0 and Phase 1 acceptance gates pass in staging. When a provider cannot represent or verify native sound, native tags, caption files, or exact scheduling, record `manual_required` or `unsupported`; never map a checklist to `verified`.

## Phase 0 — Lock provenance, approval, and safety boundaries

**Objective:** prevent a job from executing changed rules, prevent unapproved or malformed Buffer mutations, and prevent stale workers from corrupting terminal state.

### 0.1 Add immutable job execution data

Extend `jobs` with `plan_snapshot_json`, `rules_hash`, `plan_schema_version`, `source_fingerprint_json`, `execution_generation`, `cancelled_at`, and a terminal-write fence such as `active_run_token`. At job creation (`cloudflare/api.js:319-330`), read the active campaign once, normalize the plan, compute a canonical SHA-256 rules hash, and insert the snapshot in the same transaction as the job. Do not rely on the campaign-level `rules_hash` alone (`cloudflare/schema.sql:1-20`).

Update the worker to use `job.plan_snapshot_json` and `job.rules_hash` rather than reading a mutable campaign plan at execution time (`worker/run_job.py:151-180`). Persist the canonicalized plan and hash in the manifest. Reject a job with a missing or invalid snapshot instead of silently regenerating it.

Add a migration-safe backfill policy. Existing queued jobs without snapshots should be marked `blocked_needs_requeue`, not executed against current campaign data. Existing completed jobs remain readable with `legacy_provenance = true`.

### 0.2 Include every rule source in AI input and fingerprints

Add `docs_text`, normalized documents, source URLs, and document content hashes to `rules_fingerprint` (`core/campaign_ai.py:120-128`). Ensure the AI prompt payload includes the same canonical source set used by deterministic compilation (`worker/sync_campaigns.py:47-72`; `core/campaign_rules.py:80-86`). Persist evidence quotes and source paths with every normalized rule.

Create a canonical rule contract with explicit `required`, `suggested`, `prohibited`, `platform`, and `source` fields. Carry through at least `subtitle_required`, `subtitle_style`, official audio, handles, hashtags, disclosures, CTA text/URL, posting rules, account rules, duration, aspect ratio, tier allocation, and schedule policy (`core/campaign_rules.py:200-229`).

### 0.3 Enforce approval server-side

Change the Buffer endpoint to accept only `approved_for_manual_post` (`cloudflare/api.js:227-233`). Require review authorization for the mutation regardless of whether `REVIEW_TOKEN` is configured, or replace the optional token with the project’s authenticated access boundary. Update the browser to send the required authorization header (`web/app.js:265-275`). Hide or disable the Buffer action until approval is authoritative (`web/app.js:297-312`), but treat the server gate as the control.

Bind approval to `artifact_hash`, `caption_revision_id`, `rules_hash`, `platform_profile_version`, and `schedule_intent_hash`. Approval of an older revision must not authorize a newer payload. Make the review update and event insert conditional on the expected current status and verify the affected-row count (`cloudflare/api.js:475-485`).

### 0.4 Fence cancellation and stale writes

Require every worker PATCH, preview ingestion, manifest update, and stage event to include `job_id`, `run_id`, `execution_generation`, and claim token (`worker/run_job.py:43-70`; `cloudflare/api.js:415-447,501-550`). Update only when the job is still owned by that generation and is not terminal. Cancellation must atomically increment the generation and mark the job cancelled (`cloudflare/api.js:493-499`). Late workers receive a conflict and cannot insert previews or force review state.

### Phase 0 acceptance gate

Phase 0 passes only if the following tests succeed:

- A campaign edited after job creation cannot change the worker’s rules or output manifest.
- A document-only rule changes the canonical rules hash and appears in AI input and review evidence.
- A `pending_review` Buffer request returns 409 and creates no provider operation.
- The browser mutation includes review authorization and the server rejects missing authorization.
- Approval of caption revision A cannot authorize revision B.
- A cancelled job rejects a stale worker preview ingestion and status update.
- Duplicate review clicks produce one state transition and one event.

## Phase 1 — Make two finished clips a hard contract

**Objective:** guarantee exactly two materially distinct outputs with one Tier 1 and one Tier 2 before review.

### 1.1 Define the campaign output contract

Add required plan fields:

```json
{
  "output_contract": {
    "expected_count": 2,
    "tier_allocation": {"tier_1": 1, "tier_2": 1},
    "min_duration_seconds": 0,
    "max_duration_seconds": 0,
    "distinctness_profile": "default-v1"
  }
}
```

The business owner must define Tier 1 and Tier 2 semantics. The implementation must not infer tiers from the existing campaign metadata flag. A tier definition should specify the clip class, evidence required, and whether the label is mandatory or suggested.

### 1.2 Add deterministic candidate tiers and identity

Give each candidate a stable `candidate_id`, normalized `source_asset_id`, source hash, transcript hash, start/end times, tier label, selection rationale, and rules hash. Add a deterministic tier classifier with a versioned profile. If a candidate cannot be classified, it is not eligible for a required tier.

Normalize source identity before source truncation. Apply exact and perceptual source hashes before the `max_sources` limit (`worker/run_job.py:231-255`). Retain excluded-source evidence so operators can distinguish “not selected” from “duplicate.”

### 1.3 Enforce count and tier coverage before rendering

Replace the current maximum-only behavior (`worker/run_job.py:30-31,366-367`) with a contract gate:

- exactly two selected candidates;
- exactly one Tier 1 and one Tier 2;
- each candidate has a stable identity and source evidence;
- both satisfy duration and campaign policy;
- failure produces `blocked_insufficient_output_contract`, not a partial review queue.

Persist expected and actual counts in stage metrics and the job manifest.

### 1.4 Enforce rendering and validation counts

The render stage must fail if either selected candidate does not produce exactly one expected artifact (`worker/run_job.py:373-390`). Do not silently continue with one output. Validation must include all artifacts and fail the campaign-level gate if any required artifact fails (`worker/run_job.py:394-410`).

Run a final-artifact pairwise distinctness check after rendering. The versioned profile should combine normalized transcript similarity, temporal overlap, audio/media fingerprints, and source identity. Thresholds must be calibrated against labeled examples; do not reuse the current heuristic without documenting the business threshold.

Persist pairwise evidence: metric values, thresholds, profile version, and pass/fail result.

### 1.5 Persist output contract in data and UI

Add `expected_count`, `actual_count`, `tier`, `candidate_id`, `distinctness_json`, and `artifact_hash` to previews or a related candidate/output table. Add a job-level output contract summary. The review UI must show `1/2 Tier 1`, `1/2 Tier 2`, pairwise distinctness status, and a blocking explanation instead of generic “Kandidat N” labels (`web/app.js:226-233,289-326`).

### Phase 1 acceptance gate

Test at minimum: one candidate, two same-source overlapping candidates, two cross-source duplicate files, missing render for one candidate, one validation failure, missing Tier 1, missing Tier 2, and a valid pair. Only the valid pair reaches `review` and contains exactly two preview rows.

## Phase 2 — Establish caption, hashtag, disclosure, subtitle, and sound contracts

**Objective:** ensure the exact text and media metadata approved by a reviewer satisfy the structured plan for each target platform.

### 2.1 Create a platform rule contract

Normalize rules into platform profiles for Instagram, TikTok, and YouTube. Each profile should specify caption length calculation, required handles, native-tag capability, hashtag policy, required disclosures, CTA policy, prohibited terms, required phrases, subtitle delivery, audio policy, and supported schedule fields.

Distinguish **required** from **suggested** tags. Preserve hashtag provenance (`explicit`, `AI-evidence`, `deterministic-inferred`, or `reviewer-added`) and platform applicability. Do not silently reuse an inferred hashtag across platforms.

### 2.2 Introduce immutable caption revisions

Replace the free-floating `caption_draft` with a caption revision model. Store `preview_id`, `platform`, exact final text, structured handles, hashtags, disclosures, CTA, payload JSON, character-count method, revision number, editor, created time, and `caption_hash`. Keep the original draft and every edit for auditability.

The UI can remain editable, but the server must validate the final text on save and again immediately before provider mutation. Deleting a mandatory handle, disclosure, CTA, phrase, or required hashtag must be rejected with a field-level error (`web/app.js:256-276`; `cloudflare/api.js:233-245`).

### 2.3 Implement final server-side compliance

Create one deterministic validator used by review save, approval, and Buffer preflight. It must check:

- required phrases and mandatory normalized requirements;
- prohibited terms/content markers;
- required handles as text and native-tag status separately;
- required hashtags and provenance;
- disclosure text and placement policy;
- CTA text or URL;
- platform-specific length using the provider’s documented counting method;
- caption hash and rules hash consistency.

A failed check must not create a provider operation. Return structured failures and persist the preflight result.

### 2.4 Add subtitle profiles and delivery modes

Carry `subtitle_style` from AI/rules into a versioned renderer profile (`core/campaign_ai.py:68-70`; `core/campaign_rules.py:200-222`; `modules/clipping/render.py:41-74`). Support explicit modes: `burned_in`, `native_caption_file`, `none`, and `manual_required`. Do not force subtitles globally from the worker (`worker/run_job.py:375-382`).

For each platform profile, define safe areas, typography, cue limits, language, and whether a sidecar or provider caption field is supported. Emit a platform artifact or a recorded shared-artifact decision. Persist subtitle profile and artifact hash.

### 2.5 Model official sound and native tags honestly

Add an audio contract containing platform, policy (`original_audio`, `official_native_track`, `mixed_asset`, or `manual_required`), approved source/asset ID, provider track ID where known, allowed mix level, and evidence. Add native tag records containing platform, handle, provider tag ID if available, status, and evidence.

The current checklist (`modules/clipping/review_queue.py:91-94`) remains useful for manual handoff but must produce `manual_required`, not `verified`. A provider adapter may set `verified` only after the provider accepts and returns the relevant field. If Buffer cannot represent the field, route the operation to a clearly labeled manual-native step and do not claim all-six automated delivery.

### Phase 2 acceptance gate

Fixtures must cover deletion of a required handle, disclosure, CTA, hashtag, required phrase, and prohibited term; platform-specific length limits; document-only rules; subtitle style variants; official sound required; native tag unsupported; and a valid caption revision. The same validator must produce the same result in UI save, approval, and provider preflight.

## Phase 3 — Implement explicit timezone-aware schedules and per-channel operations

**Objective:** represent six independent delivery operations and make scheduling semantics unambiguous.

### 3.1 Choose and document scheduling semantics

The current mutation uses Buffer’s automatic queue (`cloudflare/api.js:247-248`; `docs/BUFFER_INTEGRATION.md:17-23`). Choose one product contract:

- **Exact scheduling:** UI accepts local date/time and IANA timezone, converts to UTC, persists the intent, and calls a provider capability that supports an exact due time.
- **Queue scheduling:** UI explicitly says “next Buffer queue slot,” persists the requested queue mode, and uses provider-returned `dueAt` as evidence. It must not be marketed as exact timezone-aware scheduling.

For the target requirement, implement exact scheduling only if the connected provider/channel capability is verified. Otherwise retain queue mode with `manual_required` or `not_supported` for exact timing.

### 3.2 Add a durable operation table

Replace append-only `buffer_uploads` (`cloudflare/schema.sql:100-110`) with or supplement it using a table keyed by `preview_id`, `platform/channel_id`, and an operation UUID. Store:

- `video_id`, `preview_id`, `channel_id`, authoritative service;
- `platform_profile_version`;
- exact caption and payload hashes;
- idempotency key;
- local schedule time, IANA timezone, UTC time, mode;
- provider post ID and returned `dueAt`;
- state: `planned`, `preflight_failed`, `attempting`, `scheduled`, `unknown`, `published`, `failed`, `manual_required`, `cancelled`;
- attempt count, last attempt, retryability, error class, error detail;
- reconciliation timestamps and evidence;
- created/updated times.

Add a unique constraint on preview/channel/caption/artifact/schedule revision, or on a durable operation key whose reuse is intentional. Store the exact provider request payload with secrets removed.

### 3.3 Validate channels server-side

`GET /api/buffer/channels` currently returns authoritative-looking channel data, but the mutation trusts client-supplied service metadata (`cloudflare/api.js:218-225,233-242`; `web/app.js:266-272`). Resolve channel IDs server-side from a cached capability snapshot. Reject unknown, disconnected, or unsupported channels. Validate that the three required services are present and that the account can schedule video posts.

Use a versioned capability matrix for Instagram, TikTok, and YouTube. Explicitly test whether each supports video URL ingestion, caption length, native audio, native tags, caption files, exact scheduling, and returned lifecycle status.

### 3.4 Implement idempotent mutation and unknown-result handling

Before mutation, create the six planned operations and run a no-request preflight. For each operation, reuse the same idempotency key and exact payload on retry. A timeout or malformed response becomes `unknown`; do not blindly retry. Reconcile using provider post ID, provider operation metadata, or an operator-required decision.

Validate GraphQL success strictly: require a post object with ID, channel ID, and acceptable schedule evidence. A response without a post ID is not `queued` (`cloudflare/api.js:248-252`). Process operations independently and return six outcomes, not a single `ok` boolean. The aggregate succeeds only when all six meet their required terminal state.

### 3.5 Show per-channel state and schedule evidence

The frontend must display two videos × three channels, exact local/UTC intent, provider `dueAt`, status, last error, retryability, and manual-native requirements. A partial success must remain actionable and must not be summarized as “N channels succeeded” only (`web/app.js:272-275`). Add explicit retry and reconcile actions that target one operation.

### Phase 3 acceptance gate

Use a staging Buffer account or mocked contract server to test: exact time conversion across DST, queue-mode semantics, missing channel, unsupported platform, duplicate click, timeout/unknown result, malformed GraphQL success, partial failure, retry after one failed channel, and all-six success. Verify no duplicate provider post is created for a repeated idempotency key.

## Phase 4 — Retention, reconciliation, capacity, and operational recovery

**Objective:** make the workflow safe to run repeatedly and safe to recover after provider or worker faults.

### 4.1 Retain media for active provider dependencies

The cleanup route currently deletes old preview objects without consulting Buffer rows (`cloudflare/api.js:260-275`). Change retention to retain media while any operation is `planned`, `attempting`, `unknown`, `scheduled`, or otherwise provider-dependent. Add a minimum retention window after the last provider confirmation. Record deletion evidence and never delete an object referenced by an unresolved operation.

Add a staging media contract test that fetches every public URL, verifies stable HTTPS, content type, byte ranges, and sufficient accessibility for provider ingestion. The repository documentation correctly warns that expiring signed URLs must not be sent to Buffer (`docs/BUFFER_INTEGRATION.md:15`).

### 4.2 Reconcile provider lifecycle

Persist and periodically reconcile provider post state. Map provider states to local states with a versioned mapping. Back off transient errors, alert on permanent errors, and surface provider deletion or permission changes. Reconciliation must be idempotent and must not overwrite a newer local manual decision.

### 4.3 Add capacity and request budgeting

Before six mutations, query or maintain channel capacity. Under the supplied Free-tier assumption, three channels and six scheduled posts are within the stated per-channel count but leave no spare channel; the connected account and current terms must be verified [5]. Track request budget and reserve capacity for reconciliation. If capacity is insufficient, block before the first mutation and show the required operator action.

### 4.4 Add retries, alerts, and durable telemetry

Define retry classes for API, R2, GraphQL, provider throttling, media reachability, and validation failures. Add bounded exponential backoff with jitter. Do not swallow critical telemetry failures (`worker/run_job.py:47-58`). Add durable alerts for stuck `attempting`, `unknown`, `scheduled` without provider confirmation, and media nearing retention expiry.

### 4.5 Add rerender lineage and cancellation recovery

Turn `request_rerender` into a queued action with a parent preview, new revision, new artifact hash, and invalidation of prior approval (`cloudflare/api.js:467-486`). Keep the old revision for audit. A rerender must re-enter caption validation and approval; it cannot reuse the old Buffer authorization.

### Phase 4 acceptance gate

Simulate provider downtime, R2 failure, worker crash after mutation, stale worker after cancellation, cleanup while a post is queued, provider post deletion, throttling, and reconciliation after an unknown result. Verify the system reaches an explicit state with no duplicate, no hidden orphan, and no premature terminal success.

## Phase 5 — Production pilot and controlled enablement

**Objective:** prove the complete contract in a low-volume account before enabling production mutation.

1. Configure a dedicated pilot Buffer workspace with only the required Instagram, TikTok, and YouTube channels. Verify account permissions, supported post types, capacity, and current Free-tier terms against official documentation [2]–[5].
2. Run the complete happy path with a campaign containing document-only rules, one Tier 1 and one Tier 2 requirement, required disclosure, CTA, handles, hashtags, and official-audio policy.
3. Confirm exactly two finished artifacts, distinctness evidence, platform caption revisions, approval hashes, six idempotent operations, provider IDs, provider `dueAt` values, and terminal states.
4. Run the failure matrix from every phase. No run may publish or queue after a failed approval, failed caption gate, failed pair invariant, unsupported capability, or unresolved unknown result.
5. Keep production Buffer mutation behind a feature flag until the pilot passes twice, including one retry/reconciliation scenario. Document the provider capability matrix and manual-native handoff procedure.
6. Enable only the target campaign path. Do not add Whop or submission behavior under this roadmap.

## Cross-phase data model summary

| Entity | Required additions |
|---|---|
| `campaigns` | Canonical source hashes, normalized plan version, capability/profile references |
| `jobs` | Plan snapshot, rules hash, source fingerprint, output contract, execution generation, run fence, cancellation fence |
| `candidates` | Stable ID, tier, source identity/hash, rationale, selection profile |
| `previews` | Candidate ID, tier, artifact hash, distinctness evidence, revision IDs, output contract version |
| `caption_revisions` | Platform, exact text, structured components, hash, validator result, editor, revision lineage |
| `audio_bindings` | Platform, policy, source/track ID, mix policy, status, evidence |
| `native_tags` | Platform, handle, provider ID, status, evidence |
| `schedule_intents` | Local time, IANA timezone, UTC instant, mode, schedule hash, approval binding |
| `delivery_operations` | Preview/channel identity, payload hash, idempotency key, provider ID/dueAt, state, attempts, errors, reconciliation |
| `job_stage_events` | Generation/fence, contract versions, expected/actual metrics, distinctness evidence |

## Required regression and contract tests

The test suite should include these named fixtures and assertions:

- `document_only_rule_changes_plan_and_rules_hash`;
- `job_uses_snapshot_after_campaign_edit`;
- `requires_exactly_two_outputs`;
- `requires_one_tier_1_and_one_tier_2`;
- `blocks_missing_render`;
- `blocks_validation_failure_in_one_required_clip`;
- `blocks_cross_source_duplicate_final_artifacts`;
- `caption_delete_required_disclosure_is_rejected`;
- `caption_delete_required_handle_is_rejected`;
- `caption_prohibited_term_is_rejected`;
- `caption_platform_limit_uses_authoritative_service`;
- `subtitle_style_selects_profile`;
- `official_audio_without_track_id_is_manual_required`;
- `native_handle_without_provider_support_is_manual_required`;
- `pending_review_cannot_mutate_buffer`;
- `approval_binds_caption_and_artifact_hashes`;
- `schedule_converts_iana_time_through_dst`;
- `queue_mode_is_not_reported_as_exact_time`;
- `unknown_provider_result_is_not_retried_blindly`;
- `idempotency_prevents_duplicate_post`;
- `partial_channel_failure_is_retriable_per_operation`;
- `cleanup_retains_media_for_active_operation`;
- `stale_worker_cannot_write_after_cancel`;
- `rerender_invalidates_prior_approval`;
- `completion_requires_six_terminal_channel_operations`.

Each test should assert the HTTP response, persisted rows, state transitions, audit evidence, and operator-visible result. Contract tests should use a mock provider where no live account is authorized; the pilot phase is the only place to validate real provider behavior, and it must remain controlled.

## Definition of done

The implementation is done when a staging run can prove all of the following in one durable manifest and operation report:

- one immutable rules snapshot and hash;
- exactly two artifacts, one Tier 1 and one Tier 2;
- two successful render and validation records;
- pairwise distinctness evidence;
- platform-specific caption revisions and compliance results;
- explicit sound/native-tag status for every platform;
- two schedule intents with timezone and UTC evidence for each video;
- six unique delivery operations with provider IDs or explicit manual/unsupported outcomes;
- no unresolved unknown state;
- no active provider dependency eligible for cleanup;
- terminal aggregate state `completed` only after the six operations meet the configured success policy;
- no Whop or submission step.

If any required platform capability is unsupported, the workflow is complete only as a **manual-required** handoff, not as an automated all-channel success. The UI, manifest, and audit report must say which field remains manual.

## Assumptions to validate before production

- The connected Buffer workspace exposes all three target services and allows video scheduling for each.
- Current Free-tier limits and request quotas match the supplied audit; official plan terms and account state must be checked [5].
- Buffer accepts the chosen media URL and the provider’s returned `dueAt` means what the product assumes [3] [4].
- Native audio, tagging, caption files, and exact scheduling are supported by an adapter or will remain manual.
- Tier definitions and material-distinctness thresholds are approved by the campaign owner.

## References

[1]: https://github.com/ibank31/scrapper-engine/blob/main/docs/AGENT_HANDOFF.md "Scrapper Engine agent handoff and production evidence"
[2]: https://developers.buffer.com/guides/authentication.html "Buffer API Authentication"
[3]: https://developers.buffer.com/guides/posts-and-scheduling.html "Buffer API Posts and Scheduling"
[4]: https://developers.buffer.com/guides/hosting-media.html "Buffer API Hosting Media"
[5]: https://buffer.com/pricing "Buffer pricing and plan limits"

> The roadmap does not assert undocumented provider capabilities. No external request was sent while creating it.

**Roadmap path:** `/home/ubuntu/scrapper-engine/docs/IMPLEMENTATION_ROADMAP.md`

**Related audit:** `/home/ubuntu/scrapper-engine/docs/END_TO_END_WORKFLOW_AUDIT.md`

**Final enablement rule:** do not enable production Buffer mutation until Phase 0, Phase 1, and the relevant Phase 2–4 gates pass.

**Stop boundary:** after the two videos have reached the configured terminal outcomes for Instagram, TikTok, and YouTube.

**Whop links/submission:** excluded.

---

**End of roadmap.**
