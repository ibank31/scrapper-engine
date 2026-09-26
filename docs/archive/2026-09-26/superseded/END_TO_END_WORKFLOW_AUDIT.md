# End-to-End Workflow Audit

**Scope:** campaign → rules → two materially distinct finished clips (Tier 1/Tier 2) → preview → human approval → two timezone-aware Buffer schedules → each video to Instagram, TikTok, and YouTube → stop. Whop links and submission are out of scope.

**Method and boundary:** This is a read-only synthesis of the supplied subsystem audits and repository files. No production code was modified, and no external request or Buffer mutation was sent.

## Executive verdict

The repository contains a useful production skeleton: campaign sync, deterministic rule compilation, AI rule analysis, source preflight, transcript-based candidate selection, 9:16 rendering, technical validation, R2 preview upload, review events, and a Buffer GraphQL mutation. A documented happy path produced two rendered clips, two validation results, two uploaded previews, and two `pending_review` records [1]. That is evidence of a successful example, not an invariant.

The target workflow is **not acceptance-ready**. The largest risks are contract-boundary failures:

- A queued job stores `campaign_id`, not an immutable plan snapshot or job-level `rules_hash`; the worker can therefore execute a changed campaign plan (`cloudflare/schema.sql:23-39`; `cloudflare/api.js:319-330`; `worker/run_job.py:151-180`).
- `docs_text` is used by deterministic compilation but is omitted from the AI prompt/fingerprint path, so document-only rules can be absent or stale (`core/campaign_rules.py:80-86`; `core/campaign_ai.py:120-128`; `worker/sync_campaigns.py:47-72`).
- The worker selects **up to** two candidates, allows missing renders, and has no Tier 1/Tier 2 allocation or final pairwise distinctness gate (`worker/run_job.py:366-410`; `core/clip_candidates.py:227-258`).
- A reviewer can delete required caption material. The Buffer endpoint checks only non-empty text and a length estimate, not handles, hashtags, CTA, disclosures, required phrases, or prohibited terms (`web/app.js:256-276`; `cloudflare/api.js:230-245`).
- Official/native sound and native handles are manual checklist items. No track ID, asset mapping, platform mapping, native tag field, or verification artifact is persisted (`core/campaign_rules.py:108,200-220`; `modules/clipping/review_queue.py:91-94`; `cloudflare/api.js:247-248`).
- One global 9:16 master with burned-in subtitles is produced. `subtitle_style` is not carried into rendering, and the worker forces subtitles (`modules/clipping/render.py:41-74`; `worker/run_job.py:375-382`). No platform-specific caption payload or native-caption sidecar is emitted.
- Buffer scheduling is queue scheduling, not two explicit timezone-aware schedules: the API requests `schedulingType: automatic` and `mode: addToQueue`, while the returned `dueAt` is not persisted (`cloudflare/api.js:247-252`; `cloudflare/schema.sql:100-110`).
- Approval can be bypassed because Buffer accepts `pending_review`; the frontend renders the upload button independent of approval and omits the review token on Buffer upload (`cloudflare/api.js:227-233`; `web/app.js:265-275,297-312`).
- Buffer operations are non-idempotent, append-only, sequential, and unreconciled. Partial success is reported as success if any channel queues (`cloudflare/api.js:237-258`; `web/app.js:272-275`).

The required completion rule should be: **exactly two compliant artifacts, one Tier 1 and one Tier 2; both approved against immutable artifact, caption, and rules revisions; six independent channel operations (2 videos × Instagram/TikTok/YouTube) reach verified terminal states; then stop.**

## Workflow assessment

| Stage | Target invariant | Current behavior | Verdict |
|---|---|---|---|
| Campaign/rules | Job executes an immutable, fully fingerprinted plan | Job references mutable campaign state; document rules are incomplete in AI provenance | Blocker/high |
| Clip set | Exactly two, one per tier, materially distinct | At most two; no tier contract, exact-count gate, or final pair gate | Blocker |
| Finished artifacts | Both render, validate, and upload | Missing renders are omitted; validation blocks only when all fail | Blocker |
| Captions/tags | Final edited text remains rule-compliant per platform | Draft is editable; server validates only empty/length | High |
| Sound/native metadata | Official sound and native tags are verified or explicitly manual | Boolean/checklist only | High limitation |
| Platform adaptation | Instagram, TikTok, YouTube receive supported payloads | One shared video/caption; no capability adapter | High |
| Approval | Only exact approved revision can mutate Buffer | `pending_review` accepted; browser upload lacks token | Blocker |
| Scheduling | Two explicit timezone-aware intents per video/channel | Automatic next-queue-slot behavior; `dueAt` not stored | Blocker for requested semantics |
| Delivery | Six operations have independent durable state | Append-only rows; no idempotency or reconciliation | High |
| Stop | Terminal aggregate after six verified outcomes | No six-operation aggregate or stop state | Missing |

## Confirmed findings

### Rules and provenance

