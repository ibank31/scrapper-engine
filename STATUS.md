# Scrapper Engine Status

**Updated:** 24 September 2026 — Phase 0 provenance and execution fencing implementation
**Branch:** `main`

## Current milestone

The campaign-aware clipping pipeline is operational through manual review. It supports campaign radar/detail hydration, rules compilation, isolated material intake, Google Drive/YouTube/direct media sources, faster-whisper transcription, deterministic candidate selection, optional local subtitle semantic ranking, FFmpeg vertical rendering, face-aware crop, campaign-aware validation, review queue generation, and Cloudflare Pages/D1/R2 preview delivery.

The current quality path is:

```text
campaign plan -> official assets -> Whisper word timestamps
-> multi-band candidate windows (compact/dialogue/story)
-> deterministic hook/context/payoff/pacing policy
-> Qwen subtitle semantic ranker when available -> rules/relevance gates
-> mandatory readable subtitles -> vertical render -> technical/editorial validation -> manual review
```

The optional semantic model is Qwen2.5-1.5B-Instruct-GGUF Q4_K_M through `llama-cpp-python`. If the model or dependency is unavailable, the deterministic fallback in `core/semantic_ranker.py` keeps the worker running.

Candidate generation now groups Whisper words into sentence/turn units using punctuation and pauses before building windows. Source preflight runs before Whisper and records duration, video/audio presence, resolution, duplicate hash, and exclusion reasons in `source-preflight.json`. Exact duplicate sources are retained in provenance but only the first is transcribed. Optional local media signals record speech density, sponsor/bumper hints, candidate silence/voice activity, FFmpeg scene changes, transcript speaker-label framing advice, and an OpenCV face-count framing hint. Silence/scene signals apply only a bounded ranking adjustment with `CLIPPER_MEDIA_SIGNAL_BUDGET_SECONDS` protection; visual speaker confidence is advisory and low confidence always recommends a wide frame. These signals never change timestamps or campaign rules. `tests/fixtures/semantic_cases.json` and `tests/fixtures/media_signal_cases.json` provide regression corpora.

Daily campaign sync now applies `core/campaign_exclusions.py` before detail hydration and AI analysis. Campaigns matching explicit gambling, casino, poker, betting, real-money gaming, deposit-match, RTP, or known-operator terms are marked `blocked`, flagged `EXCLUDED:GAMBLING_OR_MONEY_GAME`, and never enter the active campaign list or auto-queue.

The first end-to-end trial was audited against the exact source URLs. Both official videos were healthy vertical assets (21.333 s and 20.833 s, 1080×1920, HEVC video plus AAC audio). The block was editorial: one source produced a 9.44-second candidate ending mid-thought and hit deterministic `unfinished_sentence`/`short_clip` gates; the other produced no complete candidate from its transcript. The worker now checks live campaign status before downloading assets and records source/transcription/raw-candidate/semantic/hard-policy/relevance counts in zero-candidate errors instead of emitting a generic duration message.

The Ryan Zofay baseline exposed a separate rule-compilation bug: its prior 5.419-second preview passed because the campaign's `Clip Length: 15–60 seconds` instruction existed only in fetched `docs_text`, which was not included in `compile_plan`. The compiler now includes fetched document text and extracts explicit duration ranges, so the campaign minimum and maximum reach `plan.json` and validation.

Campaign asset intake now resolves Google Sheets trackers before source download. A tracker row can contain the actual Drive/YouTube/media URL plus campaign metadata such as Hype Level and Suggested Hook; the resolver preserves that metadata, ranks tracker candidates before the worker source cap, and records discovery counts in assets.json. Google Sheets are exported through the existing Drive OAuth path when available, with a public CSV fallback. Google Docs and Sheets references discovered inside campaign text are retained as asset references.

The next integration hardening keeps stage contracts explicit: a cheap asset-duration gate runs before Whisper when a campaign has a minimum duration; selector artifacts include transcript span, unit count, bounds, pause budget, and an empty-result reason; short transcript pauses up to three seconds may be bridged without crossing long silence; and semantic ranking is skipped when selection returns no candidates. This prevents avoidable Qwen calls and makes a blocked job explain which stage produced zero output.

