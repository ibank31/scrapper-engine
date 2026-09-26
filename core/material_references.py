"""Reference extraction/classification for campaign materials.

The intake layer must distinguish actual source footage from examples,
inspiration links, documents, and symbolic/named references. Named references
may be resolved through bounded YouTube metadata search, but a search result is
never treated as an asset unless it passes deterministic title/publisher
verification.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from typing import Any, Callable
from urllib.parse import urlparse


URL_RE = re.compile(r'https?://[^\s<>\[\]{}"\']+', re.I)
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
ENTITY_STOPWORDS = {
    "official", "video", "music", "clip", "clips", "the", "a", "an",
    "officialvideo", "officialmusicvideo", "audio", "live", "hd", "hq",
}


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


def _entity_hints(value: str) -> list[str]:
    """Extract likely creator/artist tokens from a named media reference."""
    raw = str(value or "").strip()
    head = re.split(r"\s+-\s+|\s+by\s+|\s*[:|•]\s*", raw, maxsplit=1, flags=re.I)[0]
    tokens = [
        token for token in _normalized_tokens(head)
        if token not in ENTITY_STOPWORDS and len(token) >= 2
    ]
    return list(dict.fromkeys(tokens))


def _channel_similarity(value: str, channel: str) -> float:
    hints = _entity_hints(value)
    channel_tokens = set(_normalized_tokens(channel))
    if not hints or not channel_tokens:
        return 0.0
    overlap = len(set(hints) & channel_tokens) / len(set(hints))
    return round(overlap * 0.9, 4)


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


def classify_url(url: str, context: str = "") -> str:
    """Classify a URL using provider and surrounding evidence."""
    parsed = urlparse(str(url or ""))
    host = parsed.netloc.lower()
    suffix = parsed.path.lower().rsplit(".", 1)[-1] if "." in parsed.path else ""
    if suffix and f".{suffix}" in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}:
        return "PRIMARY_SOURCE"
    if "drive.google.com" in host and ("/file/" in parsed.path or "open" in parsed.path):
        return "PRIMARY_SOURCE"
    if any(host.endswith(domain) for domain in ("youtube.com", "youtu.be", "vimeo.com")):
        return "REFERENCE_ONLY" if any(term in str(context).lower() for term in REFERENCE_TERMS) else "PRIMARY_SOURCE_CANDIDATE"
    if "tiktok.com" in host or "genius.com" in host:
        return "REFERENCE_ONLY"
    return classify_context(context)


def extract_document_references(text: str) -> dict[str, list[dict[str, Any]]]:
    """Extract explicit URLs, named media references, and symbolic assets."""
    urls: list[dict[str, Any]] = []
    named: list[dict[str, Any]] = []
    symbolic: list[dict[str, Any]] = []
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
                "role": classify_url(url, line),
            })
        without_urls = URL_RE.sub("", line).strip(" -–—:：")
        match = NAMED_MEDIA_RE.match(without_urls)
        if not match:
            if is_symbolic_reference(line):
                symbolic.append({
                    "reference": line,
                    "line_number": line_number,
                    "context": line[:500],
                    "role": "PRIMARY_SOURCE_CANDIDATE",
                })
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
    return {"urls": urls, "named_media": named, "symbolic_assets": symbolic}


def is_symbolic_reference(value: str) -> bool:
    raw = str(value or "").strip().lower()
    if not raw or "://" in raw:
        return False
    return raw.startswith(SYMBOLIC_PREFIXES) or bool(re.fullmatch(r"[a-z][a-z0-9_-]{2,64}", raw)) and raw in {
        "brandasset", "watermarkasset", "logoasset", "campaignasset"
    }


def _candidate_url(entry: dict[str, Any]) -> str:
    video_id = str(entry.get("id") or "").strip()
    direct = str(entry.get("webpage_url") or entry.get("original_url") or "").strip()
    if direct:
        return direct
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _run_youtube_search(
    query: str,
    max_results: int,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[list[dict[str, Any]], str | None]:
    command = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist", "--dump-single-json", "--skip-download",
        "--no-warnings", f"ytsearch{max(1, int(max_results))}:{query}",
    ]
    try:
        completed = runner(command, check=False, text=True, capture_output=True, timeout=90)
        if completed.returncode != 0:
            return [], "youtube_search_failed"
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return [], "youtube_search_malformed_json"
    except Exception as exc:
        return [], f"youtube_search_error:{str(exc)[:160]}"
    return [item for item in (payload.get("entries") or []) if isinstance(item, dict)], None


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

    Search starts with the exact named reference. Campaign/brand context is a
    fallback query only, so unrelated campaign words cannot drown out the media
    title. Official references require either creator/channel evidence or a
    verified publisher plus a very strong title match.
    """
    value = str(value or "").strip()
    if not value:
        return {"status": "unresolved", "reason": "empty_reference", "query": ""}

    run_search = runner or subprocess.run
    fallback_parts = [value]
    if brand.strip():
        fallback_parts.append(brand.strip())
    if campaign_title.strip():
        fallback_parts.append(campaign_title.strip())
    queries = list(dict.fromkeys([value, " ".join(fallback_parts)]))
    queries = [query for query in queries if query.strip()]

    all_entries: list[dict[str, Any]] = []
    search_errors: list[str] = []
    winning_query = value
    for query in queries:
        entries, error = _run_youtube_search(query, max_results, run_search)
        if error:
            search_errors.append(error)
            continue
        winning_query = query
        all_entries.extend(entries)
        # The first search is intentionally preferred when it produces a strong
        # title match. Fallback is only needed when the exact search is weak.
        if entries:
            best_title = max((_similarity(value, str(e.get("title") or "")) for e in entries), default=0.0)
            if best_title >= max(0.90, float(min_similarity) + 0.12):
                break

    candidates_by_url: dict[str, dict[str, Any]] = {}
    official_reference = "official" in value.lower()
    for entry in all_entries:
        title = str(entry.get("title") or "").strip()
        url = _candidate_url(entry)
        if not title or not url:
            continue
        channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
        title_similarity = _similarity(value, title)
        channel_similarity = _channel_similarity(value, channel)
        channel_verified = bool(entry.get("channel_is_verified") or entry.get("uploader_is_verified"))
        official_hint = "official" in title.lower() or "official" in channel.lower()
        creator_match = channel_similarity >= 0.70
        item = {
            "url": url,
            "title": title,
            "channel": channel or None,
            "duration": entry.get("duration"),
            "view_count": entry.get("view_count"),
            "similarity": title_similarity,
            "channel_similarity": channel_similarity,
            "channel_verified": channel_verified,
            "creator_match": creator_match,
            "official_hint": official_hint,
        }
        existing = candidates_by_url.get(url)
        if not existing or (item["similarity"], item["channel_similarity"]) > (existing["similarity"], existing["channel_similarity"]):
            candidates_by_url[url] = item

    candidates = list(candidates_by_url.values())
    candidates.sort(
        key=lambda item: (
            -float(item["similarity"]),
            -float(item["channel_similarity"]),
            -int(bool(item["channel_verified"])),
            str(item["title"]).lower(),
        )
    )
    best = candidates[0] if candidates else None
    if not best:
        reason = search_errors[0] if search_errors else "no_youtube_match"
        return {"status": "unresolved", "reason": reason, "query": winning_query, "candidates": []}

    verified = float(best["similarity"]) >= float(min_similarity)
    if official_reference:
        official_title_threshold = max(float(min_similarity), 0.80)
        verified = (
            float(best["similarity"]) >= official_title_threshold
            and bool(best.get("official_hint"))
            and (
                bool(best.get("creator_match"))
                or (bool(best.get("channel_verified")) and float(best["similarity"]) >= 0.90)
            )
        )
    if not verified:
        return {
            "status": "unresolved",
            "reason": "youtube_match_below_verification_threshold",
            "query": winning_query,
            "best_candidate": best,
            "candidates": candidates[:3],
        }
    return {
        "status": "verified_candidate",
        "query": winning_query,
        "candidate": best,
        "candidates": candidates[:3],
    }


__all__ = [
    "URL_RE",
    "classify_context",
    "classify_url",
    "extract_document_references",
    "is_symbolic_reference",
    "resolve_named_youtube_reference",
]
