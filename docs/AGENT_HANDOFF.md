# Scrapper Engine — Current Agent Handoff

**Updated:** 23 September 2026
**Repository:** `ibank31/scrapper-engine`
**Production branch:** `main`
**Latest implementation commit:** `186f93814608087c87beb78e34bb6d6725bcdcdf` — documentation update after the Google Sheets intake fix and CI verification. The implementation fix is `9a9ba780`; compatibility repair is `d22dfb36c3da3fe50636fe768329392dc1309b74`; subsequent documentation commits are `50651193c1ba8113638442e8c7ed77f0a263a703` and `186f93814608087c87beb78e34bb6d6725bcdcdf`.

## Product contract

The system starts from a campaign selected by the user. It reads and snapshots the campaign rules, downloads only official campaign materials, transcribes the source, finds complete moments, renders vertical previews, validates the result against the campaign plan, and puts only reviewable previews into the dashboard. Posting remains manual. `plan.json` and its `source_of_truth` fields are authoritative.

## Current pipeline

```text
campaign selection
  -> campaign detail and plan compiler
  -> official Drive/YouTube/direct asset intake
  -> faster-whisper word timestamps
  -> multi-band sentence/turn candidate windows
  -> hook/context/payoff/pacing production policy
  -> optional local Qwen subtitle semantic ranking
  -> campaign relevance and duration gates
  -> FFmpeg vertical render with face-aware crop
  -> technical/editorial validation
  -> review queue and manual ACC
```

The semantic stage is subtitle-first. It is implemented in `core/semantic_ranker.py`, exposed as `python run.py semantic_rank`, and called by `worker/run_job.py` after `select_clips`. The model ranks candidates; it does not invent timestamps, change campaign rules, or publish anything.

## Current implementation status

Implemented in the current working change:

