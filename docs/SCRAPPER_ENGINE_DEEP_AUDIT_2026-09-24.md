# SCRAPPER ENGINE — DEEP REPOSITORY AUDIT / AGENT CONTEXT

**Audit date:** 24 September 2026  
**Repository:** `ibank31/scrapper-engine`  
**Branch:** `main`  
**Audited HEAD:** `0f1f06927b01764f2a5d0f581f76234cbfe7ff02`  
**HEAD message:** `split remaining roadmap into bounded phases`  
**Previous milestone:** `0b6e01913cdc295968716234e42b6a288b858ba3` — `complete phase 0 provenance and execution fencing`

## 1. Purpose of this document

Dokumen ini dibuat sebagai **context pack untuk agent baru**.

Tujuannya bukan menggantikan source code, tetapi menghilangkan pekerjaan bodoh yang berulang: agent tidak perlu menghabiskan kredit untuk melakukan scan repository dari nol hanya untuk mengetahui arsitektur, pipeline, status Phase 0, file penting, kontrak data, dan batasan kerja.

**Aturan agent:** gunakan dokumen ini sebagai peta awal, kemudian buka hanya file yang relevan dengan slice yang sedang dikerjakan. Jangan melakukan full-repository rediscovery kecuali ada indikasi bahwa dokumen ini sudah stale.

> Dokumen ini adalah snapshot audit statis. Ia tidak mengklaim verifikasi runtime baru di Cloudflare atau production pada saat audit ini.

---

# 2. Executive summary

Scrapper Engine adalah engine pribadi dengan dua domain:

1. **Affiliate product data**
   - scraping foto/spec produk dari sumber resmi;
   - manifest-driven product image workflow.
2. **Reward campaign / clipping**
   - discovery campaign;
   - detail/rules extraction;
   - AI campaign intelligence;
   - asset intake;
   - transcription;
   - deterministic clip candidate selection;
   - optional semantic ranking;
   - FFmpeg rendering;
   - technical/editorial/relevance validation;
   - human review;
   - Cloudflare Pages/D1/R2 preview workflow;
   - Buffer integration sudah ada di codebase tetapi production mutation sengaja belum menjadi bagian dari roadmap Phase 1.

Arsitektur saat ini:

```text
Content Rewards
    ↓
campaign radar / detail hydration
    ↓
rules + public docs + material references
    ↓
Gemini campaign intelligence
    ↓
compiled plan.json + rules_hash
    ↓
Cloudflare D1 campaign/job state
    ↓
manual job dispatch
    ↓
GitHub Actions Python worker
    ↓
asset intake
    ↓
source preflight
    ↓
Whisper transcription
    ↓
candidate generation / ranking
    ↓
optional Qwen semantic ranking
    ↓
relevance + policy gates
    ↓
FFmpeg 9:16 render + subtitles/crop
    ↓
technical/editorial validation
    ↓
review queue
    ↓
R2 preview + D1 preview metadata
    ↓
human review
    ↓
Buffer/manual publication path
```

**Kondisi roadmap saat ini:** Phase 0 sudah diimplementasikan. Phase 1 belum selesai. Slice berikutnya adalah **P1-A**, kemudian **P1-B**.

Target akhir roadmap bukan sekadar "menghasilkan dua MP4". Targetnya adalah:

```text
campaign
→ immutable rules
→ exactly 2 materially distinct finished clips
→ 1 Tier 1 + 1 Tier 2
→ preview
→ human approval
→ 2 timezone-aware schedule intents per video
→ Instagram + TikTok + YouTube
→ 6 independent delivery operations
→ explicit terminal states
→ stop
```

Whop, submission, payout, dan downstream campaign reporting **di luar scope roadmap ini**.

---

# 3. Repository layout

## Top-level

