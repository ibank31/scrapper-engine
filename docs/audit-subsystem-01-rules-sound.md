# Audit Subsystem 01 — Campaign Rules, Captions, Hashtags, Subtitles, and Sound

**Scope.** This audit traces campaign rules from campaign synchronization and plan compilation through caption generation, burned-in subtitles, audio handling, review, and Buffer queuing. It covers the repository state examined on 24 September 2026. No production code was modified, no Buffer post was sent, and no external mutation was performed.

## Executive conclusion

The engine has a useful deterministic path for producing a reviewable vertical video and a caption draft, but it does **not** yet have a complete rule-to-publication contract. Campaign rules are extracted into `plan.json`, persisted in the campaign row, and partially surfaced in the review queue. Captions and hashtags are generated before review. Subtitles and normalized source audio are rendered into the MP4. However, several rule classes stop at a checklist instead of becoming an enforceable artifact: official/native sound, native handle tagging, disclosures, CTA text, platform-specific captions, and native captions.

The most material risks are **(1) queued jobs do not snapshot the plan or rule hash, (2) document-only rules are excluded from the AI prompt and the rules fingerprint, (3) the final editable caption is only checked for emptiness and length, (4) subtitle settings from the plan are ignored in favor of a global renderer, and (5) official sound has no asset or platform-track identity and cannot be attached by the Buffer request shown in the code**. Human review reduces publication risk, but the review UI does not prove that the final caption, sound, tags, or subtitle treatment satisfy the campaign.

## End-to-end current behavior

1. `worker/sync_campaigns.py` hydrates campaign details and public Google Docs, then compiles a plan with `compile_plan()` and stores it as `campaign.plan_json` (`worker/sync_campaigns.py:74-96`, `worker/sync_campaigns.py:259-264`).
2. `core/campaign_rules.py` combines description, requirement text, and `docs_text`; it extracts URLs, duration, watermark, official-audio, handles, CTA URLs, and normalized requirements (`core/campaign_rules.py:75-158`). It also merges selected AI rule fields into `production` (`core/campaign_rules.py:170-222`).
3. A job stores only `campaign_id`; when the worker runs, it reads the current campaign plan from the joined campaign row (`cloudflare/api.js:319-330`, `cloudflare/api.js:444-448`; `worker/run_job.py:151-180`).
4. The worker transcribes official media, selects candidates, applies relevance and duration gates, then renders the selected clips with `--force-subtitles` (`worker/run_job.py:285-352`, `worker/run_job.py:373-398`).
5. The renderer always burns in ASS subtitles when a transcript exists unless the explicit troubleshooting flag `--no-subtitles` is used. It copies source audio, encodes AAC, and applies `loudnorm` (`modules/clipping/render.py:38-74`).
6. The review queue creates a deterministic caption from title/brand, required handles, CTA URLs, candidate speech text, and hashtags. It creates a checklist for rules that still require human action (`modules/clipping/review_queue.py:38-64`, `modules/clipping/review_queue.py:75-100`).
7. The dashboard shows the draft and permits free-text editing before a Buffer action (`web/app.js:256-276`). The API checks only non-empty text and a conservative service length before calling Buffer with text and a video asset (`cloudflare/api.js:227-258`).
8. Buffer receives a video URL and caption text. There is no sound-track identifier, native handle field, native caption file, per-platform caption variant, or rule-validation result in that mutation (`cloudflare/api.js:247-248`).

## Findings

### F-01 — **High: Jobs do not snapshot the applied campaign plan or rule hash**

**Evidence.** Job creation inserts `campaign_id`, status, and timestamps, but no plan, `rules_hash`, or plan version (`cloudflare/api.js:319-330`; `cloudflare/schema.sql:23-39`). The worker later reads `job.campaign_plan`, which is populated from the current campaign row (`cloudflare/api.js:444-448`), and uses that plan for intake, selection, rendering, validation, and review (`worker/run_job.py:151-180`, `worker/run_job.py:228-437`).