- `core/semantic_ranker.py`: optional Qwen GGUF ranker plus deterministic fallback;
- `modules/clipping/semantic_rank.py`: CLI wrapper;
- `run.py`: `semantic_rank` command;
- `worker/run_job.py`: semantic stage before render and rejection of incomplete semantic candidates;
- `requirements-semantic.txt`: optional `llama-cpp-python` and `huggingface-hub` dependencies;
- `.github/workflows/clipper-worker.yml`: CPU model install, Hugging Face cache, Q4_K_M download, and semantic environment variables;
- `modules/clipping/validate.py`: campaign-aware duration validation;
- `modules/clipping/render.py`: mandatory readable subtitles for normal renders; missing transcript is a hard quality failure unless `--no-subtitles` is explicitly used for troubleshooting;
- `core/production_policy.py`: campaign-bounded duration bands and deterministic hook/context/payoff/pacing/media ranking;
- `core/clip_candidates.py`: stronger boundary and payoff scoring plus production-policy enrichment;
- `worker/run_job.py`: searches multiple duration bands, deduplicates intervals, assigns global ranks, then runs semantic ranking and renders the best candidates;
- `tests/test_semantic_ranker.py`: fallback semantic regression tests and evaluation corpus execution.
- `tests/fixtures/semantic_cases.json`: evaluation corpus for complete, incomplete, short-cap, and mid-thought candidates.
- Review queue and dashboard now expose semantic decision, hook/context/payoff/completeness scores, and the model reason.
- `core/media_signals.py`: optional local FFmpeg/ffprobe signals for source quality, silence/voice activity, scene changes, duplicate hashes, sponsor/bumper hints, and transcript-label speaker framing.
- `worker/run_job.py`: source preflight now runs before Whisper, writes `source-preflight.json`, and excludes only sources with no usable video/audio or less than 1.5 seconds.
- `core/campaign_exclusions.py` and `worker/sync_campaigns.py`: deterministic gambling/money-game exclusions run before detail hydration and AI analysis. Matching campaigns are marked `blocked` with `EXCLUDED:GAMBLING_OR_MONEY_GAME` and are not eligible for the active list or auto-queue.
- `worker/run_job.py`: live campaign status is checked before asset intake; zero-candidate blocks now include counts for usable sources, transcription, raw candidates, semantic rejects, hard-policy rejects, and relevance blocks.
- `core/campaign_rules.py`: fetched `docs_text` is included in plan compilation and explicit clip/video duration ranges such as `15–60 seconds` are extracted when AI rules omit them. This fixes the Ryan Zofay baseline where a 5.419-second preview bypassed the document-only duration rule.
- `core/google_sheets.py`: generic Google Sheets asset resolver exports the tracker through Drive OAuth when available and falls back to public CSV export, extracts supported media URLs from tracker rows, preserves row metadata, and ranks tracker rows using Hype Level, Suggested Hook, and value.
- `core/google_drive.py`: existing Drive client can export Google Workspace files to supported MIME types, including Google Sheets CSV.
- `modules/reward_campaign/intake.py`: dereferences Google Sheet trackers before media discovery, carries tracker provenance into assets.json, reports tracker/discovery counts, and no longer marks unreadable Google Docs as successfully downloaded. Source selection no longer alphabetically discards the campaign tracker’s preferred rows.
- `tests/test_google_sheets.py`: regression coverage for Sheet detection, CSV parsing, media URL extraction, and tracker priority.
- `core/campaign_rules.py`: Google Docs/Sheets URLs found in campaign text are now retained as production asset references.
- `core/clip_candidates.py`, `modules/clipping/select.py`, and `worker/run_job.py`: stage contracts now carry selector diagnostics, bridge transcript units across pauses up to three seconds, gate impossible minimum-duration jobs before Whisper, and skip semantic ranking when the selector has no candidates.
- Exact duplicate sources are recorded with `duplicate_of` and skipped before transcription; the first source remains authoritative for processing.
- `core/clip_candidates.py`: silence and scene signals apply a bounded advisory score adjustment only; Whisper-derived `start` and `end` remain unchanged.
- `CLIPPER_MEDIA_SIGNAL_BUDGET_SECONDS` defaults to 8 seconds per candidate. If the optional FFmpeg probes exceed the budget, the remaining optional probe is skipped and metadata records `budget_exceeded`.
- `core/visual_crop.py` exposes `visual_speaker_signal()`, an optional OpenCV face-count heuristic. It is metadata-only for now: one stable face may recommend `speaker-focused`, two or uncertain faces recommend a wide frame, and unavailable/low-confidence detection always recommends `wide-unknown`.
- `scripts/benchmark_media_signals.py` creates a synthetic 24-second video/audio fixture and measures preflight plus candidate-signal runtime. The local baseline is 116.8 ms preflight and 494.7 ms signals, under the 8-second budget; local OpenCV absence correctly produces `wide-unknown`.
- Candidate, validation, and review artifacts now retain the media signal payload. Missing tools or source media produce explicit `available: false` metadata and do not stop deterministic clipping.
- `tests/fixtures/media_signal_cases.json` and `tests/test_media_signals.py`: regression coverage for two-speaker wide framing, dominant-speaker framing, unavailable sources, and source preflight measurements.
- `scripts/evaluate_semantic_fixture.py`: reproducible decision/risk accuracy report against the checked-in semantic corpus.
- `.github/workflows/semantic-fixture.yml`: manual Qwen verification path that does not dispatch or process a production job.

The pre-fix full suite was recorded at **80 tests**. The Google Sheets fix adds dedicated regression coverage; the next GitHub test run should verify the updated suite on main before a production retry. The first end-to-end trial's two official videos were technically healthy at 21.333 s and 20.833 s, 1080×1920, HEVC/AAC. The block was editorial: one candidate ended mid-thought and hit `unfinished_sentence`/`short_clip`; the second source yielded no complete candidate. The Ryan Zofay baseline also exposed a document-only duration rule that was previously missed; `compile_plan` now extracts it. The semantic fixture reports 4/4 decision matches and 4/4 expected-risk matches in deterministic mode. The isolated Qwen workflow loaded the GGUF and produced valid output for 4/4 cases, but matched only 3/4 decisions (75%) while covering 4/4 expected risks. `node --check web/app.js`, `node --check cloudflare/api.js`, Python compilation, and `git diff --check` also pass.

## Model and fallback policy

The worker uses `Qwen/Qwen2.5-1.5B-Instruct-GGUF`, Q4_K_M, through `llama-cpp-python` when the optional package and model are available. The model is Apache-2.0 according to its official Hugging Face card. If installation, model download, inference, or structured output validation fails, the worker falls back to deterministic ranking and continues. Because the Qwen fixture trails the deterministic baseline, Qwen remains advisory for ranking/review; local structural and campaign gates remain authoritative.

