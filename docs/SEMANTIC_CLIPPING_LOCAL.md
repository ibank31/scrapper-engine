# Semantic Clipping Local-First

**Status:** implemented on `main` 22 September 2026

## Purpose

The clipping engine now uses a subtitle-first semantic stage before rendering. Whisper remains responsible for word-level timestamps. The semantic stage reads transcript candidates, evaluates hook, context, payoff, completeness, and campaign relevance, then ranks or rejects candidates. It never invents timestamps and it never overrides the campaign plan.

## Production path

```text
campaign plan
  -> official asset intake
  -> faster-whisper word timestamps
  -> sentence/turn candidate windows
  -> local semantic ranker
  -> campaign-rule validation
  -> render top candidates
  -> technical/editorial validator
  -> human review
```

The implementation is in `core/clip_candidates.py`, `core/semantic_ranker.py`, and `modules/clipping/semantic_rank.py`. The worker invokes sentence/turn segmentation and semantic ranking automatically after transcription and before rendering.

The evaluation corpus is `tests/fixtures/semantic_cases.json`. It covers a complete problem-to-solution moment, a short mid-thought excerpt, an unfinished story, and a campaign with an explicit short maximum. The corpus runs in the normal regression suite so selector changes can be checked without spending a production job.

## Semantic engine

The optional model is **Qwen2.5-1.5B-Instruct-GGUF Q4_K_M**, loaded with `llama-cpp-python` on CPU. The official model card identifies the model as Apache-2.0 licensed, approximately 1.54B parameters, and provides the GGUF quantizations. The workflow downloads the model into the GitHub Actions cache and sets `CLIPPER_SEMANTIC_MODEL`.

The model is optional. If the package, model, or inference fails, the worker uses the deterministic scorer in the same module. This is deliberate: a model outage must not make the whole free pipeline unavailable, and all timestamps and campaign policy remain locally auditable.

## Candidate contract

A candidate retains the original timestamp fields:

```json
{
  "rank": 1,
  "start": 184.2,
  "end": 231.8,
  "duration": 47.6,
  "text": "...",
  "score": 0.87,
  "semantic": {
    "decision": "render",
    "semantic_score": 87.0,
    "hook_score": 91.0,
    "context_score": 84.0,
    "payoff_score": 88.0,
    "completeness_score": 93.0,
    "campaign_relevance": "pass",
    "reason": "...",
    "risks": []
  }
}
```

`semantic_ranker.py` may change ranking and attach metadata, but it does not change `start`, `end`, or `duration`. The renderer therefore cuts the exact interval identified by the transcript.

## Rules precedence

`plan.json` remains the source of truth. The semantic model is not allowed to turn a prohibited topic into an allowed topic, waive a mandatory requirement, or change duration limits. The local fallback and validator apply the same effective duration policy:

- campaign `min_duration_seconds` wins when present;
- campaign `max_duration_seconds` is a hard upper bound when present;
- absent campaign bounds use an eight-second editorial floor and a sixty-second ceiling;
- a campaign explicitly capped below eight seconds is honored, but the result remains subject to human review.

A candidate that starts mid-thought, ends unfinished, or falls below its effective floor is rejected before rendering. A candidate with uncertain topic matching is retained only for review when it is otherwise structurally complete.

## Workflow configuration

The worker workflow installs the optional dependencies from `requirements-semantic.txt`, downloads the Q4_K_M model, caches it, and sets:

```text
CLIPPER_SEMANTIC_MODEL=/home/runner/.cache/clipper-semantic/qwen2.5-1.5b-instruct-q4_k_m.gguf
CLIPPER_SEMANTIC_ENABLED=auto
CLIPPER_SEMANTIC_THREADS=4
```

Set `CLIPPER_SEMANTIC_ENABLED=false` to force deterministic-only mode. Set `CLIPPER_SEMANTIC_MODEL` to a local GGUF path for local execution.

## Local commands

Deterministic fallback test:

```bash
python run.py semantic_rank candidates.json --plan plan.json
```

Local model execution:

```bash
pip install -r requirements-semantic.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
export CLIPPER_SEMANTIC_MODEL="$HOME/.cache/clipper-semantic/qwen2.5-1.5b-instruct-q4_k_m.gguf"
python run.py semantic_rank candidates.json --plan plan.json
```

## Known limitations

A 1.5B CPU model is a useful ranking assistant, not a replacement for a large multimodal editor. It reads subtitles and cannot reliably understand a visual-only punchline, screen demonstration, object action, or speaker identity. The existing face-aware crop, FFmpeg renderer, technical validator, and human review remain necessary. The next quality increment is optional silence/scene-change and active-speaker signals, not more visual effects.

## Sources

1. [Qwen2.5-1.5B-Instruct model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) — Apache-2.0, architecture, parameters, Transformers usage.
2. [Qwen2.5-1.5B-Instruct-GGUF model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) — Q4_K_M quantization and llama.cpp usage.
3. [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) — CPU installation, chat completion, and JSON response format.
