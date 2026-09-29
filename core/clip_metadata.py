#!/usr/bin/env python3
"""Generate English per-clip metadata (title, caption, CTA, hashtags) with Gemini.

Used for the chat review step: each finished clip gets a ready-to-post text
package in English. Generation never raises; failures return None.
"""
from __future__ import annotations

import json
import re
from typing import Any

METADATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "caption": {"type": "string"},
        "cta": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "hook_text": {"type": "string"},
    },
    "required": ["title", "caption", "cta", "hashtags"],
}

MAX_HASHTAGS = 5
MAX_TITLE_CHARS = 60


def _generate(prompt: str) -> str:
    from core.campaign_ai import _gemini_generate_with_schema
    return _gemini_generate_with_schema(prompt, METADATA_SCHEMA, timeout=60)


def _clean_hashtag(tag: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", tag or "").lower()
    return cleaned[:30]


def generate_clip_metadata(candidate: dict, campaign_name: str = "") -> dict[str, Any] | None:
    """Return normalized English metadata for one clip, or None on any failure."""
    text = str(candidate.get("text") or "").strip()
    if not text:
        return None
    hook = str(candidate.get("hook_sentence") or "").strip()
    prompt = (
        "You write English social-media metadata for a short vertical video clip. "
        "Be concrete and specific to the transcript; never invent facts, numbers, or claims "
        "that are not in the transcript. No emojis. No hashtags inside the caption text. "
        f"Campaign context: {campaign_name or 'unspecified'}. "
        "Clip transcript:\n" + text + "\n"
        "Return JSON with: title (at most 60 characters, punchy, no clickbait lies), "
        "caption (2 short sentences in English summarizing the clip), "
        "cta (one short call to action in English), "
        "hashtags (exactly 5 single-word lowercase English hashtags, no # symbol), "
        "hook_text (the opening line, copied from the transcript)."
    )
    try:
        raw = _generate(prompt)
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    title = str(parsed.get("title") or hook or text[:60]).strip()[:MAX_TITLE_CHARS]
    caption = str(parsed.get("caption") or "").strip()
    cta = str(parsed.get("cta") or "").strip()
    tags = [_clean_hashtag(tag) for tag in (parsed.get("hashtags") or []) if isinstance(tag, str)]
    tags = [tag for tag in tags if tag][:MAX_HASHTAGS]
    hook_text = str(parsed.get("hook_text") or hook or "").strip()
    if not title or not caption:
        return None
    return {
        "title": title,
        "caption": caption,
        "cta": cta,
        "hashtags": tags,
        "hook_text": hook_text,
        "source": "gemini",
    }
