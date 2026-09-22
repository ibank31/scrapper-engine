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

## Rules and quality behavior

- `plan.json` and `source_of_truth` are authoritative.
- Campaign duration bounds override defaults.
- Without campaign bounds, the default editorial floor is 8 seconds and the ceiling is 60 seconds.
- Mid-thought, unfinished, and structurally incomplete candidates are rejected before rendering.
- Subtitle rendering follows `production.subtitle_required` rather than a global default.
- Human approval and manual posting remain mandatory; auto-publish is disabled.

## Verification

The repository regression suite passes **70 tests**. The deterministic golden fixture reports **100% decision accuracy and 100% expected-risk coverage** across four cases. Required checks also pass: `node --check web/app.js`, `node --check cloudflare/api.js`, `python3 -m py_compile ...`, and `git diff --check`.

The actual Qwen GGUF path was verified by the isolated manual `semantic-fixture.yml` workflow on run `35718164052`. The model loaded and produced valid structured output for all four cases, with **3/4 decision accuracy (75%)** and **4/4 risk coverage**. The deterministic baseline remains **4/4 (100%)**. Therefore Qwen remains advisory for ranking/review; deterministic gates and fallback remain authoritative. The workflow does not touch production.

`scripts/benchmark_media_signals.py` runs a synthetic 24-second source with video and audio. The current local baseline is **116.8 ms preflight** and **494.7 ms for candidate signals**, with the 8-second budget not exceeded and the candidate interval unchanged at `2.0–18.0`. The sandbox lacks OpenCV, so the visual result is correctly recorded as `wide-unknown`; this benchmark measures runtime and safety invariants, not speaker-detection accuracy.

## Next milestone

Next, run the same benchmark in the dependency-complete GitHub environment and add a controlled two-face fixture before considering any crop integration. Keep the visual heuristic metadata-only until fixture results show stable face-count confidence. Keep Qwen advisory while it trails deterministic baseline. Do not use a five-second incomplete source as a quality benchmark.

## Documentation entry points

- `docs/AGENT_HANDOFF.md` — current implementation and operating instructions.
- `docs/SEMANTIC_CLIPPING_LOCAL.md` — semantic ranker design, model, fallback, and configuration.
- `docs/google-drive-integration.md` — Drive OAuth and campaign asset intake.
- `cloudflare/PHONE_ONLY_ARCHITECTURE.md` — phone-only operating model.
- `cloudflare/FREE_COST_POLICY.md` — free-tier limits and storage policy.

Historical design notes and superseded trial/research reports are under `docs/archive/2026-09-22/`.
