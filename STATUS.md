# Scrapper Engine Status

**Updated:** 22 September 2026
**Branch:** `main`

## Current milestone

The campaign-aware clipping pipeline is operational through manual review. It supports campaign radar/detail hydration, rules compilation, isolated material intake, Google Drive/YouTube/direct media sources, faster-whisper transcription, deterministic candidate selection, optional local subtitle semantic ranking, FFmpeg vertical rendering, face-aware crop, campaign-aware validation, review queue generation, and Cloudflare Pages/D1/R2 preview delivery.

The current quality path is:

```text
campaign plan -> official assets -> Whisper word timestamps -> candidate windows
-> Qwen subtitle semantic ranker when available -> rules/relevance gates
-> vertical render -> technical/editorial validation -> manual review
```

The optional semantic model is Qwen2.5-1.5B-Instruct-GGUF Q4_K_M through `llama-cpp-python`. If the model or dependency is unavailable, the deterministic fallback in `core/semantic_ranker.py` keeps the worker running.

Candidate generation now groups Whisper words into sentence/turn units using punctuation and pauses before building windows. Source preflight runs before Whisper and records duration, video/audio presence, resolution, duplicate hash, and exclusion reasons in `source-preflight.json`. Exact duplicate sources are retained in provenance but only the first is transcribed. Optional local media signals record speech density, sponsor/bumper hints, candidate silence/voice activity, FFmpeg scene changes, transcript speaker-label framing advice, and an OpenCV face-count framing hint. Silence/scene signals apply only a bounded ranking adjustment with `CLIPPER_MEDIA_SIGNAL_BUDGET_SECONDS` protection; visual speaker confidence is advisory and low confidence always recommends a wide frame. These signals never change timestamps or campaign rules. `tests/fixtures/semantic_cases.json` and `tests/fixtures/media_signal_cases.json` provide regression corpora.

Daily campaign sync now applies `core/campaign_exclusions.py` before detail hydration and AI analysis. Campaigns matching explicit gambling, casino, poker, betting, real-money gaming, deposit-match, RTP, or known-operator terms are marked `blocked`, flagged `EXCLUDED:GAMBLING_OR_MONEY_GAME`, and never enter the active campaign list or auto-queue.

The first end-to-end trial was audited against the exact source URLs. Both official videos were healthy vertical assets (21.333 s and 20.833 s, 1080×1920, HEVC video plus AAC audio). The block was editorial: one source produced a 9.44-second candidate ending mid-thought and hit deterministic `unfinished_sentence`/`short_clip` gates; the other produced no complete candidate from its transcript. The worker now checks live campaign status before downloading assets and records source/transcription/raw-candidate/semantic/hard-policy/relevance counts in zero-candidate errors instead of emitting a generic duration message.

The Ryan Zofay baseline exposed a separate rule-compilation bug: its prior 5.419-second preview passed because the campaign's `Clip Length: 15–60 seconds` instruction existed only in fetched `docs_text`, which was not included in `compile_plan`. The compiler now includes fetched document text and extracts explicit duration ranges, so the campaign minimum and maximum reach `plan.json` and validation.

The next integration hardening keeps stage contracts explicit: a cheap asset-duration gate runs before Whisper when a campaign has a minimum duration; selector artifacts include transcript span, unit count, bounds, pause budget, and an empty-result reason; short transcript pauses up to three seconds may be bridged without crossing long silence; and semantic ranking is skipped when selection returns no candidates. This prevents avoidable Qwen calls and makes a blocked job explain which stage produced zero output.

## Rules and quality behavior

- `plan.json` and `source_of_truth` are authoritative.
- Campaign duration bounds override defaults.
- Without campaign bounds, the default editorial floor is 8 seconds and the ceiling is 60 seconds.
- Mid-thought, unfinished, and structurally incomplete candidates are rejected before rendering.
- Subtitle rendering follows `production.subtitle_required` rather than a global default.
- Human approval and manual posting remain mandatory; auto-publish is disabled.

## Verification

The repository regression suite passes **72 tests**. The deterministic golden fixture reports **100% decision accuracy and 100% expected-risk coverage** across four cases. Required checks also pass: `node --check web/app.js`, `node --check cloudflare/api.js`, `python3 -m py_compile ...`, and `git diff --check`.

The actual Qwen GGUF path was verified by the isolated manual `semantic-fixture.yml` workflow on run `35718164052`. The model loaded and produced valid structured output for all four cases, with **3/4 decision accuracy (75%)** and **4/4 risk coverage**. The deterministic baseline remains **4/4 (100%)**. Therefore Qwen remains advisory for ranking/review; deterministic gates and fallback remain authoritative. The workflow does not touch production.

`scripts/benchmark_media_signals.py` runs a synthetic 24-second source with video and audio. The current local baseline is **116.8 ms preflight** and **494.7 ms for candidate signals**, with the 8-second budget not exceeded and the candidate interval unchanged at `2.0–18.0`. The sandbox lacks OpenCV, so the visual result is correctly recorded as `wide-unknown`; this benchmark measures runtime and safety invariants, not speaker-detection accuracy.

## Next milestone

The final deep audit is recorded in `docs/AGENT_HANDOFF.md`. Do not start another expensive production trial yet. The required order is: restore worker authentication; implement atomic dispatch/worker claims; persist structured stage telemetry and durable manifests; add a known-good non-production end-to-end fixture; expose near-miss diagnostics; then improve sparse-transcript recovery. Keep Qwen advisory and visual speaker detection metadata-only until measured fixtures justify promotion.

P0 reliability slice completed after the audit: worker-token authentication now fails closed; manual dispatch has an atomic `dispatch_token` claim; every worker atomically claims a queued job before asset intake; and 75 regression tests pass. P1 reliability now adds a partial unique index for one queued/processing job per campaign, runner identity on claims, a 1-hour bounded lease, authenticated stale-claim recovery, structured D1 stage events, and a sanitized durable R2 manifest with preview artifact keys. Remaining P1 work is a known-good non-production end-to-end fixture and live manual trial verification.

Production diagnosis on 22 September 2026 found that the Pages project lists `GITHUB_ACTIONS_TOKEN`, but the active Function runtime resolves `env.GITHUB_ACTIONS_TOKEN` as empty. Manual dispatch therefore now degrades safely to the queued scheduler path instead of marking a new campaign as API 503; the worker schedule runs every five minutes. This prevents a Pages secret propagation mismatch from becoming a user-visible pipeline failure.

## Documentation entry points

- `docs/AGENT_HANDOFF.md` — current implementation and operating instructions.
- `docs/SEMANTIC_CLIPPING_LOCAL.md` — semantic ranker design, model, fallback, and configuration.
- `docs/google-drive-integration.md` — Drive OAuth and campaign asset intake.
- `cloudflare/PHONE_ONLY_ARCHITECTURE.md` — phone-only operating model.
- `cloudflare/FREE_COST_POLICY.md` — free-tier limits and storage policy.

Historical design notes and superseded trial/research reports are under `docs/archive/2026-09-22/`.
