#!/usr/bin/env python3
"""Optional, local media-quality signals for candidate review metadata."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


def _run(command: list[str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def _probe(path: str) -> dict[str, Any]:
    result = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    return json.loads(result.stdout or "{}")


def _sha256(path: str, chunk_size: int = 1024 * 1024) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def source_quality_preflight(path: str, transcript: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return auditable source checks before candidate generation."""
    result: dict[str, Any] = {"schema_version": 1, "path": os.path.basename(path)}
    try:
        data = _probe(path)
        streams = data.get("streams", [])
        video = next((x for x in streams if x.get("codec_type") == "video"), {})
        audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
        duration = float((data.get("format") or {}).get("duration") or 0)
        width, height = int(video.get("width") or 0), int(video.get("height") or 0)
        text = " ".join(str(x.get("text") or "") for x in (transcript or {}).get("segments", []))
        words = len(re.findall(r"\b\w+\b", text))
        speech_density = round(words / duration, 3) if duration > 0 and transcript else None
        lowered = text.lower()
        sponsor_terms = ("sponsored by", "brought to you by", "use code", "promo code", "visit our sponsor", "paid partnership")
        result.update({
            "available": True,
            "duration_seconds": round(duration, 3),
            "has_audio": bool(audio),
            "speech_density_words_per_second": speech_density,
            "resolution": {"width": width, "height": height},
            "resolution_class": "hd" if min(width, height) >= 720 else "low",
            "duplicate_hash": _sha256(path),
            "possible_bumper_or_sponsor_only": bool(text and len(text.split()) < 45 and any(term in lowered for term in sponsor_terms)),
            "audio_codec": (audio or {}).get("codec_name"),
        })
        if not audio:
            result["warnings"] = ["audio_missing"]
        return result
    except Exception as exc:
        result.update(_unavailable(f"probe_failed: {type(exc).__name__}"))
        return result


def _silence_signal(path: str, start: float, duration: float) -> dict[str, Any]:
    if duration <= 0:
        return _unavailable("invalid_candidate_duration")
    try:
        result = _run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}", "-i", path, "-af", "silencedetect=noise=-35dB:d=0.35", "-f", "null", "-"], timeout=90)
        log = result.stderr or ""
        total = sum(float(x) for x in re.findall(r"silence_duration:\s*([0-9.]+)", log))
        ratio = min(1.0, total / duration)
        return {"available": True, "silence_ratio": round(ratio, 3), "silence_events": len(re.findall(r"silence_start", log)), "voice_activity_ratio": round(1.0 - ratio, 3)}
    except Exception as exc:
        return _unavailable(f"silence_probe_failed: {type(exc).__name__}")


def _scene_signal(path: str, start: float, duration: float) -> dict[str, Any]:
    try:
        result = _run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}", "-i", path, "-vf", "select='gt(scene,0.25)',showinfo", "-an", "-f", "null", "-"], timeout=90)
        count = len(re.findall(r"showinfo", result.stderr or ""))
        return {"available": True, "scene_change_count": count, "scene_change_score": round(min(1.0, count / max(1.0, duration / 8.0)), 3)}
    except Exception as exc:
        return _unavailable(f"scene_probe_failed: {type(exc).__name__}")


def _speaker_signal(candidate: dict[str, Any], transcript: dict[str, Any] | None) -> dict[str, Any]:
    labels: list[str] = []
    durations: dict[str, float] = {}
    for segment in (transcript or {}).get("segments", []):
        if float(segment.get("end", 0) or 0) <= float(candidate.get("start", 0) or 0) or float(segment.get("start", 0) or 0) >= float(candidate.get("end", 0) or 0):
            continue
        label = segment.get("speaker") or segment.get("speaker_id")
        if label is not None:
            key = str(label)
            labels.append(key)
            durations[key] = durations.get(key, 0.0) + max(0.0, float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0))
    distinct = list(dict.fromkeys(labels))
    if len(distinct) < 2:
        return {"available": bool(distinct), "speaker_count": len(distinct), "confidence": 0.0, "framing_recommendation": "default"}
    dominance = max(durations.values()) / max(0.001, sum(durations.values()))
    confidence = round(min(0.99, 0.45 + 0.5 * dominance), 3)
    return {"available": True, "speaker_count": len(distinct), "speakers": distinct, "dominant_speaker": max(durations, key=durations.get), "confidence": confidence, "framing_recommendation": "speaker-focused" if confidence >= 0.8 else "wide-two-speaker"}


def candidate_signals(path: str | None, candidate: dict[str, Any], transcript: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute advisory candidate signals; never raises into the clipping path."""
    active = _speaker_signal(candidate, transcript)
    if not path or not Path(path).exists():
        return {"schema_version": 1, "available": False, "reason": "source_unavailable", "active_speaker": active}
    start, duration = float(candidate.get("start") or 0), float(candidate.get("duration") or 0)
    return {"schema_version": 1, "available": True, "silence_voice_activity": _silence_signal(path, start, duration), "scene_change": _scene_signal(path, start, duration), "active_speaker": active}


__all__ = ["candidate_signals", "source_quality_preflight"]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--transcript")
    args = parser.parse_args()
    transcript = json.load(open(args.transcript, encoding="utf-8")) if args.transcript else None
    print(json.dumps(source_quality_preflight(args.source, transcript), indent=2))
