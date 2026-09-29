#!/usr/bin/env python3
"""Hook-first clip timing: start padding to a word boundary and edge silence trimming.

Every adjusted boundary is derived from real word timestamps, never invented.
"""
from __future__ import annotations

from typing import Any

from core.captioning import clean_words


def candidate_words(transcript: dict, start: float, end: float) -> list[dict]:
    """All cleaned words overlapping [start, end], sorted by start time."""
    collected: list[dict] = []
    for segment in transcript.get("segments", []) or []:
        seg_start, seg_end = float(segment.get("start", 0)), float(segment.get("end", 0))
        if seg_end <= start or seg_start >= end:
            continue
        segment_words = segment.get("words") or []
        if not segment_words:
            continue
        for word in segment_words:
            ws, we = float(word.get("start", seg_start)), float(word.get("end", seg_end))
            if we > start and ws < end:
                collected.append({"start": ws, "end": we, "word": str(word.get("word", ""))})
    collected = clean_words(collected)
    collected.sort(key=lambda item: item["start"])
    return collected


def pad_hook_start(candidate: dict, transcript: dict, pad_seconds: float = 2.0, max_seconds: float | None = None) -> tuple[dict, dict]:
    """Move the clip start earlier by pad_seconds, snapped to a word boundary.

    Returns (adjusted_candidate, info). The original candidate is not mutated.
    """
    adjusted = dict(candidate)
    start = float(candidate.get("start", 0))
    info: dict[str, Any] = {"padded": False, "old_start": start, "new_start": start, "pad_seconds": pad_seconds}
    if pad_seconds <= 0:
        return adjusted, info
    words = candidate_words(transcript, 0.0, start)
    if not words:
        return adjusted, info
    target = max(0.0, start - pad_seconds)
    # Snap to the earliest word start at/after the target: never mid-word.
    options = [word["start"] for word in words if word["start"] >= target - 1e-6 and word["start"] < start - 1e-6]
    if not options:
        return adjusted, info
    new_start = min(options)
    if max_seconds is not None:
        end = float(candidate.get("end", start))
        min_start = end - max_seconds
        if new_start < min_start:
            # Keep duration within bounds: snap to the first word at/after min_start.
            bounded = [word["start"] for word in words if word["start"] >= min_start - 1e-6 and word["start"] < start - 1e-6]
            if not bounded:
                return adjusted, info
            new_start = min(bounded)
    if new_start >= start - 1e-6:
        return adjusted, info
    adjusted["start"] = round(new_start, 3)
    adjusted["duration"] = round(float(candidate.get("end", start)) - new_start, 3)
    info.update({"padded": True, "new_start": adjusted["start"]})
    return adjusted, info


def trim_silence_edges(candidate: dict, transcript: dict) -> tuple[dict, dict]:
    """Tighten clip edges to the first/last spoken word inside the window."""
    adjusted = dict(candidate)
    start = float(candidate.get("start", 0))
    end = float(candidate.get("end", start))
    info: dict[str, Any] = {"trimmed": False, "old_start": start, "old_end": end}
    words = candidate_words(transcript, start, end)
    if not words:
        return adjusted, info
    new_start = max(start, words[0]["start"])
    new_end = min(end, words[-1]["end"])
    if new_start <= start + 1e-6 and new_end >= end - 1e-6:
        return adjusted, info
    adjusted["start"] = round(new_start, 3)
    adjusted["end"] = round(new_end, 3)
    adjusted["duration"] = round(new_end - new_start, 3)
    info.update({"trimmed": True, "new_start": adjusted["start"], "new_end": adjusted["end"]})
    return adjusted, info
