#!/usr/bin/env python3
"""Deterministic, auditable highlight candidate scoring."""
from __future__ import annotations

import re
from typing import Any

from core.candidate_identity import annotate_candidate
from core.media_signals import candidate_signals, media_score_adjustment, source_quality_preflight
from core.production_policy import enrich_candidate

HOOKS = ("how", "why", "what", "the truth", "nobody", "most people", "the biggest", "here's", "here is", "mistake", "secret")
SIGNALS = ("because", "but", "however", "instead", "first", "finally", "million", "percent", "%", "$", "step", "lesson", "problem", "solution")
MID_THOUGHT_STARTS = ("and", "but", "so", "because", "they", "they're", "it", "this", "that", "which", "to")
PAYOFF_TERMS = ("so", "therefore", "that means", "the lesson", "in the end", "finally", "which is why", "the answer")


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


def _score_structure(text: str, duration: float) -> tuple[float, list[str]]:
    """Reward clips that feel complete instead of merely containing keywords."""
    stripped = " ".join((text or "").split())
    lower = stripped.lower()
    first_word = re.sub(r"[^a-z']", "", lower.split()[0]) if lower.split() else ""
    score = 0.0
    reasons: list[str] = []
    if first_word in MID_THOUGHT_STARTS:
        score -= 0.20
        reasons.append("starts mid-thought")
    if re.search(r"[.!?]", stripped[:140]) or first_word in HOOKS:
        score += 0.08
        reasons.append("clear opening beat")
    if re.search(r"[.!?]$", stripped):
        score += 0.10
        reasons.append("complete ending")
    if re.search(r"\b(?:" + "|".join(re.escape(term) for term in PAYOFF_TERMS) + r")\b", lower):
        score += 0.10
        reasons.append("payoff or takeaway")
    if 28 <= duration <= 48:
        score += 0.12
        reasons.append("short-form sweet spot")
    elif duration > 55:
        score -= 0.06
        reasons.append("longer than preferred")
    if stripped.count("?") >= 2:
        score -= 0.06
        reasons.append("too many open questions")
    return score, reasons


def _boundary_quality(text: str) -> tuple[float, list[str]]:
    """Score whether the transcript window has usable sentence boundaries."""
    stripped = " ".join((text or "").split())
    if not stripped:
        return -0.2, ["empty transcript window"]
    score = 0.0
    reasons: list[str] = []
    if re.search(r"[.!?]$", stripped):
        score += 0.12
        reasons.append("complete ending")
    else:
        score -= 0.12
        reasons.append("unfinished ending")
    if len(stripped.split()) >= 35:
        score += 0.08
        reasons.append("enough context")
    return score, reasons