**Current behavior.** A queued job can use rules different from the rules visible when the user selected the campaign. The review record retains only a flattened `rules_summary_id` string, not the complete plan or hash (`cloudflare/schema.sql:56-73`; `worker/run_job.py:437-438`).

**Target behavior.** At job creation, persist an immutable plan snapshot and `rules_hash` (or a plan version). The worker must use that snapshot and record the same hash in the manifest and preview. If the campaign changes, the job should either retain the original contract or be explicitly invalidated and requeued.

**Impact.** Reproducibility and audit evidence are incomplete. A reviewer cannot reliably prove which campaign rules produced a particular caption, subtitle treatment, or sound checklist.

### F-02 — **High: Document-only rules are not supplied to AI and are omitted from the rules fingerprint**

**Evidence.** Synchronization fetches public Google Docs into `campaign["docs_text"]` (`worker/sync_campaigns.py:47-72`). The deterministic compiler consumes that text (`core/campaign_rules.py:83-86`). However, the AI prompt payload includes title, brand, category, type, platforms, description, requirements, resources, and payouts, but not `docs_text` (`core/campaign_ai.py:325-330`). The fingerprint likewise omits `docs_text` (`core/campaign_ai.py:120-128`).

**Current behavior.** Regex-based rules such as an explicit duration range can be extracted from a document, but AI-only rules such as subtitle style, hashtags, disclosures, or account/posting rules cannot be reliably analyzed from that document. A document-only change can also reuse cached AI output because the fingerprint does not change.

**Target behavior.** Include normalized document text and document provenance in the AI payload and fingerprint. Preserve evidence linking each extracted rule to its source text. Treat a changed document as a new rules version.

**Impact.** The plan can be internally inconsistent: deterministic fields reflect current document text while AI-derived fields remain stale or absent.

### F-03 — **High: Final caption edits can remove mandatory rules without a second validation gate**

**Evidence.** The UI places `caption_draft` in an unrestricted textarea (`web/app.js:256-276`). The Buffer endpoint accepts caller-supplied `body.text` or the draft and checks only empty text and a service length limit (`cloudflare/api.js:235-245`). It does not re-check handles, hashtags, CTA, disclosure, prohibited terms, or mandatory requirement text before the Buffer mutation.

**Current behavior.** A reviewer can delete a required handle, CTA URL, hashtag, disclosure, or other required phrase and still queue the video if the remaining text is non-empty and within the conservative length limit.

**Target behavior.** Store structured caption components and validate the final text against the plan immediately before any external queue action. The API should return a per-rule result and reject or require an explicit override for missing mandatory components. A caption diff should be retained for audit.

**Impact.** The system presents a compliant-looking draft but does not enforce compliance at the last controllable point.

### F-04 — **High: Official/native sound is represented only as a boolean and a manual reminder**

**Evidence.** Rule compilation produces `production.official_audio_required` as a boolean, with no sound asset, track ID, source URL, timing, or platform mapping (`core/campaign_rules.py:108`, `core/campaign_rules.py:200-220`). Validation and review only tell the operator to attach official sound in the native composer (`modules/clipping/validate.py:78-87`; `modules/clipping/review_queue.py:91-94`). The renderer preserves source audio and normalizes it, but does not identify or attach an official platform sound (`modules/clipping/render.py:66-74`). The Buffer mutation contains only caption text and a video asset (`cloudflare/api.js:247-248`).

**Current behavior.** The engine can produce a video with source audio and a checklist item. It cannot prove that the required campaign sound is the platform-native sound, nor can the shown Buffer request select that sound. Manual native-platform completion is required.

**Target behavior.** Model sound as a structured rule: platform, official track ID or approved source, source audio policy, mix/ducking policy, and evidence state. If the platform/Buffer path cannot attach native sound, make that limitation explicit in the UI and keep the item in a manual-native-post state. Do not label the action “automatic” when a mandatory native sound step remains.