`compile_plan` combines description, requirements, and `docs_text` for deterministic extraction and produces structured production fields including aspect ratio, duration, subtitles, official audio, handles, CTA URLs, hashtags, disclosures, posting rules, account rules, and CTA text (`core/campaign_rules.py:80-86,187-229`). Downstream caption generation consumes only a subset (`modules/clipping/review_queue.py:38-63`). The AI schema recognizes `subtitle_style` and several rule arrays, but `rules_fingerprint` excludes `docs_text` (`core/campaign_ai.py:60-103,120-128`). A campaign document can therefore change deterministic behavior without changing the AI cache key.

At job creation, the API inserts only campaign and queue fields (`cloudflare/api.js:319-330`). The worker later reads the current campaign and plan (`worker/run_job.py:151-180`). The campaign table’s `rules_hash` is not a substitute for a job snapshot because it is campaign-level and can change after enqueue (`cloudflare/schema.sql:1-20`).

### Two clips, tiers, and distinctness

The worker calls the selector with `MAX_REVIEW_CANDIDATES = 2`, but does not require two results (`worker/run_job.py:30-31,366-367`). It does not classify candidates as Tier 1 or Tier 2, enforce one-per-tier, or persist tier rationale. Duplicate filtering uses heuristic temporal overlap/token similarity and treats different source paths as non-duplicates; source truncation occurs before all preflight hashes are applied (`core/clip_candidates.py:227-258`; `worker/run_job.py:231-255`).

The render loop copies a result only when the expected file exists and continues with the remaining outputs (`worker/run_job.py:373-388`). Validation is per video and the job blocks only when all results fail (`worker/run_job.py:394-410`). Schema/API/UI accept any number of previews and have no expected count, tier, pair evidence, or stable candidate constraint (`cloudflare/schema.sql:56-74`; `cloudflare/api.js:501-508`; `web/app.js:226-233`).

### Captions, hashtags, disclosures, and platform adaptation

The review queue builds a draft from campaign title/brand, required handles as caption text, CTA URLs, candidate text, and up to eight inferred/explicit hashtags (`modules/clipping/review_queue.py:20-47`). It separately places native handles, official audio, CTA, and prohibited-content checks on a manual checklist (`modules/clipping/review_queue.py:75-100`). The draft does not fully consume disclosures, posting rules, account rules, or CTA text, and no final validator enforces them (`core/campaign_rules.py:214-222`; `modules/clipping/review_queue.py:38-63`).

The frontend exposes an editable textarea (`web/app.js:256-276`). The Buffer endpoint then accepts the edited text if it is non-empty and within a service limit derived from client-supplied metadata (`cloudflare/api.js:233-245`). It does not verify required components or bind the submitted text to an approved caption revision. The same text and generic video payload are sent to selected channels (`cloudflare/api.js:247-248`).

### Subtitles and sound

The renderer burns ASS subtitles whenever a transcript exists unless explicitly disabled, and the worker passes `--force-subtitles` (`modules/clipping/render.py:41-46,61-65`; `worker/run_job.py:375-382`). `subtitle_style` is extracted by AI but not used to choose a profile (`core/campaign_ai.py:68-70`; `core/campaign_rules.py:200-222`). Only a 9:16 master and review transcode are created (`worker/run_job.py:415-425`). There is no native caption sidecar, platform-specific safe-area profile, or per-platform caption payload.

Official audio is detected as a boolean and appears in the checklist (`core/campaign_rules.py:108,160-168,200-208`; `modules/clipping/review_queue.py:91-94`). The Buffer mutation carries neither track ID nor native-audio field (`cloudflare/api.js:247-248`). Thus the implemented state is **manual-native required**, not verified native audio. Native handles are similarly appended as text while native tagging remains a checklist. The repository does not establish whether the connected Buffer/native channels support track IDs, mentions, or caption-file fields.

### Approval, Buffer, scheduling, and capacity

The review transition supports approval, rejection, and rerender request (`cloudflare/api.js:467-486`). However, Buffer accepts both `pending_review` and `approved_for_manual_post` (`cloudflare/api.js:227-233`). The UI displays “Upload ke Buffer” for any preview with a download URL and sends no review token on that request (`web/app.js:297-312,265-275`). `REVIEW_TOKEN` is optional in the authorization helper (`cloudflare/api.js:146-150`). Approval is not bound to exact artifact, caption, rules, or schedule hashes. Rerender only changes status; it does not create a revision or dispatch work. Preview ingestion uses `INSERT OR REPLACE`, which can reset review state (`cloudflare/api.js:501-508`).

The Buffer integration queries channels and invokes `createPost` with `automatic` queue scheduling and `addToQueue` (`cloudflare/api.js:218-225,247-248`; `docs/BUFFER_INTEGRATION.md:17-23`). Official Buffer references cover authentication, posts/scheduling, and media hosting [2] [3] [4]. The requested timezone-aware schedules are not represented: no local time, IANA timezone, UTC instant, schedule mode, or persisted returned `dueAt` exists. The UI has no schedule controls or due-time display (`web/app.js:256-275`).

Uploads are sequential and partial. The API returns `ok` when any row is queued, while the UI displays only a count (`cloudflare/api.js:237-258`; `web/app.js:272-275`). `buffer_uploads` has no unique operation key, exact payload/caption, service, due time, attempts, retry class, or reconciliation state (`cloudflare/schema.sql:100-110`). Retries and timeouts can create duplicates or unknown provider state. Cleanup deletes old media without checking active Buffer dependencies (`cloudflare/api.js:260-275`).