Relevant environment variables:

```text
CLIPPER_SEMANTIC_MODEL=/home/runner/.cache/clipper-semantic/qwen2.5-1.5b-instruct-q4_k_m.gguf
CLIPPER_SEMANTIC_ENABLED=auto
CLIPPER_SEMANTIC_THREADS=4
```

## Important behavior

- No candidate below the effective editorial/campaign floor should be forced into a preview.
- A candidate beginning mid-thought or ending unfinished is rejected before render.
- Campaign minimum and maximum duration rules override defaults.
- Subtitle rendering is mandatory for every normal production render when a transcript exists. It uses 42px bold outlined captions for 1080×1920 output. Only explicit `--no-subtitles` troubleshooting may bypass it.
- Renderer output remains H.264/AAC vertical preview, with face-aware crop when detection is available and deterministic center fallback otherwise.
- Human approval remains required. The system does not upload or submit to social platforms.

## Commands

```bash
python -m unittest discover -s tests -q
python run.py semantic_rank candidates.json --plan plan.json
python run.py select_clips transcript.json --plan plan.json
python run.py render_clips source.mp4 candidates.json --transcript transcript.json --plan plan.json
```

## GitHub Actions

`clipper-worker.yml` is manually dispatchable with a `job_id`; the current workflow file does not define a fifteen-minute schedule. It installs the base dependencies, installs the optional semantic dependency, caches Whisper and Qwen assets, downloads the Q4_K_M model, and runs `worker/run_job.py`. The worker is still CPU-oriented and may take longer on long sources.

Do not trigger a production job merely to test code when the known source is only a five-second incomplete excerpt. Use the local regression suite or a campaign with a source long enough to contain a complete moment.

## Next recommended work

The next agent must work in this order, not add more scoring features first: **P0 restore worker authentication and atomic job claiming; P1 persist durable stage telemetry and artifact manifests; P1 add a real end-to-end fixture with a known 15–30 second complete spoken moment; P1 make source/transcript/candidate diagnostics visible in the dashboard; P2 improve sparse-transcript candidate recovery and rule provenance; P2 only then evaluate visual speaker crop integration.** Qwen must remain advisory until its measured decision accuracy matches or exceeds the deterministic baseline.

## Guardrails

The engine must not bypass source permissions, remove required watermarks, use unapproved campaign material, fabricate engagement, publish automatically, or let a semantic model override explicit campaign rules. Any ambiguous mandatory rule stays in human review.


## Final deep audit — 22 September 2026

### Audit scope and evidence

This audit traced the complete path: campaign sync and exclusion, campaign plan compilation, Pages/D1 job creation, GitHub dispatch, scheduled worker drain, source intake, media preflight, Whisper transcription, candidate selection, semantic ranking, relevance checks, render, validation, R2 upload, preview persistence, and dashboard review. It used the repository at `57091ee`, live D1 schema inspection, live Pages project/deployment metadata, GitHub Actions runs `35726572125` and `35727302308`, and the Ryan Zofay and Shuffle trial rows.

The live production Pages project is `clipper-engine`, production branch `main`, with D1 database `ee8299d2-84e5-433b-b02f-553dcd4aea73` and R2 bucket `clipper-engine-previews`. Cloudflare production metadata currently includes `GITHUB_ACTIONS_TOKEN`, `WORKER_TOKEN`, `PREVIEW_SIGNING_SECRET`, and `REVIEW_TOKEN`; the latest production deployment was successful. The earlier `GITHUB_ACTIONS_TOKEN` error belongs to the older Ryan job `1285980a-d5f5-4896-b80b-600b143814cc`, created before the current deployment, and must not be treated as the current secret state.

### Verified end-to-end behavior

The intended contract is: the user selects an active, non-excluded campaign; the sync job snapshots campaign rules and official asset URLs; the Pages API creates a queued D1 job; a GitHub worker is dispatched or the scheduled drain picks a queued job; the worker fetches the live campaign status and plan, downloads official materials, performs preflight, transcribes, selects complete windows, optionally ranks them with Qwen, applies deterministic campaign/relevance gates, renders vertical H.264/AAC previews, validates them, uploads reviewable files to R2, inserts preview rows, and leaves publishing to a human.