**Impact.** A technically valid MP4 can still fail a campaign’s central audio requirement.

### F-05 — **High: Required handles are put into caption text, while the checklist separately requires native tagging**

**Evidence.** `caption_metadata()` appends `production.required_handles` directly to the caption (`modules/clipping/review_queue.py:38-47`). The checklist says to add required handles in the platform’s native tagging field (`modules/clipping/review_queue.py:91-95`). The Buffer mutation has no native tagging input; it sends only `text`, `channelId`, and `assets` (`cloudflare/api.js:247-248`).

**Current behavior.** The same handle may be rendered as visible text but not tagged as an account. The implementation does not distinguish “mention text” from “native mention metadata.”

**Target behavior.** Represent required handles with an explicit mode: caption text, native tag, or both. Validate what the selected platform/Buffer adapter supports. If native tagging is unsupported, stop at manual native posting or show a blocking unmet requirement.

**Impact.** A visible `@handle` is not evidence of a native account tag.

### F-06 — **High: Plan caption fields are only partially consumed**

**Evidence.** The plan carries `hashtags`, `disclosures`, `posting_rules`, `account_rules`, and `cta_text` (`core/campaign_rules.py:214-222`). Caption generation uses title/brand, handles, CTA URLs, candidate text, and hashtags, but not `cta_text`, disclosures, posting rules, account rules, or the full mandatory requirement text (`modules/clipping/review_queue.py:38-63`). Mandatory requirements appear in the summary/checklist rather than being composed into the caption (`modules/clipping/review_queue.py:48-63`, `75-100`).

**Current behavior.** A plan can contain explicit caption obligations that never reach the draft. The reviewer receives a reminder, but the final Buffer preflight does not enforce it.

**Target behavior.** Compile a structured caption contract with required components, optional components, prohibited terms, placement, and platform scope. Generate the draft from that contract and validate the edited result.

**Impact.** “Rule entered the plan” currently does not mean “rule became caption content.”

### F-07 — **Medium: Subtitle policy is global and ignores campaign subtitle settings**

**Evidence.** AI extraction supports `subtitle_required` and `subtitle_style` (`core/campaign_ai.py:68-70`, `298-318`). The plan stores only `subtitle_required`; `subtitle_style` is not copied into `production` (`core/campaign_rules.py:200-222`). The renderer enables subtitles whenever a transcript exists, regardless of `production.subtitle_required`, and always uses the global ASS style (`modules/clipping/render.py:41-46`, `61-65`; `core/captioning.py:96-118`). The worker explicitly passes `--force-subtitles` (`worker/run_job.py:380-382`).

**Current behavior.** Subtitles are burned into every normal production render. A campaign that does not require subtitles still receives them, while a campaign-specific style is not applied. The subtitle system strips fillers and adjacent duplicate words (`core/captioning.py:23-38`) and uses global four-word/28-character cues and global emphasis vocabulary (`core/captioning.py:41-70`, `105-115`).

**Target behavior.** Decide separately whether subtitles are required, optional, or prohibited. Carry style, language, safe-area, and emphasis rules into rendering. Preserve the original transcript and record the transformed cue text. Generate a native caption sidecar or platform caption payload when the publication path supports it.

**Impact.** Burned-in subtitles are an irreversible visual treatment and are not equivalent to user-controlled native captions.

### F-08 — **Medium: No native caption/subtitle artifact or platform-specific render is produced**

**Evidence.** The pipeline uploads MP4, review MP4, thumbnail, and manifest artifacts (`worker/run_job.py:415-447`). The Buffer request sends only a video asset (`cloudflare/api.js:247-248`). Repository guidance explicitly says burned-in subtitles do not replace platform caption controls and recommends native captions where supported (`docs/SUBTITLE_STYLE_GUIDE.md:49-53`).