def segment_transcript(transcript: dict[str, Any], max_unit_seconds: float | None = None) -> list[dict[str, Any]]:
    """Build sentence/turn units while preserving Whisper timestamps.

    Word timestamps are preferred. A long pause or terminal punctuation closes a
    unit; when word timestamps are absent, Whisper segments remain the fallback.
    """
    segments = transcript.get("segments") or []
    units: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_start = None
    current_segment_start = None
    previous_end = None

    def flush() -> None:
        nonlocal current, current_start, current_segment_start, previous_end
        if current:
            text = " ".join(str(item.get("word") or item.get("text") or "").strip() for item in current).strip()
            text = re.sub(r"\s+([,.!?])", r"\1", text)
            if text and current_start is not None:
                units.append({
                    "start": round(float(current_start), 3),
                    "end": round(float(current[-1].get("end", previous_end or current_start)), 3),
                    "text": text,
                    "source_segment_start": current_segment_start,
                    "source_segment_end": current[-1].get("_segment_index", current_segment_start),
                })
        current = []
        current_start = None
        current_segment_start = None

    for segment_index, segment in enumerate(segments):
        words = segment.get("words") or []
        if not words:
            item = {"text": str(segment.get("text") or "").strip(), "start": segment.get("start", 0), "end": segment.get("end", 0), "_segment_index": segment_index}
            if item["text"]:
                if current and max_unit_seconds and current_start is not None and float(item["start"]) - float(current_start) >= float(max_unit_seconds):
                    flush()
                elif current and previous_end is not None and float(item["start"]) - previous_end > 1.2:
                    flush()
                if current_start is None:
                    current_start = float(item["start"])
                    current_segment_start = segment_index
                current.append(item)
                previous_end = float(item["end"])
                if re.search(r"[.!?][\"']?$", item["text"]):
                    flush()
            continue
        for word in words:
            token = str(word.get("word") or "").strip()
            if not token:
                continue
            start = float(word.get("start", segment.get("start", 0)))
            end = float(word.get("end", start))
            if current and max_unit_seconds and current_start is not None and start - float(current_start) >= float(max_unit_seconds):
                flush()
            elif current and previous_end is not None and start - previous_end > 1.2:
                flush()
            if current_start is None:
                current_start = start
                current_segment_start = segment_index
            item = dict(word, word=token, _segment_index=segment_index)
            current.append(item)
            previous_end = end
            if re.search(r"[.!?][\"']?$", token) and len(current) >= 3:
                flush()
    flush()
    return units


