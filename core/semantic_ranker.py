#!/usr/bin/env python3
"""Local subtitle-first semantic ranking with a deterministic fallback.

The model may rank candidates, but it never owns timestamps or campaign policy.
Timestamps always come from Whisper candidates and policy is re-checked locally.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any


SCHEMA = {
    "type": "object",
    "properties": {
        "rank": {"type": "integer"},
        "decision": {"type": "string", "enum": ["render", "review", "reject"]},
        "semantic_score": {"type": "number"},
        "hook_score": {"type": "number"},
        "context_score": {"type": "number"},
        "payoff_score": {"type": "number"},
        "completeness_score": {"type": "number"},
        "campaign_relevance": {"type": "string", "enum": ["pass", "uncertain", "fail"]},
        "reason": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rank", "decision", "semantic_score", "hook_score", "context_score", "payoff_score", "completeness_score", "campaign_relevance", "reason", "risks"],
}


def _rules(plan: dict[str, Any]) -> dict[str, Any]:
    production = plan.get("production") or {}
    ai = plan.get("ai_rules") or {}
    return {
        "allowed_content": production.get("allowed_content") or (ai.get("rules") or {}).get("allowed_content") or [],
        "prohibited_content": production.get("prohibited") or (ai.get("rules") or {}).get("prohibited_content") or [],
        "topic_terms": production.get("topic_terms") or (ai.get("rules") or {}).get("topic_terms") or [],
        "min_duration_seconds": production.get("min_duration_seconds"),
        "max_duration_seconds": production.get("max_duration_seconds"),
        "mandatory_requirements": [
            x.get("text") for x in (plan.get("source_of_truth") or {}).get("requirements") or []
            if isinstance(x, dict) and x.get("isMandatory") and x.get("text")
        ],
    }


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _deterministic(candidate: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(candidate.get("text") or "").split())
    lower = text.lower()
    words = _words(text)
    rules = _rules(plan)
    topic_terms = [str(x).lower() for x in rules["topic_terms"]]
    matches = [term for term in topic_terms if term and term in lower]
    first = words[0] if words else ""
    starts_mid = first in {"and", "but", "so", "because", "they", "they're", "it", "this", "that", "which", "to"}
    complete_end = bool(re.search(r"[.!?]$", text))
    duration = float(candidate.get("duration") or 0)
    campaign_min = float(rules["min_duration_seconds"] or 0)
    campaign_max = float(rules["max_duration_seconds"] or 0)
    quality_floor = campaign_min or (8.0 if not campaign_max or campaign_max >= 8.0 else 3.0)
    hook = 78.0 if ("?" in text or re.search(r"\b(how|why|what|mistake|secret|truth|biggest)\b", lower)) else 45.0
    context = min(100.0, 35.0 + len(words) * 1.2) if not starts_mid else 20.0
    payoff = 82.0 if re.search(r"\b(so|therefore|that means|the answer|the lesson|finally|which is why)\b", lower) else 42.0
    completeness = 85.0 if complete_end and not starts_mid and duration >= quality_floor else 28.0
    risks: list[str] = []
    if duration < quality_floor:
        completeness -= 30
    if campaign_max and duration > campaign_max:
        risks.append("campaign_max_duration_exceeded")
    semantic = max(0.0, min(100.0, hook * 0.22 + context * 0.25 + payoff * 0.25 + completeness * 0.28))
    relevance = "pass" if matches else "uncertain"
    if starts_mid:
        risks.append("starts_mid_thought")
    if not complete_end:
        risks.append("unfinished_sentence")
    if duration < quality_floor:
        risks.append("short_clip")
    if not matches:
        risks.append("topic_match_requires_human_review")
    decision = "reject" if starts_mid or not complete_end or duration < quality_floor or (campaign_max and duration > campaign_max) else ("render" if semantic >= 60 else "review")
    return {
        "rank": int(candidate.get("rank") or 0),
        "decision": decision,
        "semantic_score": round(semantic, 2),
        "hook_score": round(hook, 2),
        "context_score": round(context, 2),
        "payoff_score": round(payoff, 2),
        "completeness_score": round(completeness, 2),
        "campaign_relevance": relevance,
        "reason": "deterministic fallback: " + ("; ".join(risks) if risks else "complete candidate structure"),
        "risks": risks,
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def _normalize_model_results(parsed: dict[str, Any] | None, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Normalize common GGUF JSON shapes without guessing across candidates."""
    if not parsed:
        return None, "model_invalid_json"
    results = parsed.get("results")
    if results is None and len(candidates) == 1 and "decision" in parsed:
        results = [parsed]
    if not isinstance(results, list) or len(results) != len(candidates):
        return None, "model_invalid_results_count"
    indexed = {int(item.get("rank")): item for item in results if isinstance(item, dict) and str(item.get("rank", "")).isdigit()}
    normalized: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        item = indexed.get(int(candidate.get("rank") or 0))
        if item is None and len(results) == len(candidates) and isinstance(results[index], dict) and "rank" not in results[index]:
            item = results[index]
        if not isinstance(item, dict):
            return None, "model_missing_candidate_result"
        item = dict(item)
        item["rank"] = int(candidate.get("rank") or 0)
        normalized.append(item)
    return normalized, None