The supplied audit treats Buffer Free as conditionally feasible for a low-volume pilot at up to three channels, ten scheduled posts per channel, and 3,000 API requests/month. Those values were not verified against the connected account and must be validated against current official plan terms [5]. The target consumes three channels, leaving no spare channel capacity under that assumption. A capacity preflight is required.

## Confirmed facts, assumptions, and unknowns

| Type | Statement |
|---|---|
| Confirmed | No job-level immutable plan snapshot exists in the supplied schema. |
| Confirmed | `docs_text` affects deterministic compilation but is excluded from the shown AI fingerprint. |
| Confirmed | The worker can produce fewer than two outputs and has no Tier 1/Tier 2 contract. |
| Confirmed | Caption edits are not server-validated against structured rules. |
| Confirmed | Official audio/native tags are not represented as verified provider fields. |
| Confirmed | Buffer uses automatic queue mode and does not persist returned `dueAt`. |
| Confirmed | Buffer operations lack durable idempotency and reconciliation fields. |
| Confirmed | No live Buffer call, account inspection, or external mutation occurred. |
| Assumption | The connected Buffer workspace supports Instagram, TikTok, and YouTube with the generic video payload. |
| Assumption | Free-tier capacity is sufficient for exactly three channels and six scheduled posts. |
| Unknown | Whether provider/channel adapters support native sound IDs, native mentions, or caption files. |
| Unknown | Whether “two schedules” means exact times or next queue slots. Current code implements only queue slots. |
| Decision required | Definitions and measurable thresholds for Tier 1, Tier 2, and material distinctness. |

## Acceptance criteria

The workflow is complete only when:

1. Job creation stores a plan snapshot, normalized rules contract, `rules_hash`, source-document hashes, and execution generation; the worker uses that snapshot only.
2. `docs_text`, AI evidence, and all normalized fields participate in the rules fingerprint and appear in the review evidence.
3. The plan declares exactly two outputs: one Tier 1 and one Tier 2. The job blocks unless selected, rendered, validated, and uploaded counts are all exactly two.
4. Final rendered artifacts pass documented pairwise distinctness thresholds, with evidence persisted in the manifest and previews.
5. Each platform caption is a revision. Server validation checks required/prohibited terms, handles, hashtags, CTA, disclosures, required phrases, service limits, and a caption hash.
6. Approval binds the exact artifact hash, caption revision, rules hash, platform profile, and schedule intent. `pending_review` cannot mutate Buffer.
7. Official sound and native tags are represented as verified, unsupported, manual-required, or failed. A checklist alone cannot be marked verified.
8. Instagram, TikTok, and YouTube receive capability-resolved payloads; unsupported fields remain explicitly manual.
9. Each video/channel operation persists local date/time, IANA timezone, UTC instant, mode, provider `dueAt`, and outcome. If queue mode is retained, the product says “next queue slot,” not exact scheduling.
10. Six operations have unique idempotency keys, exact payload hashes, provider IDs, attempts, retryability, errors, and reconciliation state. The aggregate stops only when all six reach required terminal states.
11. Media retention covers provider ingestion and recovery; cleanup checks active operations; staging proves stable HTTPS media reachability.
12. Cancellation and stale workers cannot write after a terminal or newer job generation.

## Priority order

The immediate blockers are: **(1)** immutable job provenance, **(2)** exact two-output/Tier 1–Tier 2 enforcement, **(3)** server-side approval and caption gates, and **(4)** explicit scheduling semantics. Next implement per-channel idempotent operations and reconciliation. Treat native sound, native tagging, and platform-specific caption features as capability-adapted integrations; preserve manual status where the provider cannot verify them.

## References

[1]: https://github.com/ibank31/scrapper-engine/blob/main/docs/AGENT_HANDOFF.md "Scrapper Engine agent handoff and production evidence"
[2]: https://developers.buffer.com/guides/authentication.html "Buffer API Authentication"
[3]: https://developers.buffer.com/guides/posts-and-scheduling.html "Buffer API Posts and Scheduling"
[4]: https://developers.buffer.com/guides/hosting-media.html "Buffer API Hosting Media"
[5]: https://buffer.com/pricing "Buffer pricing and plan limits"

> Buffer capability, provider deduplication, account permissions, TikTok availability, media-ingestion timing, and exact `dueAt` guarantees were not live-tested. References [2]–[5] are official implementation and plan sources, not proof that the connected account supports every target field.

**Final verdict:** **Not acceptance-ready.** Do not enable production Buffer mutation until the Phase 0 controls in `IMPLEMENTATION_ROADMAP.md` are implemented and tested.

**Document path:** `/home/ubuntu/scrapper-engine/docs/END_TO_END_WORKFLOW_AUDIT.md`

**No production code was modified. No external requests were sent.**

*Scope ends after Instagram, TikTok, and YouTube outcomes. Whop links and submission remain excluded.*

*Line references use the supplied repository state and may move after implementation.*