The Ryan baseline exposed two independent defects. First, the old preview was 5.419 seconds even though the document said `Clip Length: 15–60 seconds`; `docs_text` was not included in plan compilation. Second, after the parser fix, the refreshed plan correctly stored `min_duration=15` and `max_duration=60`, but all three usable sources produced zero selector candidates. That second result was a legitimate quality block, not a Qwen failure: the worker log showed `raw_candidates=0`, and Qwen was subsequently changed to be skipped for empty selector input. The Shuffle trial similarly showed technically healthy official videos but an unfinished or incomplete spoken moment.

### P0 gaps — fix before more production trials

**P0.1 Worker authentication is disabled.** `cloudflare/api.js` currently has `workerAuthorized()` returning `true` with a temporary quality-first comment. That means an unauthenticated caller can reach worker-only sync, job patch, preview insertion, and R2 upload routes if the endpoint is known. Restore `x-worker-token` validation against `env.WORKER_TOKEN` before any external trial. Keep review authentication separate. Add negative API tests for missing and wrong worker tokens.

**P0.2 Job dispatch is not atomic.** The `/api/jobs/:id/run` route reads `status='queued'`, checks the message, calls GitHub, and only then writes a message. Two browser clicks, a scheduled drain, or a retry can dispatch the same job more than once. The repository architecture guidance explicitly requires an atomic claim. Add a dispatch lease/claim field or use an atomic `UPDATE jobs SET status='processing', message='dispatching' WHERE id=? AND status='queued'`, verify `changes===1`, dispatch exactly once, and transition to `processing` or back to `queued` with an error on dispatch failure. Add a GitHub Actions concurrency group keyed by `job_id`, not only one global `clipper-worker` group.

**P0.3 Worker claiming is also not atomic.** The scheduled worker can select one queued job while a manual worker is starting. The worker should atomically claim the row before downloading anything, with `claimed_at`, `claim_token`, and a stale-claim recovery policy. A worker must not process a job that is already `processing` under another claim.

### P1 gaps — fix before calling the engine production-quality

**P1.1 Stage telemetry is encoded in free-text messages.** D1 has only `status`, `progress`, `message`, and `error` for jobs. Candidate counts and source diagnostics are currently concatenated into an error string. Add a `job_runs` or `job_stage_events` table with `job_id`, `run_id`, `stage`, `status`, `started_at`, `ended_at`, `metrics_json`, `error_code`, and `error_detail`. Keep the small job state machine, but persist structured stage facts. This makes “asset succeeded, transcript existed, selector returned zero” visible without reading GitHub logs.

**P1.2 Intermediate artifacts are deleted after the worker exits.** `worker/run_job.py` removes its temporary root in `finally`. `source-preflight.json`, transcripts, selector diagnostics, semantic runtime, validation, and review manifests therefore disappear unless they are embedded in a preview row. For blocked jobs there is no durable evidence. Upload a compact `jobs/<job_id>/manifest.json` and relevant JSON artifacts to R2, and store the manifest key plus schema version in D1. Do not upload raw source media again; store hashes, URLs, sizes, durations, and derived metadata.

**P1.3 Preview validation contains ephemeral local paths.** Existing validation JSON includes paths such as `/tmp/clipper-job-.../outputs/clip-001.mp4`. Those paths are not useful after the worker exits and can mislead operators. Replace them with durable fields: `source_asset_id`, `artifact_key`, `rendered_duration`, `width`, `height`, codecs, and validation status. Keep local path only under a clearly named non-durable debug field if needed.

**P1.4 No true end-to-end fixture protects the contracts.** The 72-test suite is mainly unit coverage and the semantic corpus is synthetic. Add a checked-in small fixture with a known 20–30 second complete spoken moment, a matching campaign plan with explicit 15–30 second bounds, and expected outputs for intake metadata, transcript span, at least one candidate, semantic runtime, render duration, validation, and review manifest. Run it locally and in a non-production GitHub workflow. A green unit suite alone cannot catch a plan-string/object mismatch, missing asset handoff, wrong CLI argument, or R2/D1 field mismatch.

