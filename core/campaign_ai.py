#!/usr/bin/env python3
"""Campaign intelligence using the Gemini API."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Iterable

import requests

GEMINI_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TRANSIENT_GEMINI_STATUSES = {408, 429, 500, 502, 503, 504}

DEFAULT_PROFILE = {
    "preferred_topics": ["technology", "artificial intelligence", "software", "coding", "developer", "business", "education", "science", "creator", "podcast", "gaming"],
    "preferred_platforms": ["tiktok", "youtube", "instagram"],
    "preferred_workflow": ["official footage", "provided clips", "content bank", "approved campaign assets", "short-form clipping"],
    "excluded_topics": ["gambling", "casino", "adult content", "nicotine", "illegal drugs", "weapons", "fraud"],
}


class GeminiApiError(RuntimeError):
    """A transport or API-level Gemini failure."""


class GeminiSafetyError(GeminiApiError):
    """Gemini rejected the prompt or candidate for safety reasons."""


class GeminiJsonError(RuntimeError):
    """Gemini returned empty, invalid, or incomplete JSON."""


# Gemini structured output supports this OpenAPI/JSON-Schema subset. Keep the
# shape aligned with normalize_ai_result and campaign_rules consumers.
GEMINI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "campaigns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "campaign_id": {"type": "string"},
                    "campaign_fit": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "number"},
                            "label": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["label", "reason"],
                    },
                    "rules": {
                        "type": "object",
                        "properties": {
                            "source_policy": {"type": "string"},
                            "platforms": {"type": "array", "items": {"type": "string"}},
                            "aspect_ratio": {"type": "string"},
                            "min_duration_seconds": {"type": "integer"},
                            "max_duration_seconds": {"type": "integer"},
                            "subtitle_required": {"type": "boolean"},
                            "subtitle_style": {"type": "string"},
                            "watermark_required": {"type": "boolean"},
                            "third_party_watermark_allowed": {"type": "boolean"},
                            "official_audio_required": {"type": "boolean"},
                            "cta_required": {"type": "boolean"},
                            "cta_text": {"type": "string"},
                            "handles": {"type": "array", "items": {"type": "string"}},
                            "hashtags": {"type": "array", "items": {"type": "string"}},
                            "disclosures": {"type": "array", "items": {"type": "string"}},
                            "topic_terms": {"type": "array", "items": {"type": "string"}},
                            "allowed_content": {"type": "array", "items": {"type": "string"}},
                            "prohibited_content": {"type": "array", "items": {"type": "string"}},
                            "asset_sources": {"type": "array", "items": {"type": "string"}},
                            "posting_rules": {"type": "array", "items": {"type": "string"}},
                            "account_rules": {"type": "array", "items": {"type": "string"}},
                            "audience_tiers": {"type": "object"},
                            "platform_rules": {"type": "object"},
                            "subtitle_delivery_profile": {"type": "string"},
                            "sound_policy": {"type": "string"},
                            "native_tags": {"type": "array", "items": {"type": "string"}},
                            "material_policy": {"type": "object"},
                        },
                        "required": [
                            "source_policy", "platforms",
                            "subtitle_required", "subtitle_style", "watermark_required", "third_party_watermark_allowed",
                            "official_audio_required", "cta_required", "handles", "hashtags", "disclosures",
                            "topic_terms", "allowed_content", "prohibited_content", "asset_sources", "posting_rules", "account_rules",
                        ],
                    },
                    "ambiguities": {"type": "array", "items": {"type": "string"}},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"rule_path": {"type": "string"}, "quote": {"type": "string"}},
                            "required": ["rule_path", "quote"],
                        },
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["campaign_id", "campaign_fit", "rules", "ambiguities", "evidence", "confidence"],
            },
        },
    },
    "required": ["campaigns"],
}


def _load_profile() -> dict[str, Any]:
    path = Path(os.getenv("SCRAPPER_AI_PROFILE", "config/campaign_ai_profile.json"))
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else DEFAULT_PROFILE
    except Exception:
        return DEFAULT_PROFILE


def rules_fingerprint(campaign: dict[str, Any]) -> str:
    payload = {
        "title": campaign.get("title"), "brand": campaign.get("brand"),
        "description": campaign.get("description"), "docs_text": campaign.get("docs_text") or campaign.get("documents") or "",
        "source_urls": campaign.get("source_urls") or campaign.get("asset_urls") or [],
        "platforms": campaign.get("platforms"),
        "type": campaign.get("type"), "requirements": campaign.get("requirements") or [],
        "resources": campaign.get("resources") or [], "payouts": campaign.get("payouts") or [],
        "normalized_plan": campaign.get("plan") or campaign.get("source_of_truth") or {},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _gemini_api_key() -> str:
    """Read the key only when an API call is needed; never print or include it in errors."""
    return os.environ["GEMINI_API_KEY"]


def _json_from_text(text: str) -> Any:
    if not isinstance(text, str) or not text.strip():
        raise GeminiJsonError("Gemini returned empty text")
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as exc:
        if exc.pos >= max(0, len(clean) - 2) or clean.count("{") > clean.count("}") or clean.count("[") > clean.count("]"):
            raise GeminiJsonError("Gemini returned truncated JSON") from exc
        raise GeminiJsonError("Gemini returned invalid JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("campaigns"), list):
        raise GeminiJsonError("Gemini JSON did not contain a campaigns array")
    return parsed


def _safe_block_reason(prompt_feedback: Any) -> str:
    if not isinstance(prompt_feedback, dict):
        return "none"
    reason = prompt_feedback.get("blockReason") or prompt_feedback.get("block_reason")
    return str(reason)[:80] if reason else "none"


def _retry_config() -> tuple[int, float, float]:
    try:
        retries = max(0, min(5, int(os.getenv("GEMINI_MAX_RETRIES", "2"))))
    except ValueError:
        retries = 2
    try:
        base = max(0.1, min(30.0, float(os.getenv("GEMINI_RETRY_BASE_SECONDS", "2"))))
    except ValueError:
        base = 2.0
    try:
        cap = max(base, min(60.0, float(os.getenv("GEMINI_RETRY_MAX_SECONDS", "20"))))
    except ValueError:
        cap = 20.0
    return retries, base, cap


def _retry_delay(attempt: int, base: float, cap: float) -> float:
    exponential = min(cap, base * (2 ** max(0, attempt - 1)))
    return min(cap, exponential + random.uniform(0, exponential * 0.25))


def _error_reason(response: Any) -> str:
    reason = "unspecified"
    try:
        error_body = response.json()
        if isinstance(error_body, dict) and isinstance(error_body.get("error"), dict):
            reason = str(error_body["error"].get("message") or reason)
    except (ValueError, TypeError):
        pass
    return re.sub(r"AIza[0-9A-Za-z_-]{12,}", "[redacted]", reason)[:240]


def _gemini_generate(prompt: str, timeout: int = 120) -> str:
    url = f"{GEMINI_API_BASE.rstrip('/')}/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.8,
            "maxOutputTokens": 12000,
            "responseMimeType": "application/json",
            "responseSchema": GEMINI_RESPONSE_SCHEMA,
        },
    }
    max_retries, retry_base, retry_cap = _retry_config()
    for attempt in range(1, max_retries + 2):
        try:
            response = requests.post(
                url,
                headers={"content-type": "application/json", "x-goog-api-key": _gemini_api_key()},
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt > max_retries:
                raise GeminiApiError(
                    f"Gemini API request failed after {attempt} attempts: {type(exc).__name__}"
                ) from exc
            delay = _retry_delay(attempt, retry_base, retry_cap)
            print(
                "Gemini request diagnostics: "
                f"attempt={attempt} transport_error={type(exc).__name__} "
                f"retryable=true retry_in={delay:.2f}s"
            )
            time.sleep(delay)
            continue

        if not response.ok:
            status = int(response.status_code)
            retryable = status in TRANSIENT_GEMINI_STATUSES
            reason = _error_reason(response)
            print(
                "Gemini request diagnostics: "
                f"attempt={attempt} http_status={status} retryable={str(retryable).lower()}"
            )
            if not retryable or attempt > max_retries:
                raise GeminiApiError(
                    f"Gemini API request failed with HTTP {status}: {reason}"
                )
            delay = _retry_delay(attempt, retry_base, retry_cap)
            print(f"Gemini transient error: HTTP {status}; retry_in={delay:.2f}s")
            time.sleep(delay)
            continue

        body = response.json()
        candidates = body.get("candidates") if isinstance(body, dict) else None
        candidates = candidates if isinstance(candidates, list) else []
        feedback = body.get("promptFeedback") if isinstance(body, dict) else None
        candidate = candidates[0] if candidates else {}
        finish_reason = candidate.get("finishReason") or candidate.get("finish_reason") or "none"
        parts = candidate.get("content", {}).get("parts", []) if isinstance(candidate, dict) else []
        parts = parts if isinstance(parts, list) else []
        text_parts = [
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        text = "".join(text_parts)
        truncated = str(finish_reason).upper() in {"MAX_TOKENS", "LENGTH"}
        print(
            "Gemini response diagnostics: "
            f"http_status={response.status_code} candidate_count={len(candidates)} "
            f"part_count={len(parts)} finish_reason={str(finish_reason)[:40]} "
            f"prompt_block_reason={_safe_block_reason(feedback)} "
            f"text_length={len(text)} truncated={str(truncated).lower()}"
        )
        if not candidates:
            reason = _safe_block_reason(feedback)
            if reason != "none":
                raise GeminiSafetyError(f"Gemini prompt blocked: {reason}")
            raise GeminiApiError("Gemini returned no candidates")
        if truncated:
            raise GeminiJsonError(
                f"Gemini response truncated: finish_reason={str(finish_reason)[:40]}"
            )
        if str(finish_reason).upper() not in {"STOP", "NONE"}:
            raise GeminiApiError(
                f"Gemini candidate finished with {str(finish_reason)[:40]}"
            )
        if not text:
            raise GeminiJsonError("Gemini candidate contained no text")
        return text

    raise GeminiApiError("Gemini request exhausted retries")


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def normalize_ai_result(item: dict[str, Any], campaign_id: str) -> dict[str, Any]:
    rules = item.get("rules") if isinstance(item.get("rules"), dict) else {}
    fit = item.get("campaign_fit") if isinstance(item.get("campaign_fit"), dict) else {}
    fit_score = _num(fit.get("score"))
    if fit_score is not None:
        fit_score = max(0.0, min(1.0, fit_score))
    confidence = max(0.0, min(1.0, _num(item.get("confidence"), 0.0) or 0.0))
    return {
        "schema_version": 1, "campaign_id": campaign_id,
        "campaign_fit": {"score": fit_score, "label": str(fit.get("label") or "unknown"), "reason": str(fit.get("reason") or "")},
        "rules": {
            "source_policy": str(rules.get("source_policy") or "campaign_defined"), "platforms": list(rules.get("platforms") or []),
            "aspect_ratio": rules.get("aspect_ratio"), "min_duration_seconds": _int_or_none(rules.get("min_duration_seconds")),
            "max_duration_seconds": _int_or_none(rules.get("max_duration_seconds")), "subtitle_required": bool(rules.get("subtitle_required")),
            "subtitle_style": str(rules.get("subtitle_style") or "campaign_defined"), "watermark_required": bool(rules.get("watermark_required")),
            "third_party_watermark_allowed": bool(rules.get("third_party_watermark_allowed")), "official_audio_required": bool(rules.get("official_audio_required")),
            "cta_required": bool(rules.get("cta_required")), "cta_text": rules.get("cta_text"), "handles": list(rules.get("handles") or []),
            "hashtags": list(rules.get("hashtags") or []), "disclosures": list(rules.get("disclosures") or []), "topic_terms": list(rules.get("topic_terms") or []),
            "allowed_content": list(rules.get("allowed_content") or []), "prohibited_content": list(rules.get("prohibited_content") or []),
            "asset_sources": list(rules.get("asset_sources") or []), "posting_rules": list(rules.get("posting_rules") or []), "account_rules": list(rules.get("account_rules") or []),
            "audience_tiers": rules.get("audience_tiers") if isinstance(rules.get("audience_tiers"), dict) else {},
            "platform_rules": rules.get("platform_rules") if isinstance(rules.get("platform_rules"), dict) else {},
            "subtitle_delivery_profile": str(rules.get("subtitle_delivery_profile") or ""),
            "sound_policy": str(rules.get("sound_policy") or "manual_required"),
            "native_tags": list(rules.get("native_tags") or []),
            "material_policy": rules.get("material_policy") if isinstance(rules.get("material_policy"), dict) else {},
        },
        "ambiguities": [str(x) for x in (item.get("ambiguities") or [])],
        "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
        "confidence": confidence,
    }


def _campaign_prompt_payload(campaign: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_id": campaign.get("id"), "title": campaign.get("title"), "brand": campaign.get("brand"), "category": campaign.get("category"),
        "type": campaign.get("type"), "platforms": campaign.get("platforms") or [], "description": campaign.get("description") or "",
        "requirements": campaign.get("requirements") or [], "resources": campaign.get("resources") or [], "payouts": campaign.get("payouts") or [],
        "docs_text": campaign.get("docs_text") or "", "source_urls": campaign.get("source_urls") or campaign.get("asset_urls") or [],
        "source_of_truth": campaign.get("source_of_truth") or {},
    }


def _prompt(batch: Iterable[dict[str, Any]]) -> str:
    profile = _load_profile()
    return """You are the campaign-intelligence layer of a clipping production engine.
