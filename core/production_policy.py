#!/usr/bin/env python3
"""Deterministic production-quality policy for short-form clip selection.

This module makes editorial decisions inside the pipeline. It intentionally
returns scores and reasons for ranking, not a user-facing performance forecast.
Campaign rules remain authoritative; the policy only optimizes among compliant
candidate windows.
"""
from __future__ import annotations

import re
from typing import Any


GREETING_TERMS = {
    "hello", "hi", "hey", "welcome", "today", "guys", "everyone",
    "thanks", "thank", "okay", "alright", "so", "um", "uh",
}
CONFLICT_TERMS = {
    "but", "however", "actually", "wrong", "mistake", "problem", "fight",
    "argue", "never", "nobody", "surprise", "wait", "why", "how", "what",
    "secret", "truth", "crazy", "insane", "impossible", "because",
}
PAYOFF_TERMS = {
    "so", "therefore", "that means", "the lesson", "in the end", "finally",
    "which is why", "the answer", "turns out", "actually", "but then",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _platforms(plan: dict[str, Any] | None) -> set[str]:
    campaign = (plan or {}).get("campaign") or {}
    production = (plan or {}).get("production") or {}
    values = campaign.get("platforms") or production.get("platforms") or []
    return {str(value).lower().strip() for value in values if str(value).strip()}


def effective_bounds(plan: dict[str, Any] | None) -> tuple[float, float]:
    production = (plan or {}).get("production") or {}
    campaign_minimum = float(production.get("min_duration_seconds") or 0)
    campaign_maximum = float(production.get("max_duration_seconds") or 0)
    minimum = campaign_minimum or (8.0 if not campaign_maximum or campaign_maximum >= 8.0 else 3.0)
    maximum = campaign_maximum if campaign_maximum > 0 else 60.0
    return min(minimum, maximum), maximum


def _duration_score(duration: float, minimum: float, maximum: float) -> tuple[float, str]:
    """Prefer compact complete clips without enforcing a universal duration."""
    if duration < minimum or duration > maximum:
        return -0.35, "outside production duration bounds"
    # These are ranking bands, not hard rules. The strongest band depends on
    # whether the transcript contains enough structure to justify its length.
    if duration <= 18:
        return 0.08, "compact single-beat clip"
    if duration <= 35:
        return 0.13, "efficient short-form length"
    if duration <= 50:
        return 0.10, "dialogue/story length with room for payoff"
    return 0.01, "long clip requires unusually strong structure"


def _hook_score(text: str) -> tuple[float, list[str]]:
    words = _words(text)
    if not words:
        return -0.20, ["empty opening"]
    opening = words[:14]
    lower = " ".join(opening)
    score = 0.0
    reasons: list[str] = []
    if "?" in text[:120] or any(term in opening for term in CONFLICT_TERMS):
        score += 0.13
        reasons.append("conflict/question in opening")
    if any(term in opening for term in {"you", "your", "this", "that", "why", "how", "what"}):
        score += 0.04
        reasons.append("direct audience or situation reference")
    if opening and opening[0] in GREETING_TERMS:
        score -= 0.10
        reasons.append("generic greeting/setup")
    if len(opening) >= 8:
        score += 0.04
        reasons.append("enough opening signal")
    if len(words) < 20:
        score -= 0.10
        reasons.append("opening has little context")
    return score, reasons


def _payoff_score(text: str, duration: float) -> tuple[float, list[str]]:
    lower = (text or "").lower()
    reasons: list[str] = []
    matches: list[int] = []
    for term in PAYOFF_TERMS:
        position = lower.find(term)
        if position >= 0:
            matches.append(position)
    if not matches:
        # A complete sentence can still be a visual or comedic payoff, so this
        # is a modest penalty rather than rejection.
        return -0.03, ["explicit payoff cue not detected"]
    relative = min(matches) / max(1, len(lower))
    if 0.35 <= relative <= 0.88:
        reasons.append("payoff arrives before the ending")
        return 0.13, reasons
    if relative > 0.88:
        return -0.10, ["payoff arrives too late"]
    return 0.03, ["payoff cue appears early"]


def score_production_candidate(candidate: dict[str, Any], plan: dict[str, Any] | None = None) -> tuple[float, list[str]]:
    """Return a bounded ranking adjustment and auditable internal reasons."""
    duration = float(candidate.get("duration") or 0)
    minimum, maximum = effective_bounds(plan)
    score = 0.0
    reasons: list[str] = []
    duration_delta, duration_reason = _duration_score(duration, minimum, maximum)
    score += duration_delta
    reasons.append(duration_reason)
    hook_delta, hook_reasons = _hook_score(str(candidate.get("text") or ""))
    score += hook_delta
    reasons.extend(hook_reasons)
    payoff_delta, payoff_reasons = _payoff_score(str(candidate.get("text") or ""), duration)
    score += payoff_delta
    reasons.extend(payoff_reasons)
    if re.search(r"[.!?]$", str(candidate.get("text") or "").strip()):
        score += 0.08
        reasons.append("complete spoken ending")
    else:
        score -= 0.12
        reasons.append("unfinished spoken ending")
    media = candidate.get("media_signals") or {}
    silence = (media.get("silence_voice_activity") or {})
    if silence.get("available"):
        ratio = float(silence.get("silence_ratio") or 0)
        if ratio >= 0.40:
            score -= 0.08
            reasons.append("high silence risk")
        elif ratio <= 0.10:
            score += 0.03
            reasons.append("continuous voice activity")
    speaker = (media.get("visual_active_speaker") or {})
    if speaker.get("framing_recommendation") == "wide-two-speaker":
        score += 0.03
        reasons.append("dialogue framing should stay wide")
    return round(max(-0.45, min(0.40, score)), 4), reasons


def enrich_candidate(candidate: dict[str, Any], plan: dict[str, Any] | None = None) -> dict[str, Any]:
    adjustment, reasons = score_production_candidate(candidate, plan)
    enriched = dict(candidate)
    enriched["production_quality_adjustment"] = adjustment
    enriched["production_quality_reasons"] = reasons
    enriched["score"] = round(max(0.0, min(1.0, float(candidate.get("score") or 0) + adjustment)), 4)
    return enriched


__all__ = ["effective_bounds", "enrich_candidate", "score_production_candidate"]