```text
.github/
  workflows/
    campaign-sync-ai.yml
    clipper-worker.yml
    preview-cleanup.yml
    semantic-fixture.yml
    tests.yml

cloudflare/
  api.js
  schema.sql
  migrations/
  README.md
  PRODUCTION_SETUP.md
  PHONE_ONLY_ARCHITECTURE.md
  FREE_COST_POLICY.md
  wrangler.toml.example

config/
  campaign_ai_profile.json

core/
  campaign_ai.py
  campaign_exclusions.py
  campaign_priority.py
  campaign_readiness.py
  campaign_rules.py
  captioning.py
  clip_candidates.py
  fetch.py
  google_drive.py
  google_sheets.py
  imgconv.py
  job_workspace.py
  media_signals.py
  nextjs_flight.py
  pagemeta.py
  production_policy.py
  relevance.py
  semantic_ranker.py
  textutil.py
  visual_crop.py

data/
  reward_campaign/
    campaigns.json
    DIGEST.md
    flight.txt

detail_probe/
  probe5.py

docs/
  AGENT_HANDOFF.md
  BUFFER_INTEGRATION.md
  END_TO_END_WORKFLOW_AUDIT.md
  IMPLEMENTATION_ROADMAP.md
  NEXT_AGENT_PROMPT.md
  SEMANTIC_CLIPPING_LOCAL.md
  SUBTITLE_STYLE_GUIDE.md
  VIDEO_QUALITY_EVALUATION_2026-09-23.md
  audit-subsystem-01-rules-sound.md
  audit-subsystem-02-two-clips.md
  audit-subsystem-03-buffer.md
  audit-subsystem-04-approval-data.md
  audit-subsystem-05-quality-ops.md
  google-drive-integration.md
  archive/...

manifests/
  sortirin_photos.json

modules/
  clipping/
    render.py
    review_queue.py
    select.py
    semantic_rank.py
    transcribe.py
    validate.py
  product_image/
    run.py
  reward_campaign/
    build_plan.py
    intake.py
    pull_detail.py
    scrape.py

scripts/
  benchmark_media_signals.py
  evaluate_semantic_fixture.py
  verify_production.sh

tests/
  fixtures/
  test_campaign_ai.py
  test_campaign_exclusions.py
  test_campaign_intake.py
  test_campaign_priority.py
  test_campaign_readiness.py
  test_campaign_rules.py
  test_candidate_limit.py
  test_clip_candidates.py
  test_google_drive.py
  test_google_sheets.py
  test_job_workspace.py
  test_media_signals.py
  test_production_policy.py
  test_relevance.py
  test_render_quality.py
  test_review_queue.py
  test_semantic_ranker.py
  test_worker_claim.py
  test_worker_diagnostics.py

web/
  app.js
  config.js
  index.html
  manual-config.js
  manual.html
  styles.css
  functions/api/[[path]].js

worker/
  run_job.py
  sync_campaigns.py

run.py
requirements.txt
requirements-semantic.txt
README.md
AGENTS.md
STATUS.md
```

Repository tree inspection confirms the project is not a tiny clipping script. It contains the scraper, campaign intelligence, local media pipeline, Cloudflare application layer, frontend, worker orchestration, tests, fixtures, deployment workflows, and a substantial documentation/audit layer.

---

# 4. Source-of-truth hierarchy

Agent harus memahami hierarki berikut:

1. **Current source code**
2. `docs/IMPLEMENTATION_ROADMAP.md` untuk target architecture dan acceptance gates
3. `docs/AGENT_HANDOFF.md` untuk operational context
4. `STATUS.md` untuk current milestone dan historical verification
5. `AGENTS.md` untuk non-negotiable engineering rules
6. Historical audit documents hanya sebagai konteks, bukan kontrak terbaru

Jika dokumentasi historis bertentangan dengan current code atau roadmap terbaru, jangan menghidupkan kembali desain lama.

---

# 5. Core campaign flow

## 5.1 Discovery

`modules/reward_campaign/scrape.py`

Fungsi utama:

- fetch `contentrewards.com/discover`;
- decode Next.js Flight payload;
- extract campaign objects;
- normalize budget/rate/platform/category;
- calculate relevance and priority;
- mark obvious excluded categories;
- output `data/reward_campaign/campaigns.json`;
- output `DIGEST.md`.

Campaign exclusion dipertegas lagi oleh:

`core/campaign_exclusions.py`

Current deterministic exclusion policy mencakup gambling / casino / betting / money-game style categories dan beberapa restricted categories.

**Penting:** excluded campaigns tidak boleh menghabiskan detail hydration atau Gemini quota.

---

# 6. Campaign detail and rules

## `modules/reward_campaign/pull_detail.py`

Mengambil detail campaign dan mengekstrak:

- campaign metadata;
- requirements;
- resources;
- payout data;
- public resource links.

