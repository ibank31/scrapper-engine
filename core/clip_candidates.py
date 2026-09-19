#!/usr/bin/env python3
"""Deterministic, auditable highlight candidate scoring."""
from __future__ import annotations

import re
from typing import Any

HOOKS = ("how", "why", "what", "the truth", "nobody", "most people", "the biggest", "here's", "here is", "mistake", "secret")
SIGNALS = ("because", "but", "however", "instead", "first", "finally", "million", "percent", "%", "$", "step", "lesson", "problem", "solution")


def _words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _score_text(text: str) -> tuple[float, list[str]]:
    lower = (text or "").lower()
    score = 0.0
    reasons: list[str] = []
    hook_hits = sum(1 for x in HOOKS if x in lower)
    signal_hits = sum(1 for x in SIGNALS if x in lower)
    question = "?" in text
    if hook_hits:
        score += min(0.25, hook_hits * 0.08)
        reasons.append("hook language")
    if signal_hits:
        score += min(0.30, signal_hits * 0.05)
        reasons.append("story or information signal")
    if question:
        score += 0.10
        reasons.append("question")
    if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|percent|dollars?|million|thousand|k)\b", lower):
        score += 0.15
        reasons.append("concrete number")
    if 35 <= _words(text) <= 145:
        score += 0.20
        reasons.append("usable spoken density")
    elif _words(text) < 20:
        score -= 0.25
        reasons.append("too little context")
    return max(0.0, min(1.0, score)), reasons


def select_candidates(transcript: dict[str, Any], min_seconds: float = 20.0, max_seconds: float = 60.0, limit: int = 10) -> list[dict[str, Any]]:
    segments = transcript.get("segments") or []
    if not segments:
        return []
    candidates: list[dict[str, Any]] = []
    for start_index, first in enumerate(segments):
        start = float(first.get("start", 0.0))
        text_parts: list[str] = []
        end = start
        for current in segments[start_index:]:
            end = float(current.get("end", end))
            text_parts.append(str(current.get("text") or "").strip())
            duration = end - start
            if duration >= min_seconds:
                if duration <= max_seconds:
                    score, reasons = _score_text(" ".join(text_parts))
                    candidates.append({
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "duration": round(duration, 3),
                        "text": " ".join(x for x in text_parts if x),
                        "score": round(score, 4),
                        "reasons": reasons,
                        "source_segment_start": start_index,
                        "source_segment_end": segments.index(current),
                    })
                else:
                    break
    candidates.sort(key=lambda x: (-x["score"], x["start"]))
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        overlaps = any(not (candidate["end"] <= chosen["start"] or candidate["start"] >= chosen["end"]) for chosen in selected)
        if not overlaps:
            candidate["rank"] = len(selected) + 1
            selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


__all__ = ["select_candidates"]
