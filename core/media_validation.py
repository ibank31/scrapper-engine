"""Cheap, deterministic validation of downloaded media before expensive analysis.

This module is intentionally provider-neutral. A file is not considered a usable
video asset merely because its extension says .mp4. We probe the actual streams
before the worker spends time on Whisper, semantic ranking, or rendering.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def validate_video_file(path: str | Path, *, min_duration_seconds: float = 1.5) -> dict[str, Any]:
    """Return a structured, auditable media validation result.

    The check is deliberately cheap: file existence/size plus one ffprobe call.
    It verifies a real video stream, an audio stream, and a minimum duration.
    """
    target = Path(path)
    result: dict[str, Any] = {
        "schema_version": 1,
        "path": str(target),
        "status": "fail",
        "exists": target.is_file(),
        "bytes": target.stat().st_size if target.is_file() else 0,
        "has_video": False,
        "has_audio": False,
        "duration_seconds": 0.0,
        "video_codec": None,
        "audio_codec": None,
        "width": None,
        "height": None,
        "container": None,
        "issues": [],
    }
    if not target.is_file():
        result["issues"].append("file_missing")
        return result
    if result["bytes"] <= 0:
        result["issues"].append("empty_file")
        return result
    if target.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        result["issues"].append("unsupported_video_extension")
        return result

    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(completed.stdout or "{}")
    except Exception as exc:
        result["issues"].append(f"ffprobe_failed:{str(exc)[:180]}")
        return result

    streams = payload.get("streams") or []
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = payload.get("format") or {}
    result["container"] = fmt.get("format_name")
    result["has_video"] = bool(videos)
    result["has_audio"] = bool(audios)

    if videos:
        video = videos[0]
        result["video_codec"] = video.get("codec_name")
        result["width"] = int(video.get("width") or 0) or None
        result["height"] = int(video.get("height") or 0) or None
    else:
        result["issues"].append("video_stream_missing")

    if audios:
        result["audio_codec"] = audios[0].get("codec_name")
    else:
        result["issues"].append("audio_stream_missing")

    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    result["duration_seconds"] = round(max(0.0, duration), 3)
    if duration < float(min_duration_seconds):
        result["issues"].append(f"duration_below_minimum:{float(min_duration_seconds):g}")

    if result["has_video"] and result["has_audio"] and duration >= float(min_duration_seconds):
        result["status"] = "pass"
    return result


__all__ = ["SUPPORTED_VIDEO_EXTENSIONS", "validate_video_file"]