Mendukung Google Drive OAuth jika tersedia dan public fallback dengan `gdown`.

Tidak ada bypass login/security wall.

## `core/campaign_rules.py`

Ini adalah salah satu modul paling penting.

`compile_plan()` menggabungkan:

- campaign description;
- static requirements;
- resource links;
- fetched `docs_text`;
- AI rules.

Kemudian menghasilkan production plan dengan:

- source of truth;
- normalized requirements;
- AI rules;
- production constraints;
- duration bounds;
- aspect ratio;
- subtitles;
- official audio;
- watermark;
- required handles;
- CTA;
- hashtags;
- disclosures;
- prohibited/allowed content;
- posting/account rules;
- gates;
- automation policy.

`publish_allowed` tetap `false`.

Campaign rules adalah source of truth. Jangan mengganti aturan campaign dengan asumsi global.

---

# 7. Gemini campaign intelligence

## `core/campaign_ai.py`

Gemini digunakan untuk mengubah rules tidak terstruktur menjadi structured intelligence.

Input penting:

- campaign identity;
- title/brand/category/type;
- platforms;
- description;
- requirements;
- resources;
- payouts;
- `docs_text`;
- source URLs;
- source-of-truth data.

Output normalized mencakup:

- campaign fit;
- confidence;
- production rules;
- platform;
- aspect ratio;
- duration;
- subtitles;
- watermark;
- official audio;
- CTA;
- handles;
- hashtags;
- disclosures;
- topic terms;
- allowed/prohibited content;
- posting/account rules;
- evidence;
- ambiguities.

AI result dianggap usable hanya bila confidence memadai dan tidak memiliki critical ambiguity.

Jika Gemini gagal, fallback **tidak mengarang aturan**. Campaign masuk status needs-review/uncertain.

## Fingerprinting

`rules_fingerprint()` membuat hash dari campaign/rule input agar Gemini tidak dipanggil ulang bila rules tidak berubah.

AI hanya perlu dijalankan untuk:

- campaign baru;
- rules hash berubah;
- atau force-AI manual run.

---

# 8. Daily campaign sync

## `worker/sync_campaigns.py`

Flow:

```text
scrape campaign radar
→ deterministic exclusion
→ active campaigns
→ parallel detail hydration
→ public Google Docs fetch
→ existing D1 intelligence lookup
→ rules fingerprint
→ Gemini only when required
→ compile_plan
→ priority scoring
→ readiness assessment
→ D1 sync
→ optional auto-queue
```

Auto-queue default:

```text
CLIPPER_AUTO_QUEUE=0
```

Jadi user-driven/manual flow tetap default.

Workflow:

`.github/workflows/campaign-sync-ai.yml`

- scheduled daily at 00:00 WIB;
- manual `workflow_dispatch`;
- Gemini API key dari GitHub secret;
- model selection configurable;
- current workflow uses a small AI batch size;
- secrets tidak ditulis ke source.

---

# 9. Campaign readiness

## `core/campaign_readiness.py`

Tujuan modul ini adalah ranking/decision support campaign sebelum clipping.

Status:

```text
siap
ketat
belum_siap
lewati
```

Ia mengidentifikasi:

- clipping vs UGC vs slideshow;
- public material hints;
- YouTube/Drive/Docs/direct media;
- login portal;
- account-heavy rules;
- strict caption;
- watermark requirements;
- fixed tags;
- Discord-centric rules;
- provided footage.

Ini bukan final production gate.

---

# 10. Asset intake

## `modules/reward_campaign/intake.py`

Membuat campaign workspace:

```text
job workspace/
  plan.json
  assets.json
  MANUAL_ASSETS.md
  assets/
  materials/
  outputs/
  review/
```

Menangani:

- direct media;
- YouTube;
- Google Drive;
- Google Sheets trackers;
- Google Docs references;
- campaign rules snapshot;
- checksums/provenance;
- unresolved/manual asset references.

Google Sheets support penting karena tracker dapat berisi actual Drive/YouTube/media URL dan metadata seperti Hype Level / Suggested Hook.

**Jangan menghapus provenance hanya karena source tidak dipakai.**

---

# 11. Local clipping pipeline

## `modules/clipping/transcribe.py`

Whisper local transcription.

Workflow production menggunakan:

```text
CLIPPER_WHISPER_MODEL=small
CLIPPER_WHISPER_BEAM=3
```

