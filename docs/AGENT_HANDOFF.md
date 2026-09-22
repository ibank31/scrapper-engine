# Scrapper Engine — Current Agent Handoff

**Updated:** 22 September 2026
**Repository:** `ibank31/scrapper-engine`
**Production branch:** `main`
**Latest implementation commit:** `c36e535` — semantic golden evaluation harness, explicit engine/fallback diagnostics, and a manual non-production Qwen fixture workflow.

## Product contract

The system starts from a campaign selected by the user. It reads and snapshots the campaign rules, downloads only official campaign materials, transcribes the source, finds complete moments, renders vertical previews, validates the result against the campaign plan, and puts only reviewable previews into the dashboard. Posting remains manual. `plan.json` and its `source_of_truth` fields are authoritative.

## Current pipeline

```text
campaign selection
  -> campaign detail and plan compiler
  -> official Drive/YouTube/direct asset intake
  -> faster-whisper word timestamps
  -> sentence/turn candidate windows
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
- `modules/clipping/render.py`: subtitle output only when required by the campaign or explicitly forced;
- `core/clip_candidates.py`: stronger boundary and payoff scoring;
- `tests/test_semantic_ranker.py`: fallback semantic regression tests and evaluation corpus execution.
- `tests/fixtures/semantic_cases.json`: evaluation corpus for complete, incomplete, short-cap, and mid-thought candidates.
- Review queue and dashboard now expose semantic decision, hook/context/payoff/completeness scores, and the model reason.
- `core/media_signals.py`: optional local FFmpeg/ffprobe signals for source quality, silence/voice activity, scene changes, duplicate hashes, sponsor/bumper hints, and transcript-label speaker framing.
- `worker/run_job.py`: source preflight now runs before Whisper, writes `source-preflight.json`, and excludes only sources with no usable video/audio or less than 1.5 seconds.
- `core/campaign_exclusions.py` and `worker/sync_campaigns.py`: deterministic gambling/money-game exclusions run before detail hydration and AI analysis. Matching campaigns are marked `blocked` with `EXCLUDED:GAMBLING_OR_MONEY_GAME` and are not eligible for the active list or auto-queue.
- Exact duplicate sources are recorded with `duplicate_of` and skipped before transcription; the first source remains authoritative for processing.
- `core/clip_candidates.py`: silence and scene signals apply a bounded advisory score adjustment only; Whisper-derived `start` and `end` remain unchanged.
- `CLIPPER_MEDIA_SIGNAL_BUDGET_SECONDS` defaults to 8 seconds per candidate. If the optional FFmpeg probes exceed the budget, the remaining optional probe is skipped and metadata records `budget_exceeded`.
- `core/visual_crop.py` exposes `visual_speaker_signal()`, an optional OpenCV face-count heuristic. It is metadata-only for now: one stable face may recommend `speaker-focused`, two or uncertain faces recommend a wide frame, and unavailable/low-confidence detection always recommends `wide-unknown`.
- `scripts/benchmark_media_signals.py` creates a synthetic 24-second video/audio fixture and measures preflight plus candidate-signal runtime. The local baseline is 116.8 ms preflight and 494.7 ms signals, under the 8-second budget; local OpenCV absence correctly produces `wide-unknown`.
- Candidate, validation, and review artifacts now retain the media signal payload. Missing tools or source media produce explicit `available: false` metadata and do not stop deterministic clipping.
- `tests/fixtures/media_signal_cases.json` and `tests/test_media_signals.py`: regression coverage for two-speaker wide framing, dominant-speaker framing, unavailable sources, and source preflight measurements.
- `scripts/evaluate_semantic_fixture.py`: reproducible decision/risk accuracy report against the checked-in semantic corpus.
- `.github/workflows/semantic-fixture.yml`: manual Qwen verification path that does not dispatch or process a production job.

The full suite currently passes: **69 tests**. The semantic fixture reports 4/4 decision matches and 4/4 expected-risk matches in deterministic mode. The isolated Qwen workflow loaded the GGUF and produced valid output for 4/4 cases, but matched only 3/4 decisions (75%) while covering 4/4 expected risks. `node --check web/app.js`, `node --check cloudflare/api.js`, Python compilation, and `git diff --check` also pass.

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
- Subtitle rendering follows `production.subtitle_required`; it is not automatically added to campaigns that do not require it.
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

`clipper-worker.yml` runs on schedule every fifteen minutes and can be dispatched with a `job_id`. It installs the base dependencies, installs the optional semantic dependency, caches Whisper and Qwen assets, downloads the Q4_K_M model, and runs `worker/run_job.py`. The worker is still CPU-oriented and may take longer on long sources.

Do not trigger a production job merely to test code when the known source is only a five-second incomplete excerpt. Use the local regression suite or a campaign with a source long enough to contain a complete moment.

## Next recommended work

1. Add optional silence and scene-change signals to the semantic candidate payload.
2. Add active-speaker heuristics for two-person podcast framing.
3. Keep the manual Qwen fixture as a regression check; do not promote Qwen to automatic decision authority while it trails the deterministic baseline.
4. Run `python3 scripts/benchmark_media_signals.py` in the dependency-complete GitHub environment and add a controlled two-face fixture before considering any crop integration; keep the visual heuristic metadata-only until confidence is stable.
5. Improve active-speaker confidence with optional visual evidence; the current heuristic requires transcript speaker labels or face detections and recommends a wide frame when confidence is low.
6. Re-enable worker authentication only after quality behavior is stable, because the current branch previously disabled it temporarily for debugging.

## Guardrails

The engine must not bypass source permissions, remove required watermarks, use unapproved campaign material, fabricate engagement, publish automatically, or let a semantic model override explicit campaign rules. Any ambiguous mandatory rule stays in human review.