Read each campaign independently. Extract only what is supported by supplied text. Never invent a rule.
Identify every explicit production or posting rule that can affect clip validity.
Build a campaign-specific material acquisition plan. Do not assume every campaign uses the same acquisition method. For every required material, identify intent, quantity, preferred/fallback sources, allowed/forbidden source types, discovery methods, identity fields, verification requirements, and evidence. Never treat an example/reference link as production footage unless the campaign explicitly says so. If acquisition is unclear, choose manual_required or unresolved rather than inventing a source.
Record CRITICAL ambiguity only when an unknown could change asset selection, edit/render decisions, or posting compliance.
Decide campaign_fit using this operator profile:
""" + json.dumps(profile, ensure_ascii=False) + """
Return one object matching the supplied response schema. Include one campaign result for every input campaign.
Campaigns:
""" + json.dumps([_campaign_prompt_payload(x) for x in batch], ensure_ascii=False)


def _fallback_result(campaign: dict[str, Any], reason: str = "AI omitted this campaign") -> dict[str, Any]:
    cid = str(campaign.get("id") or "")
    safe_reason = re.sub(r"AIza[0-9A-Za-z_-]{12,}", "[redacted]", str(reason))[:240]
    return {
        "schema_version": 1, "campaign_id": cid,
        "campaign_fit": {"score": None, "label": "unknown", "reason": "AI analysis unavailable"},
        "rules": {
            "source_policy": "unknown", "platforms": campaign.get("platforms") or [], "aspect_ratio": None,
            "min_duration_seconds": None, "max_duration_seconds": None, "subtitle_required": False, "subtitle_style": "campaign_defined",
            "watermark_required": False, "third_party_watermark_allowed": False, "official_audio_required": False, "cta_required": False,
            "cta_text": None, "handles": [], "hashtags": [], "disclosures": [], "topic_terms": [], "allowed_content": [],
            "prohibited_content": [], "asset_sources": [], "posting_rules": [], "account_rules": [], "audience_tiers": {}, "platform_rules": {}, "subtitle_delivery_profile": "", "sound_policy": "manual_required", "native_tags": [],
        },
        "ambiguities": [f"CRITICAL: {safe_reason}"], "evidence": [], "confidence": 0.0,
    }


def analyze_campaigns(campaigns: list[dict[str, Any]], batch_size: int = 8) -> dict[str, dict[str, Any]]:
    if not campaigns:
        return {}
    results: dict[str, dict[str, Any]] = {}
    batch_size = max(1, batch_size)
    for start in range(0, len(campaigns), batch_size):
        batch = campaigns[start:start + batch_size]
        batch_no = start // batch_size + 1
        try:
            parsed = _json_from_text(_gemini_generate(_prompt(batch)))
            items = parsed["campaigns"]
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                cid = str(raw.get("campaign_id") or "")
                if cid:
                    results[cid] = normalize_ai_result(raw, cid)
            for campaign in batch:
                cid = str(campaign.get("id") or "")
                if cid not in results:
                    results[cid] = _fallback_result(campaign)
        except (GeminiApiError, GeminiJsonError) as exc:
            reason = str(exc)
            print(
                "(!) Gemini batch failed: "
                f"batch={batch_no} campaigns={len(batch)} model={GEMINI_MODEL} "
                f"reason={reason[:240]}"
            )
            for campaign in batch:
                cid = str(campaign.get("id") or "")
                if cid:
                    results[cid] = _fallback_result(
                        campaign, f"Gemini batch {batch_no} failed: {reason}"
                    )
    return results


__all__ = ["GEMINI_RESPONSE_SCHEMA", "GeminiApiError", "GeminiJsonError", "GeminiSafetyError", "analyze_campaigns", "normalize_ai_result", "rules_fingerprint"]