## `core/clip_candidates.py`

Candidate generation adalah deterministic dan auditable.

Memperhatikan:

- hook language;
- information/story signals;
- questions;
- concrete numbers;
- spoken density;
- sentence boundaries;
- complete ending;
- payoff;
- pause bridging;
- mid-thought starts;
- duration;
- media signals.

Whisper word timestamps dipakai untuk membentuk sentence/turn units.

Short pauses sampai sekitar 3 detik dapat dijembatani.

Long silence tidak boleh diseberangi.

Candidate payload saat ini sudah membawa selection metadata seperti:

- transcript span;
- unit count;
- bounds;
- pause budget;
- candidate count;
- empty-result reason.

---

# 12. Semantic ranking

## `core/semantic_ranker.py`

Optional local Qwen model:

```text
Qwen2.5-1.5B-Instruct-GGUF
Q4_K_M
```

Qwen bersifat advisory.

Deterministic ranker tetap authoritative.

Jika Qwen tidak tersedia:

```text
deterministic fallback
```

tetap menjalankan pipeline.

Historical verification:

- deterministic fixture: 4/4;
- isolated Qwen fixture: 3/4 decision accuracy, 4/4 risk coverage.

Jangan membuat production correctness bergantung pada Qwen.

---

# 13. Production policy and relevance

## `core/production_policy.py`

Enrich candidate dengan campaign-aware policy.

## `core/relevance.py`

Memisahkan:

- technical validity;
- campaign relevance.

Ini sengaja dilakukan karena MP4 yang valid secara teknis tetap bisa salah campaign.

**Rule:** jangan menyamakan `rendered` dengan `production-safe`.

---

# 14. Rendering

## `modules/clipping/render.py`

Current renderer:

- FFmpeg;
- 1080x1920;
- face-aware crop bila tersedia;
- centered fallback bila face tracking unavailable;
- subtitles sebagai normal quality policy;
- ASS subtitle rendering;
- watermark support;
- H.264;
- AAC;
- 48 kHz;
- loudnorm;
- faststart.

Current normal render menolak transcript yang hilang, karena subtitle dianggap quality policy.

`--no-subtitles` masih tersedia sebagai troubleshooting escape hatch.

**Roadmap Phase 2 akan mengganti pendekatan global ini dengan explicit platform/campaign subtitle profiles.**

---

# 15. Validation

## `modules/clipping/validate.py`

Checks current:

### Technical

- video stream;
- 1080x1920;
- H.264;
- square pixels;
- 23–60 FPS;
- audio stream;
- AAC;
- 48 kHz.

### Editorial

- effective minimum duration;
- campaign max duration;
- possible mid-thought opening;
- incomplete ending.

### Campaign/relevance

- campaign relevance status;
- watermark review;
- no third-party watermark review;
- official audio manual check;
- required handles manual check;
- CTA manual check.

Important:

Current validation can return:

```text
pass
needs_review
fail
```

It is **per candidate**, not yet the final hard campaign-level "exactly two required outputs" contract.

That is one of the main jobs of Phase 1.

---

# 16. Review queue

## `modules/clipping/review_queue.py`

Creates human review package:

- copied review video;
- thumbnail;
- `INDEX.md`;
- `review.json`;
- caption draft;
- checklist;
- campaign rule summary.

Caption generation is currently rule-aware but is not yet the immutable platform-specific caption revision model planned for Phase 2.

Current checklist explicitly surfaces:

- mandatory campaign requirements;
- handles;
- CTA;
- watermark;
- third-party watermark;
- official audio;
- prohibited content;
- validation/manual review.

---

# 17. Worker orchestration

## `worker/run_job.py`

This is the production orchestration center.

Conceptually:

```text
claim job
→ load immutable job snapshot
→ preflight
→ intake assets
→ source quality preflight
→ deduplicate sources
→ transcribe
→ candidate select
→ optional semantic rank
→ relevance/policy
→ render
→ validate
→ review queue
→ upload preview/video/thumbnail to R2
→ write manifest
→ insert preview rows
→ manual review
```

Phase 0 added fencing:

- job ID;
- run ID;
- execution generation;
- claim token;
- active run token;
- cancellation generation;
- immutable plan snapshot;
- rules hash;
- source fingerprint;
- manifest provenance.

Late/stale workers should receive conflicts instead of writing over current state.