## Rules and quality behavior

- `plan.json` and `source_of_truth` are authoritative.
- Campaign duration bounds override defaults.
- Without campaign bounds, the default editorial floor is 8 seconds and the ceiling is 60 seconds.
- Mid-thought, unfinished, and structurally incomplete candidates are rejected before rendering.
- Subtitle rendering is mandatory for every normal production render when a transcript exists; `--no-subtitles` is reserved for explicit troubleshooting.
- Human approval and manual posting remain mandatory; auto-publish is disabled.

## Verification

The repository regression suite passes **84 tests**. GitHub Actions run `35882633238` completed successfully: `Ran 84 tests in 7.091s`, `OK`. The deterministic semantic fixture reports `4/4` decision matches and `4/4` expected-risk matches (`decision_accuracy=1.0`, `risk_coverage=1.0`). The same run passed the Node syntax checks and semantic fixture workflow steps.

The actual Qwen GGUF path was verified by the isolated manual `semantic-fixture.yml` workflow on run `35718164052`. The model loaded and produced valid structured output for all four cases, with **3/4 decision accuracy (75%)** and **4/4 risk coverage**. The deterministic baseline remains **4/4 (100%)**. Therefore Qwen remains advisory for ranking/review; deterministic gates and fallback remain authoritative. The workflow does not touch production.

`scripts/benchmark_media_signals.py` runs a synthetic 24-second source with video and audio. The current local baseline is **116.8 ms preflight** and **494.7 ms for candidate signals**, with the 8-second budget not exceeded and the candidate interval unchanged at `2.0–18.0`. The sandbox lacks OpenCV, so the visual result is correctly recorded as `wide-unknown`; this benchmark measures runtime and safety invariants, not speaker-detection accuracy.

## Phase 0 safety boundary — implemented locally

Jobs now capture an immutable plan snapshot, canonical rules hash, source fingerprint, schema version, and execution generation at creation. Workers use only that snapshot and block legacy jobs without provenance as `blocked_needs_requeue`. Document text and source URLs participate in AI fingerprints and prompt input. Review approval requires review authorization and binds the exact artifact and caption revision to the job rules hash; Buffer rejects pending or mismatched revisions. Worker stage, manifest, preview, upload, and status writes are fenced by claim token, run ID, and execution generation; cancellation increments the generation and clears the active token. The checked-in D1 schema and self-healing migration include the new fields. Local verification passes 88 tests, Python compilation/compileall, pip check, both Node syntax checks, diff check, and secret scan. Production deployment/migration is intentionally not claimed until the Pages/D1 deployment is run.

## Next milestone

The remaining implementation is now split into bounded agent slices in `docs/IMPLEMENTATION_ROADMAP.md`. The next task is **P1-A — output contract foundation**: add the versioned two-output contract and pure validation tests only. Each subsequent session must execute one slice, pass its acceptance gate, report the next slice ID, and stop. No production deployment, Buffer mutation, publication, or expensive trial is part of the Phase 1 foundation work.

Phase 0 provenance, approval, and stale-write fencing is implemented in commit `0b6e019` and verified by GitHub Actions run `35985728295` with 88 tests passing. The old P1/P2/P3 labels in historical notes are retained for audit context; the actionable sequence is now P1-A through P5-C in the implementation roadmap. The next agent must not combine slices or treat a green unit suite as proof of end-to-end readiness.

Production diagnosis on 22 September 2026 found that the Pages project lists `GITHUB_ACTIONS_TOKEN`, but the active Function runtime resolved `env.GITHUB_ACTIONS_TOKEN` as empty in an older deployment. The current production deployment `e4b739ea` has the required secret names configured and successfully dispatched the manual worker. Clipping remains intentionally **manual-only** through the homepage; only `campaign-sync-ai.yml` runs daily at 00:00 WIB.

