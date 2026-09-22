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

Candidate generation now groups Whisper words into sentence/turn units using punctuation and pauses before building windows. Optional local media signals now record source duration, audio presence, speech density, resolution, duplicate hash, sponsor/bumper hints, candidate silence/voice activity, FFmpeg scene changes, and transcript speaker-label framing advice. Signals are advisory and are carried into validation and the review manifest without changing Whisper timestamps or campaign rules. `tests/fixtures/semantic_cases.json` and `tests/fixtures/media_signal_cases.json` provide regression corpora.

## Rules and quality behavior

- `plan.json` and `source_of_truth` are authoritative.
- Campaign duration bounds override defaults.
- Without campaign bounds, the default editorial floor is 8 seconds and the ceiling is 60 seconds.
- Mid-thought, unfinished, and structurally incomplete candidates are rejected before rendering.
- Subtitle rendering follows `production.subtitle_required` rather than a global default.
- Human approval and manual posting remain mandatory; auto-publish is disabled.

## Verification

The repository regression suite passes **56 tests**. The latest media-signal implementation is committed in `00648bc`; the sentence-aware quality loop is in `3f4fd58`, and the semantic ranker/workflow foundation is in `18246e9`. Required checks also pass: `node --check web/app.js`, `node --check cloudflare/api.js`, `python3 -m py_compile ...`, and `git diff --check`.

The actual Qwen GGUF path was **not run in this local sandbox or against a production job**. GitHub Actions remains configured to install and load it on a sufficiently long controlled source. Local tests exercise the deterministic fallback and verify that unavailable optional signals remain explicit rather than silently passing.

## Next milestone

Run one controlled end-to-end GitHub Actions job using a sufficiently long approved source, confirm Qwen load/inference diagnostics, and inspect media/semantic metadata in the review queue. Improve active-speaker detection with visual evidence when an optional vision dependency is available; current framing advice is transcript-label based. Do not use a five-second incomplete source as a quality benchmark.

## Documentation entry points

- `docs/AGENT_HANDOFF.md` — current implementation and operating instructions.
- `docs/SEMANTIC_CLIPPING_LOCAL.md` — semantic ranker design, model, fallback, and configuration.
- `docs/google-drive-integration.md` — Drive OAuth and campaign asset intake.
- `cloudflare/PHONE_ONLY_ARCHITECTURE.md` — phone-only operating model.
- `cloudflare/FREE_COST_POLICY.md` — free-tier limits and storage policy.

Historical design notes and superseded trial/research reports are under `docs/archive/2026-09-22/`.
