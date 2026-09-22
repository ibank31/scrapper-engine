# Scrapper Engine — Current Agent Handoff

**Updated:** 22 September 2026
**Repository:** `ibank31/scrapper-engine`
**Production branch:** `main`
**Latest implementation commit:** `00648bc` — optional source-quality, silence/scene, and speaker-framing signals with review metadata and regression fixtures.

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
- Candidate, validation, and review artifacts now retain the media signal payload. Missing tools or source media produce explicit `available: false` metadata and do not stop deterministic clipping.
- `tests/fixtures/media_signal_cases.json` and `tests/test_media_signals.py`: regression coverage for two-speaker wide framing, dominant-speaker framing, unavailable sources, and source preflight measurements.

The full suite currently passes: **56 tests**. `node --check web/app.js`, `node --check cloudflare/api.js`, Python compilation, and `git diff --check` also pass.

## Model and fallback policy

The worker uses `Qwen/Qwen2.5-1.5B-Instruct-GGUF`, Q4_K_M, through `llama-cpp-python` when the optional package and model are available. The model is Apache-2.0 according to its official Hugging Face card. If installation, model download, or inference fails, the worker falls back to deterministic ranking and continues. This keeps the free pipeline available and makes failures observable rather than fatal.

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
3. Add a small fixture from a long approved source and run one controlled end-to-end worker test, including the Qwen path on GitHub Actions. This was intentionally not run in the local sandbox because no approved long source was available and production jobs are not a debugging fixture.
4. Improve active-speaker confidence with optional visual evidence; the current heuristic requires transcript speaker labels and recommends a wide frame when confidence is low.
5. Re-enable worker authentication only after quality behavior is stable, because the current branch previously disabled it temporarily for debugging.

## Guardrails

The engine must not bypass source permissions, remove required watermarks, use unapproved campaign material, fabricate engagement, publish automatically, or let a semantic model override explicit campaign rules. Any ambiguous mandatory rule stays in human review.
