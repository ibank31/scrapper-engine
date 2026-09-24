"""Explicit subtitle delivery profiles and artifact evidence."""
from __future__ import annotations

import hashlib
import json
from typing import Any

PROFILE_VERSION = "subtitle-delivery-v1"
MODES = {"burned_in", "native_caption_file", "none", "manual_required"}


def resolve_subtitle_profile(profile: str | None, *, transcript_available: bool, required: bool = False) -> dict[str, Any]:
    mode = str(profile or ("burned_in" if required or transcript_available else "manual_required"))
    if mode not in MODES:
        mode = "manual_required"
    compliant = transcript_available if mode in {"burned_in", "native_caption_file"} else (not required if mode == "none" else False)
    return {"version": PROFILE_VERSION, "mode": mode, "transcript_available": bool(transcript_available), "required": bool(required), "compliant": compliant, "typography": {"font": "DejaVu Sans", "size": 50, "outline": 3}, "safe_area": {"top": 80, "bottom": 670, "left": 80, "right": 80}, "cue_limits": {"max_words": 4, "max_chars": 28}, "language": "und", "artifact_hash": None}


def attach_artifact_hash(profile: dict[str, Any], artifact: bytes | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(artifact, bytes):
        payload = artifact
    elif isinstance(artifact, str):
        payload = artifact.encode("utf-8")
    else:
        payload = json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result = dict(profile)
    result["artifact_hash"] = hashlib.sha256(payload).hexdigest()
    return result


__all__ = ["MODES", "PROFILE_VERSION", "attach_artifact_hash", "resolve_subtitle_profile"]