---

# 18. Important current limitation: two-output contract is NOT implemented yet

The README says the worker produces at most two best candidates.

The roadmap requires something stricter:

```text
EXACTLY 2
1 × Tier 1
1 × Tier 2
```

Those are not equivalent.

Current code behavior is still essentially maximum-based:

```text
<= 2 candidates
```

The worker can therefore encounter:

```text
1 usable candidate
```

and continue with one preview.

The roadmap explicitly requires this to become a hard block:

```text
blocked_insufficient_output_contract
```

Likewise, current candidate selection has no durable Tier 1/Tier 2 contract.

This is why P1-A and P1-B exist.

---

# 19. Important current limitation: production workflow source count

The repository documentation describes processing multiple available video sources and retaining provenance.

However, the current GitHub Actions production worker explicitly sets:

```text
CLIPPER_MAX_VIDEO_SOURCES=1
```

in `.github/workflows/clipper-worker.yml`.

Therefore:

- code contains multi-source capability;
- production workflow currently constrains the run to one source;
- this must not be "fixed" casually during P1-A/P1-B;
- source-limit semantics are specifically addressed by the Phase 1 candidate identity/selection work.

Do not broaden this scope while implementing P1-A or P1-B.

---

# 20. Cloudflare architecture

## `cloudflare/api.js`

Cloudflare Pages Function / API layer.

Responsibilities include:

- D1 schema initialization/self-healing;
- campaigns;
- jobs;
- job claims;
- worker authorization;
- execution generation fences;
- stage events;
- previews;
- review transitions;
- R2 uploads;
- preview/media URLs;
- Buffer channel discovery;
- Buffer mutation guard;
- cleanup.

## `cloudflare/schema.sql`

Important current tables:

### `campaigns`

Contains:

- campaign identity;
- score;
- budget;
- platform JSON;
- detail JSON;
- plan JSON;
- first/last seen;
- priority components;
- competition proxy;
- rules hash;
- AI rules;
- AI status/timestamp.

### `jobs`

Contains Phase 0 provenance/fencing fields:

```text
plan_snapshot_json
rules_hash
plan_schema_version
source_fingerprint_json
execution_generation
cancelled_at
active_run_token
dispatch_token
run_id
manifest_key
manifest_schema_version
```

### `job_stage_events`

Durable stage telemetry.

### `previews`

Current fields include:

```text
rank
status
video_key
review_video_key
thumbnail_key
validation_json
caption_draft
checklist_json
artifact_hash
caption_revision_id
caption_hash
approval_artifact_hash
approval_caption_revision_id
approval_rules_hash
platform_profile_version
schedule_intent_hash
rules_summary_id
```

Some of these are Phase 0 scaffolding for later phases.

### `buffer_uploads`

Still exists as the older Buffer operation representation.

Phase 3 roadmap calls for a durable `delivery_operations` model rather than treating this old table as the final architecture.

---

# 21. Phase 0 status

Phase 0 is implemented in:

```text
0b6e019
```

HEAD then moved to:

```text
0f1f069
```

which mainly formalized the bounded roadmap.

Phase 0 implementation includes:

### Immutable provenance

Jobs snapshot:

- plan;
- rules hash;
- schema version;
- source fingerprint;
- execution generation.

### AI provenance

Document text and source URLs participate in fingerprints/prompt input.

### Approval binding

Approval is tied to:

- artifact hash;
- caption revision ID;
- rules hash;
- platform profile version;
- schedule intent hash.

### Worker fencing

Writes are protected by:

- claim token;
- run ID;
- generation;
- active run token.

### Cancellation

Cancellation increments execution generation and prevents stale worker writes.

### Schema

Checked-in schema and self-healing migration include the Phase 0 fields.

---

# 22. Phase 0 acceptance evidence

`STATUS.md` records the Phase 0 verification as:

- 88 tests passing for the Phase 0 verification;
- Python compilation/compileall;
- pip check;
- Node syntax checks;
- diff check;
- secret scan;
- GitHub Actions verification.

The latest HEAD itself does not introduce a new production pipeline implementation. It formalizes the bounded roadmap.

**Important documentation inconsistency:** older portions of `STATUS.md` still mention an 84-test verification from an earlier checkpoint, while the later Phase 0 section states 88 tests. Treat the later Phase 0 entry and the actual current Actions run as the relevant checkpoint. Do not assume an old number is the current suite size without running tests.

