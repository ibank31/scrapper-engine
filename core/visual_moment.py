#!/usr/bin/env python3
"""Gemini multimodal keyframe check for top candidates.

Gemini actually looks at frames (start/middle/end of the candidate) and
returns a visual verdict. Advisory only: never changes timestamps, never
rejects, never raises.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from typing import Any

VISUAL_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "on_topic": {"type": "boolean"},
        "face_visible": {"type": "boolean"},
        "readable_text": {"type": "boolean"},
        "visual_notes": {"type": "string"},
    },
    "required": ["on_topic", "face_visible", "readable_text", "visual_notes"],
}

DEFAULT_FRAME_COUNT = int(os.environ.get("CLIPPER_VISUAL_FRAMES", "3"))


def _video_duration(path: str) -> float | None:
    try:
        raw = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            text=True, timeout=30,
        )
        return float(raw.strip())
    except Exception:
        return None


def extract_keyframes(video_path: str, start: float, end: float, count: int = DEFAULT_FRAME_COUNT, out_dir: str | None = None) -> list[str]:
    """Extract `count` evenly spaced JPEG frames from [start, end]."""
    if count < 1 or not os.path.exists(video_path):
        return []
    start, end = max(0.0, float(start)), max(0.0, float(end))
    if end <= start:
        return []
    duration = _video_duration(video_path)
    if duration:
        end = min(end, duration)
        if end <= start:
            return []
    own_dir = out_dir is None
    target = out_dir or tempfile.mkdtemp(prefix="clipper-frames-")
    os.makedirs(target, exist_ok=True)
    frames: list[str] = []
    try:
        for index in range(count):
            timestamp = start if count == 1 else start + (end - start) * index / (count - 1)
            if duration:
                timestamp = min(timestamp, max(start, duration - 0.05))
            frame_path = os.path.join(target, f"frame-{index:02d}.jpg")
            proc = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{timestamp:.3f}", "-i", video_path,
                 "-frames:v", "1", "-q:v", "4", frame_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            )
            if proc.returncode == 0 and os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                frames.append(frame_path)
    except Exception:
        return []
    return frames


def _generate_parts(parts: list[dict[str, Any]]) -> str:
    from core.campaign_ai import _gemini_generate_with_parts
    return _gemini_generate_with_parts(parts, VISUAL_VERDICT_SCHEMA, timeout=90)


def visual_verdict(frame_paths: list[str], campaign_context: str = "") -> dict[str, Any] | None:
    """Ask Gemini to look at the frames; return an advisory verdict or None."""
    existing = [path for path in frame_paths if os.path.exists(path)]
    if not existing:
        return None
    try:
        parts: list[dict[str, Any]] = [
            {"text": (
                "You are verifying frames from a short vertical video clip made for a reward campaign. "
                "Look at the frames and answer honestly. "
                f"Campaign context: {campaign_context or 'unspecified'}. "
                "Return JSON: on_topic (do the frames look relevant to the campaign context), "
                "face_visible (is a person's face clearly visible in any frame), "
                "readable_text (is there large readable on-screen text), "
                "visual_notes (one short sentence describing what you see)."
            )}
        ]
        for path in existing[:4]:
            with open(path, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode()
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": encoded}})
        parsed = json.loads(_generate_parts(parts))
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    verdict = {
        "on_topic": bool(parsed.get("on_topic")),
        "face_visible": bool(parsed.get("face_visible")),
        "readable_text": bool(parsed.get("readable_text")),
        "visual_notes": str(parsed.get("visual_notes") or "")[:300],
        "frames_examined": len(existing),
        "source": "gemini-vision",
    }
    return verdict