**Current behavior.** The output is one global 1080×1920 master and one global subtitle style. The style guide acknowledges that safe zones differ by platform (`docs/SUBTITLE_STYLE_GUIDE.md:6-22`, `24-43`), but the code does not create platform variants or a native caption payload.

**Target behavior.** Keep a master render, but add platform profiles for safe area, caption placement, language, and caption delivery. At minimum, make the review artifact state “burned-in only” and require platform-native caption completion when required.

**Impact.** A single preview cannot prove safe placement or caption compliance on every selected platform.

### F-09 — **Medium: Hashtag generation is deterministic but not platform- or rule-sensitive enough**

**Evidence.** Explicit tags are combined with a small inferred lexicon from campaign title, brand, category, and candidate text, normalized, deduplicated, and truncated to eight (`modules/clipping/review_queue.py:20-35`). The same caption text is then sent to every selected Buffer channel (`cloudflare/api.js:233-248`).

**Current behavior.** The engine avoids wholly speculative tags, but it can add inferred tags even when the campaign provides no explicit hashtag rule. It does not preserve hashtag provenance, distinguish required from suggested tags, or create per-platform variants.

**Target behavior.** Label each tag as required, allowed suggestion, or rejected; preserve the source rule; validate the final edited set; and generate a platform-specific caption when channel constraints or campaign rules differ.

**Impact.** Reviewers cannot tell which tags are mandatory, and one text variant is reused across different services.

### F-10 — **Medium: AI ambiguity does not block rendering, despite `render_allowed` being false**

**Evidence.** Plan compilation sets `automation_policy.render_allowed` only when AI rules exist and status is `pass` (`core/campaign_rules.py:224-228`). The worker, however, blocks only statuses `fail`, `rejected`, or `blocked`, critical ambiguities, and low-confidence `pass`; `needs_review` proceeds to production (`worker/run_job.py:183-216`).

**Current behavior.** A plan marked `needs_review` can still consume assets, transcribe, render, and reach human review. This is consistent with a human-gated workflow but inconsistent with the plan’s `render_allowed` field.

**Target behavior.** Define the distinction explicitly: either block automated rendering for unresolved mandatory ambiguity, or mark the plan as “render allowed with human rule review” and surface the unresolved fields before processing.

**Impact.** The automation contract is ambiguous, especially for sound, caption, and platform rules extracted with low confidence.

### F-11 — **Low: Rules provenance and caption identity are weakly persisted**

**Evidence.** `rules_summary_id` is a concatenated human-readable summary, not an identifier tied to a plan version (`modules/clipping/review_queue.py:57-63`; `cloudflare/schema.sql:66-72`). `buffer_uploads` stores preview, channel, Buffer post ID, status, and error, but not the final text, hashtag set, native sound state, or platform service (`cloudflare/schema.sql:100-110`).

**Current behavior.** The operator can see a summary, but later audit cannot reconstruct the exact rule inputs and final caption sent to each channel.

**Target behavior.** Persist `plan_hash`, structured rule evaluations, final caption text, required/actual tags, channel service, and sound/native-caption completion state per upload attempt.

## Automation and native-platform limitations

**Automated today:** rule compilation; AI-assisted rule extraction; duration/relevance gates; candidate selection; burned-in subtitle generation; AAC encoding and loudness normalization; deterministic caption draft; inferred/explicit hashtag draft; review artifact creation; conservative Buffer text-length preflight.

**Human-gated today:** visual watermark verification; uncertain relevance; required native handles; CTA placement; official/native sound attachment; final review decision; any actual Buffer queue action. The repository contract correctly states that publishing remains manual/human-approved (`docs/AGENT_HANDOFF.md:8-10`, `83-90`). Buffer integration, however, is an external queue mutation after confirmation, not a native-platform composer and not proof of native sound or tagging (`docs/BUFFER_INTEGRATION.md:17-23`).