---

# 23. Current GitHub Actions

## `campaign-sync-ai.yml`

Schedule:

```text
00:00 WIB daily
```

Also supports manual dispatch with:

- force AI;
- model override.

## `clipper-worker.yml`

Manual dispatch only.

Current notable settings:

```text
timeout: 55 minutes
Whisper: small
beam: 3
max video sources: 1
FFmpeg preset: medium
CRF: 19
Qwen semantic model: enabled/auto
```

This is intentionally bounded because video processing is expensive.

## `tests.yml`

Runs:

```text
python -m unittest discover -s tests -v
semantic fixture
node --check cloudflare/api.js
node --check web/app.js
```

## `preview-cleanup.yml`

Handles preview retention/cleanup.

Roadmap Phase 4 will make cleanup aware of unresolved provider dependencies.

---

# 24. Frontend

## `web/app.js`

Current UI supports:

- campaign radar;
- filters/search;
- campaign detail;
- job queue;
- review previews;
- validation summary;
- caption draft;
- manual review actions;
- Buffer upload action after approval.

Current UI still presents preview rows largely by rank.

Roadmap Phase 1-E will eventually expose:

```text
candidate_id
tier
1/2 Tier 1
1/2 Tier 2
distinctness evidence
output contract status
```

Do not redesign this during P1-A or P1-B.

---

# 25. Buffer integration

Buffer integration is already present.

Recent commits show:

```text
61e9f3e  feat: add Buffer queue upload
1480a975 feat: add rule-aware captions and Buffer preflight
a3f2e39  fix: use Buffer organization id type
c4cd4f9  fix: allow read-only Buffer channel check
b90151d  docs: audit end-to-end Buffer workflow
```

Current server-side Buffer guard checks:

- preview exists;
- video exists;
- status is `approved_for_manual_post`;
- approval artifact hash matches;
- approval caption revision matches;
- approval rules hash matches.

However, the roadmap intentionally postpones the complete six-operation/idempotent scheduling contract until Phase 3.

**Do not modify Buffer mutation behavior during P1-A/P1-B.**

---

# 26. Known architecture gaps that are intentionally future work

These are not bugs to opportunistically fix during P1-A/P1-B.

## Phase 1

Missing:

- versioned output contract;
- exact two-output enforcement;
- Tier 1/Tier 2 semantics;
- durable candidate identity;
- deterministic tier classifier;
- exact selector gate;
- all-or-nothing render/validation;
- final pairwise distinctness evidence;
- review output contract UI.

## Phase 2

Missing:

- platform profiles;
- immutable caption revisions;
- common compliance validator;
- subtitle delivery profiles;
- honest native sound/tag capability records.

## Phase 3

Missing:

- explicit exact-vs-queue schedule semantics;
- durable six-operation delivery model;
- server-side channel capability resolution;
- robust idempotency;
- unknown-result reconciliation;
- six-operation UI.

## Phase 4

Missing:

- provider-aware retention;
- reconciliation loop;
- capacity/budget management;
- durable retry/alert model;
- rerender lineage.

## Phase 5

Missing:

- controlled pilot;
- staging readiness fixture;
- production enablement gate.

---

# 27. Critical current behavior vs target behavior

| Area | Current repository | Roadmap target |
|---|---|---|
| Candidate count | Maximum/at-most two behavior | Exactly two |
| Tier | No durable Tier 1/Tier 2 contract | Exactly 1 Tier 1 + 1 Tier 2 |
| Candidate identity | Existing candidate data but not Phase 1 durable identity contract | Stable candidate ID + source identity/hash + transcript hash |
| Source identity | Multi-source capability exists | Normalize identity before source limit |
| Source limit in workflow | `CLIPPER_MAX_VIDEO_SOURCES=1` | Phase 1 selection semantics must preserve source evidence |
| Render failure | Candidate-level behavior can continue if another output survives | Required pair is all-or-nothing |
| Validation | Per-output status | Campaign-level required-output gate |
| Distinctness | Some historical/current heuristics exist | Versioned final artifact pairwise evidence |
| Captions | Rule-aware draft | Immutable platform-specific revisions |
| Subtitles | Global production quality policy | Explicit platform/campaign profile |
| Official audio | Manual review instruction | Explicit status/evidence |
| Native tags | Manual review instruction | Explicit provider capability/status |
| Buffer | Existing guarded mutation path | Six durable idempotent operations |
| Scheduling | Queue-oriented Buffer path | Exact/queue semantics explicitly represented |
| Cleanup | Preview cleanup exists | Provider dependency-aware retention |
| Production publication | Manual/human approval | Controlled pilot before automation |