def _visual_fallback_candidates(
    transcript: dict[str, Any],
    min_seconds: float,
    max_seconds: float,
    limit: int,
    source_path: str,
    plan: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Create bounded visual candidates when speech is absent or unusable.

    Speech is not a universal requirement for clipping. Music, sports, gaming,
    reaction and montage campaigns can still have valid visual moments. This
    fallback is disabled when subtitles are explicitly required.
    """
    production = (plan or {}).get("production") or {}
    if production.get("subtitle_required") is True:
        return []
    quality = source_quality_preflight(source_path, transcript)
    total_duration = float(quality.get("duration_seconds") or 0)
    if total_duration < max(0.75, float(min_seconds)):
        return []
    upper = min(float(max_seconds), total_duration)
    lower = max(0.75, float(min_seconds))
    if upper < lower:
        return []
    target = min(upper, max(lower, 30.0))
    if target < lower:
        target = upper
    if target <= 0:
        return []
    max_start = max(0.0, total_duration - target)
    starts = [0.0, max_start * 0.33, max_start * 0.66, max_start]
    candidates: list[dict[str, Any]] = []
    seen_starts: set[float] = set()
    for start in starts:
        start = round(max(0.0, min(max_start, float(start))), 3)
        if start in seen_starts:
            continue
        seen_starts.add(start)
        end = round(start + target, 3)
        item = {
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "text": "",
            "score": 0.25,
            "reasons": ["visual fallback: transcript tidak menyediakan jendela bicara lengkap"],
            "source_segment_start": None,
            "source_segment_end": None,
        }
        item["source_quality"] = quality
        item["media_signals"] = candidate_signals(source_path, item, transcript)
        adjustment, signal_reasons = media_score_adjustment(item["media_signals"])
        item["media_score_adjustment"] = adjustment
        item["score"] = round(max(0.0, min(1.0, item["score"] + adjustment)), 4)
        item["reasons"].extend(signal_reasons)
        item = enrich_candidate(item, plan)
        item = annotate_candidate(
            item,
            source_path,
            quality.get("duplicate_hash"),
            transcript,
            plan,
        )
        item["reasons"].extend(item.get("production_quality_reasons") or [])
        candidates.append(item)
    candidates.sort(key=lambda item: (-float(item.get("score") or 0), float(item.get("start") or 0)))
    for rank, item in enumerate(candidates[:max(1, int(limit))], 1):
        item["rank"] = rank
    return candidates[:max(1, int(limit))]


def select_candidates(transcript: dict[str, Any], min_seconds: float = 20.0, max_seconds: float = 60.0, limit: int = 10, source_path: str | None = None, max_gap_seconds: float = 3.0, plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    # Keep transcript units bounded by the active editorial band. This matters
    # for Whisper output that contains long punctuation-free runs: without a
    # bound, one giant unit can exceed every campaign duration band and produce
    # zero candidates even though usable speech exists inside it.
    units = segment_transcript(transcript, max_unit_seconds=max_seconds)
    candidates: list[dict[str, Any]] = []
    source_quality = source_quality_preflight(source_path, transcript) if source_path else None
    for start_index, first in enumerate(units):
        start = float(first.get("start", 0.0))
        text_parts: list[str] = []
        end = start
        for end_index, current in enumerate(units[start_index:], start_index):
            if end_index > start_index:
                gap = float(current.get("start", end)) - end
                if gap > max_gap_seconds:
                    break
            end = float(current.get("end", end))
            text_parts.append(str(current.get("text") or "").strip())
            duration = end - start
            if duration >= min_seconds:
                if duration <= max_seconds:
                    text = " ".join(x for x in text_parts if x)
                    score, reasons = _score_text(text)
                    structure_score, structure_reasons = _score_structure(text, duration)
                    boundary_score, boundary_reasons = _boundary_quality(text)
                    score = max(0.0, min(1.0, score + structure_score + boundary_score))
                    reasons.extend(structure_reasons)
                    reasons.extend(boundary_reasons)
                    item = {
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "duration": round(duration, 3),
                        "text": text,
                        "score": round(score, 4),
                        "reasons": reasons,
                        "source_segment_start": first.get("source_segment_start", start_index),
                        "source_segment_end": current.get("source_segment_end", end_index),
                        "unit_start": start_index,
                        "unit_end": end_index,
                    }
                    if source_quality:
                        item["source_quality"] = source_quality
                        item["media_signals"] = candidate_signals(source_path, item, transcript)
                        adjustment, signal_reasons = media_score_adjustment(item["media_signals"])
                        item["media_score_adjustment"] = adjustment
                        item["score"] = round(max(0.0, min(1.0, item["score"] + adjustment)), 4)
                        item["reasons"].extend(signal_reasons)
                    item = enrich_candidate(item, plan)
                    item = annotate_candidate(
                        item,
                        source_path,
                        (source_quality or {}).get("duplicate_hash") if source_quality else None,
                        transcript,
                        plan,
                    )
                    item["reasons"].extend(item.get("production_quality_reasons") or [])
                    candidates.append(item)
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
    if selected:
        return selected
    if source_path and plan is not None:
        return _visual_fallback_candidates(transcript, min_seconds, max_seconds, limit, source_path, plan)
    return []


def _candidate_tokens(candidate: dict[str, Any]) -> set[str]:
    return set(re.findall(r"[a-z0-9$%]+", str(candidate.get("text") or "").lower()))


def candidates_are_near_duplicates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Detect previews that would look the same to a human reviewer."""
    if str(left.get("source") or "") != str(right.get("source") or ""):
        return False
    left_start, left_end = float(left.get("start") or 0), float(left.get("end") or 0)
    right_start, right_end = float(right.get("start") or 0), float(right.get("end") or 0)
    intersection = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    shortest = max(0.001, min(left_end - left_start, right_end - right_start))
    if intersection / shortest >= 0.45:
        return True
    left_tokens, right_tokens = _candidate_tokens(left), _candidate_tokens(right)
    if left_tokens and right_tokens:
        similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
        if similarity >= 0.82 and abs((left_end - left_start) - (right_end - right_start)) <= 12:
            return True
    return False


def select_distinct_candidates(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Keep high-scoring candidates while preventing duplicate-looking previews."""
    selected: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda x: (-float(x.get("score") or 0), float(x.get("start") or 0))):
        if any(candidates_are_near_duplicates(item, chosen) for chosen in selected):
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


__all__ = ["segment_transcript", "select_candidates", "candidates_are_near_duplicates", "select_distinct_candidates"]