**P1.5 Job creation has a check-then-insert dedup race.** `/campaigns/:id/jobs` checks for an open job and then inserts. Two requests can create two queued jobs. Add a database-enforced strategy or an atomic transaction/claim pattern. At minimum, add a unique open-job key if the schema design permits it, or make the insert-and-reconcile path return the canonical job id deterministically.

**P1.6 R2 and D1 are not transactional.** The worker uploads video and thumbnail objects, then inserts preview rows. If D1 insertion fails, orphan R2 objects remain; if a retry inserts with `INSERT OR REPLACE`, review fields can be overwritten. Add a run id and idempotent object keys, insert/update preview rows with an explicit conflict policy, and run cleanup for unreferenced objects. Never use `OR REPLACE` for a record that can already have review state without preserving `review_reason`, `reviewed_by`, and `reviewed_at`.

### P2 quality gaps — address after reliability is fixed

**P2.1 Sparse Whisper transcripts are still the main quality bottleneck.** A 20-second source can yield only one or two Whisper segments. The selector now bridges pauses up to three seconds and writes diagnostics, but it still depends on timestamped speech units and can produce zero windows even when a human could make a usable clip. Add a controlled recovery path: use audio duration plus adjacent transcript units, allow a bounded context pad only when it does not cross long silence, and label the result `needs_human_boundary_review` rather than silently treating it as a confident candidate. Do not lower campaign minimums.

**P2.2 Rule extraction needs provenance.** `compile_plan` now parses duration ranges from `docs_text`, but the plan does not say which document sentence produced `min_duration_seconds` and `max_duration_seconds`. Store `rule_evidence` with source field, quote, parser version, and confidence. If AI and deterministic extraction disagree, preserve both and route the plan to human review rather than silently preferring one.

**P2.3 Candidate selection should expose near misses.** A zero-candidate result should retain the best rejected windows with rejection reasons, not only `candidate_count=0`. Store up to three bounded near misses with start/end, duration, transcript text, and failed reasons. This lets a reviewer distinguish “no speech,” “speech too sparse,” “unfinished boundary,” and “campaign minimum too high.”

**P2.4 Qwen is not a quality authority.** The isolated Qwen fixture produced valid output for 4/4 cases but only 3/4 decision matches, while deterministic mode matched 4/4. Qwen can rank or add advisory reasons; it must not override explicit rules, timestamps, duration gates, gambling exclusions, or local structural safety. Keep model, fallback reason, prompt/schema version, and result validation in the manifest.

**P2.5 Visual speaker heuristics are not ready to control crop.** The OpenCV heuristic is metadata-only and correctly falls back to a wide frame when unavailable or uncertain. Do not make it choose a crop until a dependency-complete two-face fixture measures false framing and confidence stability.

### P3 operational and maintainability gaps

The handoff and status files previously contained stale commit references; always verify `git log`, live deployment commit, and D1 freshness independently. The Pages project has production secrets, but an old queued job can retain an old error forever; the dashboard should distinguish historical dispatch error from current runtime configuration. The API uses a wildcard CORS policy and worker auth is currently disabled; review whether that is acceptable after authentication is restored. The workflow has a static cache key (`whisper-and-qwen-semantic-v1`); bump it when model or prompt/schema changes. Gemini sync logs showed transient 429/503 failures while the workflow still completed; campaign sync must persist per-campaign analysis freshness, fallback reason, and model version rather than treating a green workflow as proof that every campaign was freshly analyzed.

### Exact operating procedure for the next agent

1. Read this handoff, `STATUS.md`, `AGENTS.md`, and the clipping skill before editing.
2. Confirm the repository head, live Pages production deployment commit, and live D1 schema. Never infer live state from a migration file or an old job row.
3. Do not start another paid/expensive production trial until the local end-to-end fixture passes from plan to review manifest.
4. First implement P0 authentication and atomic claim/dispatch. Add tests that simulate duplicate dispatch and stale workers.
5. Then implement structured stage telemetry and durable manifest storage. A blocked job must still have enough evidence to explain the exact first empty stage.
6. Then implement the known-good 20–30 second fixture and run it in a non-production workflow. Verify D1 changes and R2 artifact existence, not merely a green Actions badge.
7. Only after those checks should a real campaign trial be started. Record the job id, run id, source hashes, plan hash, stage metrics, preview keys, validation status, and reviewer outcome.
8. Never weaken campaign minimums to force a preview. Never allow Qwen or a fallback to override hard policy. Never publish automatically. Never remove gambling/money-game exclusions.