---

# 28. Tests and regression philosophy

Current tests cover:

- campaign AI;
- campaign exclusions;
- campaign intake;
- priority;
- readiness;
- rules;
- candidate limits;
- candidate segmentation/ranking;
- Google Drive/Sheets;
- workspace;
- media signals;
- production policy;
- relevance;
- render quality;
- review queue;
- semantic ranker;
- worker claim;
- worker diagnostics.

Examples already present:

```text
test_limit_two_returns_only_two_candidates
test_word_timestamps_form_sentence_units_at_punctuation_and_pauses
test_selects_ranked_non_overlapping_windows
test_rewards_complete_payoff_over_keyword_only_excerpt
test_short_source_can_still_produce_a_candidate
test_bridges_short_pause_but_not_long_silence
test_media_adjustment_does_not_change_candidate_interval
test_claim_sends_dispatch_token_and_succeeds
test_lost_claim_is_clean_noop
test_unexpected_claim_error_is_not_hidden
test_caption_and_checklist_follow_plan
test_mandatory_source_rule_is_visible
test_caption_metadata_contains_rules_and_relevant_hashtags
```

The roadmap adds required future fixtures such as:

```text
requires_exactly_two_outputs
requires_one_tier_1_and_one_tier_2
blocks_missing_render
blocks_validation_failure_in_one_required_clip
blocks_cross_source_duplicate_final_artifacts
...
```

---

# 29. P1-A: exact scope for the next agent

## Goal

Define the **versioned two-output contract**.

Expected contract:

```json
{
  "output_contract": {
    "expected_count": 2,
    "tier_allocation": {
      "tier_1": 1,
      "tier_2": 1
    },
    "min_duration_seconds": 0,
    "max_duration_seconds": 0,
    "distinctness_profile": "default-v1"
  }
}
```

P1-A should establish:

- schema representation;
- validation helper;
- deterministic pure validation;
- invalid-contract blocking reason;
- campaign-specific duration override validation;
- regression fixtures.

P1-A must NOT:

- implement candidate identity;
- implement tier classifier;
- select exactly two candidates;
- change rendering;
- change Buffer;
- change scheduling;
- change Phase 2 caption logic.

Acceptance:

```text
valid contract passes
missing contract fields fail
expected_count != 2 fails
tier allocation != 1+1 fails
invalid duration bounds fail
invalid distinctness profile fails
campaign duration override incompatibility fails
```

---

# 30. P1-B: exact scope for the following agent

## Goal

Define durable candidate identity and deterministic tiers.

Candidate should carry at least:

```text
candidate_id
normalized source_asset_id
source hash
transcript hash
start
end
tier
selection rationale
rules hash
classifier/profile version
```

Required behavior:

1. Normalize source identity before source truncation.
2. Deduplicate exact/perceptual sources before source limit.
3. Retain excluded-source evidence.
4. Use a deterministic versioned tier classifier.
5. Do not infer tier from old campaign metadata flag.
6. Unclassifiable candidates are not eligible for a required tier.

P1-B must NOT:

- enforce exact two selection;
- change render behavior;
- change Buffer;
- modify platform caption logic;
- begin P1-C.

---

# 31. Bounded agent protocol

Every agent session should follow:

```text
1. Read AGENTS.md.
2. Read this context document.
3. Read only the relevant slice in IMPLEMENTATION_ROADMAP.md.
4. Inspect the specific files required by that slice.
5. Confirm previous slice acceptance.
6. Make the smallest reversible implementation.
7. Add regression tests.
8. Run targeted tests.
9. Run repository verification required by AGENTS.md.
10. Report changed files and acceptance result.
11. STOP.
```

The agent must not:

- scan the whole repository repeatedly;
- redesign unrelated subsystems;
- fix Buffer during Phase 1;
- deploy production;
- mutate production data;
- rotate secrets;
- add Whop/submission logic;
- start the next slice automatically;
- convert an acceptance failure into a "best effort" implementation.