**Native limitations visible in this implementation:** the Buffer mutation shown has no native sound-track selector, native mention field, or native caption-file input (`cloudflare/api.js:247-248`). The system uses one 9:16 master and global subtitle style despite platform-specific safe-zone differences (`docs/SUBTITLE_STYLE_GUIDE.md:6-22`, `24-35`). Therefore, official sound, native tagging, and native caption delivery must remain explicit manual or adapter-specific steps unless a future platform adapter supports them.

## Phased recommendations

### Phase 0 — Make the current contract honest

1. Add a job-level immutable plan snapshot, `rules_hash`, and source provenance. Include them in the manifest and preview record.
2. Add a pre-Buffer caption compliance endpoint or server-side gate. Check required handles, hashtags, CTA text/URL, disclosures, mandatory phrases, prohibited terms, and per-channel limits against the edited text.
3. Change UI labels and checklist language to distinguish **draft**, **Buffer queue**, **native-platform posting**, and **native sound/tagging still required**.
4. Expose unresolved AI ambiguities and a clear `render_allowed_with_human_review` state.

### Phase 1 — Close rule-to-artifact gaps

1. Include `docs_text` in AI input, fingerprinting, and evidence. Add deterministic document provenance to `source_of_truth`.
2. Carry `subtitle_style`, subtitle language, safe-area profile, `cta_text`, disclosures, posting rules, and account rules into a structured caption/render contract.
3. Separate required handles from caption text and native tags. Preserve required versus inferred hashtags and their provenance.
4. Persist the exact final caption and structured compliance result for every Buffer channel attempt.

### Phase 2 — Add platform-aware media delivery

1. Define a sound contract with approved source/track IDs, platform, audio ownership state, and manual-completion evidence. Keep source audio normalization separate from native-sound attachment.
2. Produce platform profiles or variants for subtitle safe areas and caption delivery. Add native caption sidecars/payloads where the adapter supports them.
3. Add a final review checklist that records sound attached, native tags applied, CTA placement, native captions enabled, and the exact platform/channel.

### Phase 3 — Adapter and automation hardening

Only automate native sound, tagging, or publication where the selected platform API/Buffer adapter explicitly supports the required fields and returns verifiable success. Otherwise keep the workflow manual and make the limitation a first-class status, not an unchecked checklist item. Add regression fixtures for document-only rules, caption deletion, required sound, required handles, and platform-specific caption variants.

## Assumptions and audit gaps

- This audit assumes `campaign_plan` is always the current `campaigns.plan_json` returned by the API; the schema provides no job-level snapshot to confirm otherwise.
- The supplied repository files do not establish which specific external native-sound or native-tag fields a particular Buffer channel might support beyond the request shape implemented here. The finding is therefore limited to the code’s absence of such fields and the documented manual-native step.
- No live Buffer call, campaign sync, worker run, or production queue action was executed.
- The report does not assess the semantic quality of the spoken clip beyond how its transcript is reused for subtitles and caption text.

## References

[1]: ../core/campaign_rules.py "Campaign rule compiler"
[2]: ../core/campaign_ai.py "Campaign AI extraction and normalization"
[3]: ../worker/sync_campaigns.py "Campaign synchronization and plan persistence"
[4]: ../worker/run_job.py "Clipping worker pipeline"
[5]: ../modules/clipping/render.py "Vertical clip renderer"
[6]: ../core/captioning.py "Subtitle cue and ASS/SRT generation"
[7]: ../modules/clipping/review_queue.py "Review queue and caption draft generation"
[8]: ../modules/clipping/validate.py "Technical and campaign-aware validation"
[9]: ../cloudflare/api.js "Cloudflare API, preview, review, and Buffer routes"
[10]: ../cloudflare/schema.sql "D1 schema"
[11]: ../web/app.js "Review UI and Buffer caption workflow"
[12]: ./BUFFER_INTEGRATION.md "Buffer integration contract"
[13]: ./SUBTITLE_STYLE_GUIDE.md "Subtitle style and platform safe-zone guidance"
[14]: ./AGENT_HANDOFF.md "Current product contract and operational guardrails"