### Last known trial records

| Trial | Job ID | Result | Evidence |
|---|---|---|---|
| Shuffle Streamers | `7b0813da-a653-43e1-a9b4-5d1feccf2e17` | blocked | healthy official videos; incomplete/unfinished candidate; old message predates structured counters |
| Ryan old baseline | `3331ecfe-4e12-4539-8423-976a2036dcce` | review | one preview, but 5.419 s and therefore violated the document's 15–60 s rule |
| Ryan after parser fix, stale plan | `1285980a-d5f5-4896-b80b-600b143814cc` | queued | historical dispatch-secret error; do not use as current secret evidence |
| Ryan after refreshed plan | `bc416fcd-199b-4f41-b054-c21cd477ff26` | blocked | 3 usable sources, 3 transcribed, 0 raw candidates; Qwen skipped after selector-empty hardening |

The current goal is not “make every campaign produce a preview.” The goal is **make every campaign outcome correct, explainable, cheap to evaluate, and safe to review**.


## P0 reliability implementation — completed 22 September 2026

The first reliability slice is now implemented and tested. `workerAuthorized()` validates `x-worker-token` or `Authorization: Bearer` against `env.WORKER_TOKEN`; missing configuration fails closed. The API self-healing schema now adds `jobs.dispatch_token`, `jobs.claimed_at`, and `jobs.claimed_by`, plus an index on `(status, claimed_at)`. The checked-in `cloudflare/schema.sql` matches these fields.

Manual `/api/jobs/:id/run` dispatch now performs an atomic update that writes a random dispatch token only when the job is still `queued` and has no existing dispatch token. A second caller receives `409 job_already_dispatched`. GitHub workflow input `dispatch_token` carries this internal claim token to the worker. If GitHub dispatch fails, the token is cleared only by the caller that owns it, allowing a controlled retry.

Every worker calls authenticated `/api/jobs/:id/claim` before downloading or transcribing. The API atomically changes `queued` to `processing`, stores claim timestamp/owner, and accepts either a matching dispatch token or a fresh scheduled-run token. A losing runner receives `409 job_claim_lost` and exits without consuming Whisper/Qwen/render credits. The worker helper `claim_job()` has regression coverage for success, duplicate-claim no-op, and unexpected server-error propagation.

Verification after this slice: **75 tests pass**, Python compilation/compileall pass, `node --check cloudflare/api.js` and `node --check web/app.js` pass, `pip check` reports no broken requirements, and `git diff --check` passes. This does not yet solve the job-creation check-then-insert race, stale claim recovery, structured stage telemetry, or durable manifest storage; those remain the next P1 items. Do not claim the entire reliability program is complete merely because P0 dispatch/claim is implemented.

Operational requirement: the GitHub Actions secret `CLIPPER_WORKER_TOKEN` must equal the Cloudflare Pages Production secret `WORKER_TOKEN`. The production API also needs `GITHUB_ACTIONS_TOKEN` for manual dispatch. Never put either secret value in logs or documentation. Scheduled workers use an ephemeral claim token when no dispatch token exists.


## Session handoff — 23 September 2026: Google Sheets tracker fix and connector limitation

### Verified implementation state

The Backyard Breaks failure was traced to a generic asset-discovery gap, not a campaign-specific failure. The campaign uses a Google Sheet named **Backyard Breaks – Clip Context Tracker** as the source of truth for clip links and context. The sheet contains direct Google Drive media URLs plus metadata such as Hype Level, Suggested Hook, card value, and rarity. The previous intake implementation handled Google Docs but did not dereference Google Sheets, so the worker could download the reference documents while still reporting `video_sources: 0`.

The generic fix is now implemented:

- `core/google_sheets.py` detects Google Sheets, exports CSV through Drive OAuth when available, falls back to public CSV export, parses rows, extracts supported media URLs, preserves row metadata, and ranks candidates using Hype Level, Suggested Hook, and numeric value.
- `core/google_drive.py` supports Google Workspace file export.
- `modules/reward_campaign/intake.py` dereferences Sheet trackers, stores tracker rows, carries provenance into `assets.json`, reports tracker/discovery/selection counts, and selects media by tracker priority rather than alphabetical URL order.
- Google Docs behavior remains intact.
- The fix is campaign-generic. Do not add a Backyard-specific URL list or campaign-id special case.
- Current resolver limitation: CSV export covers the first Sheet tab. Multi-tab Sheets API range traversal remains future hardening.

### Verification evidence

Current `main` head is `186f93814608087c87beb78e34bb6d6725bcdcdf`.

GitHub Actions run `35882633238` completed successfully:

```
Ran 84 tests in 7.091s
OK

semantic fixture:
case_count=4
decision_matches=4
risk_matches=4
decision_accuracy=1.0
risk_coverage=1.0
```

For commit `186f938...`, both the test check and the Cloudflare Pages check completed successfully. The Cloudflare Pages check reports a successful deployment of project `clipper-engine` for commit `186f938...`, with preview deployment `https://e32ee1e6.clipper-engine.pages.dev`. This verifies the Pages deployment pipeline, but the preview URL was not independently rendered through the web reader.

### Production smoke-test status

The known failed Backyard job is:

- Job: `0ca3b531-a506-4e51-80f2-ad2e92180641`
- Previous worker run: `clipper-worker #45`
- Run ID: `35863583776`
- Previous failure: `records: 4 | downloaded: 4 | failed: 0 | video_sources: 0`, followed by `tidak ada video asset langsung`.

The code fix is **not yet considered production-verified** until this worker is run again and the intake log proves tracker dereference and media discovery, ideally showing non-zero `tracker_rows`, `discovered_media_sources`, `selected_media_sources`, and `video_sources`.

Important operational distinction: `clipper-worker.yml` is manually dispatchable. A code push does not automatically execute the known production job. Do not mark the Backyard fix as end-to-end successful from CI/Pages success alone.

### Cloudflare connector limitation in the current ChatGPT session

On 23 September 2026, a direct attempt to execute the Cloudflare developer MCP connector was rejected by the ChatGPT runtime with:

`FORBIDDEN: This conversation does not support developer MCPs`.

This is a **conversation/runtime capability limitation**, not evidence that the user's Cloudflare account or token lacks permission. Do not claim direct Cloudflare API access from this session. Available evidence can still include GitHub Actions Cloudflare Pages check-runs and repository configuration, but that is not equivalent to unrestricted Cloudflare API access.

A replacement agent should first test whether its session actually supports the Cloudflare developer MCP. If supported, verify directly:

1. Pages project `clipper-engine`, production branch `main`, latest deployment commit/status.
2. D1 database `ee8299d2-84e5-433b-b02f-553dcd4aea73`.
3. R2 bucket `clipper-engine-previews`.
4. Production Worker/Pages environment bindings and required secret presence, without exposing secret values.
5. Production D1 job `0ca3b531-a506-4e51-80f2-ad2e92180641`.
6. Then run/trigger the manual worker smoke test if the available GitHub connector supports workflow dispatch.

Never infer Cloudflare runtime state solely from an old deployment, an old job row, or a migration file.

### Exact next action for replacement agent

Do not restart the project audit. Continue from commit `186f938...`.

1. Verify current GitHub main head and latest checks.
2. Verify direct Cloudflare MCP access. If available, inspect live Pages/D1/R2 state.
3. Locate the worker workflow and determine whether workflow dispatch is writable through the GitHub connector.
4. Run the known Backyard production job only after confirming the current code is deployed.
5. Inspect the worker run logs and artifacts for Sheet discovery metrics.
6. If asset discovery succeeds but the worker then fails on Drive permissions, diagnose the specific source permission/download path next. Do not revert the generic Sheet resolver.
7. If the worker reaches Whisper/selection, continue through render/validation and record the exact first failing stage.
8. Update this handoff with the actual smoke-test evidence. Do not call the fix production-complete before that evidence exists.

The target outcome is not merely “a preview exists.” The target is a traceable chain: **campaign tracker → tracker rows → selected media source → downloaded media → transcription → candidate → render → validation → durable review artifact**.