---

# 32. Current Git history context

Recent commits on `main` show the project moving rapidly toward the current architecture.

Important sequence:

```text
0f1f069  split remaining roadmap into bounded phases
0b6e019  complete phase 0 provenance and execution fencing
b90151d  docs: audit end-to-end Buffer workflow
a3f2e39  fix: use Buffer organization id type
c4cd4f9  fix: allow read-only Buffer channel check
1480a97  feat: add rule-aware captions and Buffer preflight
61e9f3b  feat: add Buffer queue upload
2f445a8  style: lower and strengthen global subtitles
8cbfab0  fix: improve global subtitle style and distinct previews
f5de973  feat: add platform-safe subtitle emphasis styling
dfacd4d  fix: render visible short-form subtitles
47a357a  docs: record Backyard production smoke test
592742e  docs: remove session-specific connector note
```

This history matters because the repository is in a transition from a quality-first best-effort clipping pipeline toward a contract-driven production system.

Do not mistake historical features for completed roadmap contracts.

---

# 33. What is already strong

The audit found several mature pieces that future agents should reuse rather than rewrite:

- campaign rules are already treated as source of truth;
- public document text is incorporated into rule understanding;
- AI fingerprinting prevents unnecessary Gemini calls;
- AI failure falls back safely;
- campaign exclusions happen before expensive detail/AI work;
- Google Drive/Sheets intake is already substantial;
- source preflight and provenance exist;
- Whisper word timestamps are used intelligently;
- candidate ranking is deterministic and auditable;
- Qwen is advisory with deterministic fallback;
- relevance is separated from technical validation;
- render output has strong technical normalization;
- human review is explicit;
- Phase 0 job provenance is implemented;
- stale worker writes are fenced;
- Buffer mutation already has approval/provenance checks;
- tests and CI are established.

These are foundations, not things to replace just because a new agent wants to demonstrate productivity by rewriting half the repo. Humanity has enough rewrites already.

---

# 34. What an agent must understand before touching code

The single most important conceptual distinction:

```text
CURRENT:
"Produce up to two good clips."

TARGET:
"Prove that exactly two required clips exist,
one Tier 1 and one Tier 2,
both valid,
both materially distinct,
and only then permit review."
```

Another critical distinction:

```text
CURRENT:
"Manual checklist says official audio / native tags should be checked."

TARGET:
"System records whether the provider capability actually
verified the field, or explicitly marks it manual_required/unsupported."
```

And:

```text
CURRENT:
"Buffer upload works after approval."

TARGET:
"Six independent delivery operations are durable,
idempotent, reconcilable, and have explicit terminal states."
```

---

# 35. Agent quick-start

If an agent has only a few minutes of context budget, it should read:

```text
1. This document
2. AGENTS.md
3. docs/IMPLEMENTATION_ROADMAP.md
   only the active slice section
4. The specific source files named by that slice
5. Relevant tests
```

For **P1-A**:

```text
core/campaign_rules.py
modules/reward_campaign/build_plan.py
tests/test_campaign_rules.py
tests/test_campaign_ai.py
docs/IMPLEMENTATION_ROADMAP.md
```

For **P1-B**:

```text
core/clip_candidates.py
core/production_policy.py
worker/run_job.py
modules/clipping/select.py
tests/test_clip_candidates.py
tests/test_candidate_limit.py
```

Do not read Buffer files for P1-A/P1-B unless a direct dependency is proven.

---

# 36. Audit conclusion

At the audited HEAD, the repository is not "unfinished from scratch". It is a functioning campaign-aware clipping engine with substantial production hardening already implemented.

The major unfinished work is **contract hardening**, especially:

```text
P1:
exact two outputs + Tier 1/Tier 2 + durable candidate identity

P2:
platform caption/subtitle/audio/tag contracts

P3:
timezone scheduling + six durable delivery operations

P4:
retention + reconciliation + recovery

P5:
controlled pilot
```

The current next action is therefore narrow and deliberate:

```text
P1-A → output contract foundation
P1-B → candidate identity and deterministic tiers
P1-C → exact selection
P1-D → all-or-nothing render/validation
P1-E → review visibility
```

Each slice should be completed and accepted before the next begins.

**Do not ask a new agent to rediscover the entire repository before every slice. This document exists specifically to stop that waste.**