def _model_rank(candidates: list[dict[str, Any]], plan: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    model_path = os.environ.get("CLIPPER_SEMANTIC_MODEL", "").strip()
    if not model_path or os.environ.get("CLIPPER_SEMANTIC_ENABLED", "auto").lower() in {"0", "false", "off"}:
        return None, "model_disabled_or_path_missing"
    try:
        from llama_cpp import Llama
    except ImportError:
        return None, "llama_cpp_unavailable"
    try:
        llm = Llama(model_path=model_path, n_ctx=8192, n_threads=max(1, int(os.environ.get("CLIPPER_SEMANTIC_THREADS", "4"))), verbose=False)
        prompt_data = {
            "campaign_rules": _rules(plan),
            "candidates": [
                {"rank": c.get("rank"), "start": c.get("start"), "end": c.get("end"), "duration": c.get("duration"), "subtitle": c.get("text")}
                for c in candidates
            ],
        }
        messages = [
            {"role": "system", "content": "You rank short-video candidates from subtitles. Never invent timestamps. Return one JSON object per candidate inside a results array. Campaign rules are authoritative. Reject incomplete thoughts."},
            {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)},
        ]
        response = llm.create_chat_completion(
            messages=messages,
            temperature=0.0,
            max_tokens=1800,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"].get("content", "")
        parsed = _extract_json(content)
        return _normalize_model_results(parsed, candidates)
    except Exception as exc:
        return None, f"model_inference_failed:{type(exc).__name__}"


def rank_candidates_with_metadata(candidates: list[dict[str, Any]], plan: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return candidates with semantic metadata, preserving source timestamps."""
    model_results, fallback_reason = _model_rank(candidates, plan)
    results = model_results or [_deterministic(candidate, plan) for candidate in candidates]
    runtime = {
        "schema_version": 1,
        "engine": "qwen" if model_results is not None else "deterministic",
        "fallback_used": model_results is None,
        "fallback_reason": fallback_reason,
        "candidate_count": len(candidates),
    }
    by_rank = {int(item.get("rank") or 0): item for item in results}
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        semantic = by_rank.get(int(candidate.get("rank") or 0), _deterministic(candidate, plan))
        local_guard = _deterministic(candidate, plan)
        if local_guard["decision"] == "reject" and semantic.get("decision") != "reject":
            semantic = dict(semantic)
            semantic["decision"] = "reject"
            semantic["risks"] = list(dict.fromkeys(list(semantic.get("risks") or []) + list(local_guard.get("risks") or [])))
            semantic["reason"] = str(semantic.get("reason") or "") + "; local hard-policy gate: " + ", ".join(local_guard.get("risks") or ["structural_rejection"])
        semantic["engine"] = runtime["engine"]
        semantic["fallback_used"] = runtime["fallback_used"]
        semantic["fallback_reason"] = runtime["fallback_reason"]
        item["semantic"] = semantic
        item["score"] = round(float(candidate.get("score") or 0) * 0.35 + float(semantic.get("semantic_score") or 0) / 100 * 0.65, 4)
        ranked.append(item)
    ranked.sort(key=lambda x: (-float(x.get("score") or 0), float(x.get("start") or 0)))
    for index, item in enumerate(ranked, 1):
        item["rank"] = index
        item["semantic"]["rank"] = index
    return ranked, runtime


def rank_candidates(candidates: list[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Backward-compatible ranking API; use rank_candidates_with_metadata for diagnostics."""
    ranked, _runtime = rank_candidates_with_metadata(candidates, plan)
    return ranked


__all__ = ["rank_candidates", "rank_candidates_with_metadata", "SCHEMA"]
