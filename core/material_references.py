"""Reference extraction/classification for campaign materials.

The intake layer must distinguish actual source footage from examples,
inspiration links, documents, and symbolic/named references. Named references
can optionally be resolved through a bounded YouTube metadata search, but a
search result is never treated as an asset unless it passes deterministic
title/role verification.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from typing import Any, Callable
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://[^\s<>\[\]{}"']+", re.I)
NAMED_MEDIA_RE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z0-9 _/.-]{1,80})\s*[:：-]\s*(?P<value>[^\n]{2,240})$",
    re.I,
)
PRIMARY_TERMS = (
    "official video", "music video", "source video", "video source",
    "raw footage", "raw asset", "provided clip", "content bank",
    "campaign video", "source", "footage", "video",
)
REFERENCE_TERMS = (
    "example", "examples", "reference", "references", "inspiration",
    "inspo", "sample", "competitor", "similar", "tiktok examples",
)
SYMBOLIC_PREFIXES = ("brandasset", "brand_asset", "watermark", "logo", "asset:")


def clean_url(value: str) -> str:
    return str(value or "").rstrip(".,;:!?)]}")


def _normalized_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(value or "").lower())


def _similarity(query: str, title: str) -> float:
    q = " ".join(_normalized_tokens(query))
    t = " ".join(_normalized_tokens(title))
    if not q or not t:
        return 0.0
    sequence = SequenceMatcher(None, q, t).ratio()
    q_tokens = set(_normalized_tokens(query))
    t_tokens = set(_normalized_tokens(title))
    overlap = len(q_tokens & t_tokens) / max(1, len(q_tokens))
    return round(max(sequence, overlap * 0.9), 4)


def classify_context(text: str, *, explicit_source: bool = False) -> str:
    """Classify a URL/named reference without treating examples as footage."""
    context = " ".join(str(text or "").lower().split())
    if explicit_source:
        return "PRIMARY_SOURCE"
    if any(term in context for term in REFERENCE_TERMS):
        return "REFERENCE_ONLY"
    if any(term in context for term in PRIMARY_TERMS):
        return "PRIMARY_SOURCE_CANDIDATE"
    return "AMBIGUOUS_REFERENCE"


def extract_document_references(text: str) -> dict[str, list[dict[str, Any]]]:
    """Extract explicit URLs and named media references with line evidence."""
    urls: list[dict[str, Any]] = []
    named: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(str(text or "").splitlines(), 1):
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        line_urls = [clean_url(item) for item in URL_RE.findall(line)]
        for url in line_urls:
            urls.append({
                "url": url,
                "line_number": line_number,
                "context": line[:500],
                "role": classify_context(line),
            })
        without_urls = URL_RE.sub("", line).strip(" -–—:：")
        match = NAMED_MEDIA_RE.match(without_urls)
        if not match:
            continue
        label = str(match.group("label") or "").strip()
        value = str(match.group("value") or "").strip()
        label_context = f"{label}: {value}"
        role = classify_context(label_context)
        if role != "PRIMARY_SOURCE_CANDIDATE":
            continue
        named.append({
            "label": label,
            "value": value,
            "line_number": line_number,
            "context": label_context[:500],
            "role": role,
        })
    return {"urls": urls, "named_media": named}


def is_symbolic_reference(value: str) -> bool:
    raw = str(value or "").strip().lower()
    if not raw or "://" in raw:
        return False
    return raw.startswith(SYMBOLIC_PREFIXES) or bool(re.fullmatch(r"[a-z][a-z0-9_-]{2,64}", raw)) and raw.lower() in {
        "brandasset", "watermarkasset", "logoasset", "campaignasset"
    }


def _candidate_url(entry: dict[str, Any]) -> str:
    video_id = str(entry.get("id") or "").strip()
    direct = str(entry.get("webpage_url") or entry.get("original_url") or "").strip()
    if direct:
        return direct
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def resolve_named_youtube_reference(
    value: str,
    *,
    campaign_title: str = "",
    brand: str = "",
    max_results: int = 5,
    min_similarity: float = 0.72,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Resolve a named video reference to a verified YouTube candidate.

    This is deliberately metadata-only. The returned candidate is still a
    source candidate and can enter the normal access/download gates afterward.
    """
    query_parts = [str(value or "").strip(), str(brand or "").strip(), str(campaign_title or "").strip()]
    query = " ".join(part for part in query_parts if part)
    if not query.strip():
        return {"status": "unresolved", "reason": "empty_reference", "query": ""}

    command = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist", "--dump-single-json", "--skip-download",
        "--no-warnings", f"ytsearch{max(1, int(max_results))}:{query}",
    ]
    try:
        completed = (runner or subprocess.run)(
            command, check=False, text=True, capture_output=True, timeout=90
        )
        if completed.returncode != 0:
            return {"status": "unresolved", "reason": "youtube_search_failed", "query": query}
        payload = json.loads(completed.stdout or "{}")
    except Exception as exc:
        return {"status": "unresolved", "reason": f"youtube_search_error:{str(exc)[:160]}", "query": query}

    entries = [item for item in (payload.get("entries") or []) if isinstance(item, dict)]
    candidates = []
    for entry in entries:
        title = str(entry.get("title") or "").strip()
        url = _candidate_url(entry)
        if not title or not url:
            continue
        similarity = _similarity(value, title)
        official_hint = "official" in value.lower() or "official" in title.lower()
        candidates.append({
            "url": url,
            "title": title,
            "channel": entry.get("channel") or entry.get("uploader"),
            "duration": entry.get("duration"),
            "view_count": entry.get("view_count"),
            "similarity": similarity,
            "official_hint": official_hint,
        })

    candidates.sort(key=lambda item: (-float(item["similarity"]), str(item["title"]).lower()))
    best = candidates[0] if candidates else None
    if not best:
        return {"status": "unresolved", "reason": "no_youtube_match", "query": query, "candidates": []}

    verified = float(best["similarity"]) >= float(min_similarity)
    if "official" in value.lower() and not best.get("official_hint"):
        verified = False
    if not verified:
        return {
            "status": "unresolved",
            "reason": "youtube_match_below_verification_threshold",
            "query": query,
            "best_candidate": best,
            "candidates": candidates[:3],
        }
    return {
        "status": "verified_candidate",
        "query": query,
        "candidate": best,
        "candidates": candidates[:3],
    }


__all__ = [
    "URL_RE",
    "classify_context",
    "extract_document_references",
    "is_symbolic_reference",
    "resolve_named_youtube_reference",
]