## Latest quality implementation — 23 September 2026

The quality-first production changes are in commits `4748e12`, `024c867`, and `3887172`. The Google Sheets asset-intake fix is implemented in `9a9ba780`; the intake helper compatibility repair is `d22dfb36c3da3fe50636fe768329392dc1309b74`; documentation was updated in `50651193c1ba8113638442e8c7ed77f0a263a703` and `186f93814608087c87beb78e34bb6d6725bcdcdf`. The selector now searches multiple editorial duration bands, removes duplicate intervals, and ranks candidates using opening hook, context, payoff timing, completed ending, speech activity, and multi-speaker framing signals. Campaign minimum and maximum duration rules remain authoritative. The renderer uses larger outlined subtitles by default and fails normal rendering when a transcript is absent, so every production preview is captioned. The Cloudflare Pages production deployment was last verified for the prior quality commit `3887172`. For commit `186f938...`, the GitHub Cloudflare Pages check completed successfully and reported deployment success for project `clipper-engine`; preview deployment `https://e32ee1e6.clipper-engine.pages.dev`. This verifies the Pages deployment pipeline. It does not replace a worker production smoke test.

## Documentation entry points

- `docs/AGENT_HANDOFF.md` — current implementation and operating instructions.
- `docs/SEMANTIC_CLIPPING_LOCAL.md` — semantic ranker design, model, fallback, and configuration.
- `docs/google-drive-integration.md` — Drive OAuth and campaign asset intake.
- `cloudflare/PHONE_ONLY_ARCHITECTURE.md` — phone-only operating model.
- `cloudflare/FREE_COST_POLICY.md` — free-tier limits and storage policy.

Historical design notes and superseded trial/research reports are under `docs/archive/2026-09-22/`.


## 23 September 2026 — latest production verification

The known Backyard Breaks production failure was caused by a generic Google Sheets asset-discovery gap. The campaign's Clip Context Tracker contains direct Drive media URLs and row metadata, while the old intake resolver only expanded Google Docs. The generic Sheet resolver is now verified in production.

Live Cloudflare verification confirmed project `clipper-engine`, production branch `main`, Pages deployment `e4b739ea-01ce-460f-a3ee-ce594eaf13a6`, commit `592742ed9dc72651167de21566dfe1242f32faee`, successful Pages stages, D1 `ee8299d2-84e5-433b-b02f-553dcd4aea73`, R2 `clipper-engine-previews`, and production bindings for `DB`, `CLIPS`, and the required secret names. Secret values were not exposed.

The production smoke test for job `0ca3b531-a506-4e51-80f2-ad2e92180641` ran in GitHub Actions run `35888149181` and completed successfully. The worker log proved `records: 6 | downloaded: 6 | failed: 0 | tracker_rows: 60 | media_sources: 56 | selected: 1 | video_sources: 1`. The full trace was successful: campaign rules, asset intake, source preflight (`source_count=1`, `usable_sources=1`), Whisper transcription (`transcribed=1`), selector (`candidate_count=5`), semantic/rules gates (`semantic_rejects=0`, `hard_policy_rejects=0`, `relevance_blocks=0`), render (`rendered_count=2`), validation (`2/2` technical passes), R2 upload (`preview_count=2`), and manual-review record creation.

The job is now `review` at 100% with two `pending_review` previews. R2 contains the two MP4 artifacts, two review MP4s, two thumbnails, and `jobs/0ca3b531-a506-4e51-80f2-ad2e92180641/manifest.json`; D1 contains the corresponding two review records. Auto-publish remains disabled. Both previews are marked `needs_review` because campaign relevance is uncertain and human verification of third-party watermark/relevance remains required.

Operational note: the D1 job row retains the historical `run_id` `35863583776` because the current update uses `COALESCE`; the stage-event rows and `claimed_by` correctly identify the successful run `35888149181`. This metadata issue does not invalidate the completed smoke test, but should be corrected in a future telemetry-focused change rather than by changing campaign behavior.
