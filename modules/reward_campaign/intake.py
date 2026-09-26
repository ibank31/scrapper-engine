#!/usr/bin/env python3
"""Harvest campaign rules and publicly authorized media into an auditable workspace."""
from __future__ import annotations

import argparse
import json
import os
import re
import math
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.fetch import DEFAULT_HEADERS, FetchError, fetch_bytes
from core.google_drive import (
    configured as google_drive_configured,
    discover_folder_oauth,
    download_asset_oauth,
    download_file_oauth,
)
from core.google_sheets import GoogleSheetError, discover_sheet_assets, fetch_sheet_rows, is_google_sheet_url
from core.job_workspace import create_workspace, now_iso, read_json, sha256_file, write_json
from core.candidate_identity import normalize_source_asset_id
from core.material_references import extract_document_references, is_symbolic_reference, resolve_named_youtube_reference
from core.media_validation import validate_video_file
from core.material_planner import match_candidate, required_asset_minimums

DIRECT_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".wav", ".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".webp", ".srt", ".ass"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
URL_RE = re.compile(r"https?://[^\s<>\]\)\"]+", re.I)
# Kept only for CLI compatibility. Intake never uses this as a discovery cap.
MAX_VIDEO_SOURCES = 0
DEFAULT_DOWNLOAD_MAX_ASSETS = 8
DEFAULT_DOWNLOAD_MAX_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_DISK_SAFETY_MARGIN = 1024 * 1024 * 1024
DEFAULT_UNKNOWN_DOWNLOAD_RESERVE = 800 * 1024 * 1024
POSITIVE_NAME_HINTS = ("master", "final", "source", "original", "clean", "1080", "2160", "4k", "hq")
NEGATIVE_NAME_HINTS = ("proxy", "preview", "thumb", "thumbnail", "lowres", "low-res", "watermark", "bumper", "intro", "sample")


def _resolve_symbolic_asset(plan: dict, reference: str) -> tuple[str | None, dict]:
    """Resolve a symbolic asset only from explicit campaign mappings; never invent a URL."""
    key = str(reference or "").strip().lower().replace("-", "_").replace(" ", "_")
    production = plan.get("production") or {}
    campaign = plan.get("campaign") or {}
    containers = [
        production.get("asset_mappings"), production.get("symbolic_assets"),
        production.get("assets"), production.get("brand_assets"),
        campaign.get("asset_mappings"), campaign.get("assets"),
    ]
    for container in containers:
        if isinstance(container, dict):
            for candidate_key in (reference, key):
                value = container.get(candidate_key)
                if isinstance(value, str) and value.strip():
                    return value.strip(), {"mapping_source": "campaign_plan", "mapping_key": candidate_key}
                if isinstance(value, dict):
                    url = value.get("url") or value.get("source_url")
                    if isinstance(url, str) and url.strip():
                        return url.strip(), {"mapping_source": "campaign_plan", "mapping_key": candidate_key}
        elif isinstance(container, list):
            for item in container:
                if not isinstance(item, dict):
                    continue
                item_key = str(item.get("name") or item.get("key") or item.get("id") or "").strip().lower().replace("-", "_").replace(" ", "_")
                if item_key != key:
                    continue
                url = item.get("url") or item.get("source_url")
                if isinstance(url, str) and url.strip():
                    return url.strip(), {"mapping_source": "campaign_plan", "mapping_key": item_key}
    return None, {"mapping_source": None, "mapping_key": key}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _download_guard(destination: str, required_size: int = 0, safety_margin: int | None = None) -> tuple[str, str | None]:
    """Protect the runner before every source download, including YouTube/direct URLs."""
    free_bytes = shutil.disk_usage(Path(destination).parent).free
    required = max(0, int(required_size))
    if required <= 0:
        required = max(512 * 1024 * 1024, _env_int("CLIPPER_UNKNOWN_DOWNLOAD_RESERVE", DEFAULT_UNKNOWN_DOWNLOAD_RESERVE))
    required = int(required * 1.10)
    margin = max(0, int(safety_margin if safety_margin is not None else _env_int("CLIPPER_DISK_SAFETY_MARGIN", DEFAULT_DISK_SAFETY_MARGIN)))
    if free_bytes < required + margin:
        return "deferred", "DEFERRED_DISK_BUDGET"
    return "ready", None


def _name_priority(name: str) -> float:
    lowered = str(name or "").lower()
    return sum(4.0 for token in POSITIVE_NAME_HINTS if token in lowered) - sum(7.0 for token in NEGATIVE_NAME_HINTS if token in lowered)


def _asset_priority(item: dict) -> tuple[float, str]:
    """Cheap deterministic ranking using metadata only, before any download."""
    mime = str(item.get("mimeType") or "").lower()
    name = str(item.get("name") or "")
    video_meta = item.get("videoMediaMetadata") or {}
    width = int(video_meta.get("width") or 0)
    height = int(video_meta.get("height") or 0)
    duration = float(video_meta.get("durationMillis") or 0) / 1000.0
    size_bytes = int(item.get("size") or 0)
    pixels = width * height
    resolution_score = min(40.0, pixels / 50000.0) if pixels else 0.0
    duration_score = min(18.0, duration / 10.0) if duration >= 8 else 0.0
    size_score = min(12.0, math.log2(max(1, size_bytes) / (64 * 1024 * 1024) + 1) * 4.0)
    mime_score = 20.0 if mime.startswith("video/") else 0.0
    tracker = item.get("priority") or ()
    tracker_score = 0.0
    for index, value in enumerate(tracker):
        try:
            tracker_score += float(value or 0) * (4.0 / (index + 1))
        except (TypeError, ValueError):
            continue
    base_priority = float(item.get("_base_priority") or 0)
    score = base_priority + mime_score + resolution_score + duration_score + size_score + _name_priority(name) + tracker_score
    return round(score, 4), str(item.get("id") or item.get("url") or name)


def _reference_text(url: str) -> tuple[str, str | None]:
    match = re.search(r"docs\.google\.com/document/d/([A-Za-z0-9_-]+)", url)
    if not match:
        return "", "not a public Google Doc"
    try:
        raw = fetch_bytes(
            f"https://docs.google.com/document/d/{match.group(1)}/export?format=txt",
            headers=DEFAULT_HEADERS,
            retries=2,
            timeout=60,
            min_bytes=1,
        )
        return raw.decode("utf-8", "ignore"), None
    except Exception as exc:
        return "", str(exc)[:300]


def _reference_urls(url: str) -> list[str]:
    """Return URLs embedded in a public Google Doc; kept for intake compatibility."""
    text, _ = _reference_text(url)
    return [u.rstrip(".,;") for u in URL_RE.findall(text)]


def download_youtube(url: str, destination: str, required_size: int = 0, safety_margin: int | None = None, max_bytes: int = 0) -> tuple[str, str | None]:
    """Download at most the first five minutes into an isolated temporary directory."""
    destination_path = Path(destination)
    temp_dir = destination_path.parent / ".youtube-tmp" / destination_path.stem
    try:
        guard, reason = _download_guard(destination, required_size, safety_margin)
        if guard != "ready":
            return "deferred", reason
        destination_path.unlink(missing_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        for leftover in temp_dir.glob("*"):
            if leftover.is_file():
                leftover.unlink(missing_ok=True)
        command = [
            sys.executable, "-m", "yt_dlp", "--no-playlist", "--retries", "5",
            "--fragment-retries", "5", "--extractor-retries", "3",
            "--retry-sleep", "http:linear=2::2", "--socket-timeout", "30",
            "--max-filesize", f"{max_bytes}B" if max_bytes > 0 else "800M", "--download-sections", "*0-300",
            "--force-keyframes-at-cuts", "-f", "bv*[height<=1080]+ba/b[height<=1080]",
            "--merge-output-format", "mp4", "-o", str(temp_dir / "source.%(ext)s"), url,
        ]
        subprocess.run(command, check=True, text=True, timeout=900)
        rendered = temp_dir / "source.mp4"
        if rendered.exists() and rendered.stat().st_size > 0:
            if max_bytes > 0 and rendered.stat().st_size > max_bytes:
                shutil.rmtree(temp_dir, ignore_errors=True)
                destination_path.unlink(missing_ok=True)
                return "deferred", "DEFERRED_DOWNLOAD_BYTE_BUDGET"
            rendered.replace(destination_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return "downloaded", None
        shutil.rmtree(temp_dir, ignore_errors=True)
        return "failed", "yt-dlp produced no complete file"
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        destination_path.unlink(missing_ok=True)
        return "failed", f"yt-dlp exit {exc.returncode}; YouTube may require a supported JS runtime or the video may be unavailable"
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        destination_path.unlink(missing_ok=True)
        return "failed", str(exc)[:300]



def download_drive(url: str, destination: str, folder: bool = False) -> tuple[str, str | None]:
    try:
        if folder:
            return "failed", "Drive folder download is disabled; use metadata-first discovery"
        if google_drive_configured():
            return download_file_oauth(url, destination)
        timeout = max(30, int(os.getenv("GOOGLE_DRIVE_PUBLIC_TIMEOUT_SECONDS", "180")))
        command = [sys.executable, "-m", "gdown", url, "-O", destination, "--fuzzy"]
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=timeout)
        if completed.returncode != 0:
            return "failed", (completed.stderr or completed.stdout or f"gdown exit {completed.returncode}")[:300]
        return ("downloaded", None) if os.path.exists(destination) and os.path.getsize(destination) > 0 else ("failed", "empty Drive file")
    except Exception as exc:
        return "failed", str(exc)[:300]


def download_direct(url: str, destination: str, safety_margin: int | None = None, max_bytes: int = 0) -> tuple[str, str | None]:
    try:
        guard, reason = _download_guard(destination, 0, safety_margin)
        if guard != "ready":
            return "deferred", reason
        target = Path(destination)
        part = Path(str(target) + ".part")
        target.unlink(missing_ok=True)
        part.unlink(missing_ok=True)
        data = fetch_bytes(url, headers=DEFAULT_HEADERS, retries=3, timeout=180, min_bytes=1)
        part.write_bytes(data)
        if part.stat().st_size <= 0:
            part.unlink(missing_ok=True)
            return "failed", "empty response"
        if max_bytes > 0 and part.stat().st_size > max_bytes:
            part.unlink(missing_ok=True)
            return "deferred", "DEFERRED_DOWNLOAD_BYTE_BUDGET"
        part.replace(target)
        return "downloaded", None
    except (FetchError, OSError, Exception) as exc:
        Path(str(destination) + ".part").unlink(missing_ok=True)
        return "failed", str(exc)[:300]


def _media_files(root: str) -> list[Path]:
    return [p for p in Path(root).rglob("*") if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".part") and p.suffix.lower() in DIRECT_EXTENSIONS]


def _source_id(url: str) -> str:
    return normalize_source_asset_id(url) or f"source-{abs(hash(url))}"


def _source_type(url: str, host: str | None = None) -> str:
    host = host or urlparse(url).netloc.lower()
    if "youtube.com/" in url or "youtu.be/" in url:
        return "youtube"
    if "drive.google.com" in host:
        return "google_drive_folder" if "/folders/" in url else "google_drive"
    if "vimeo.com/" in url:
        return "vimeo"
    return "direct_media"


def _is_youtube_collection_url(url: str) -> bool:
    """Return True for YouTube channel/tab/playlist URLs that must be expanded before download."""
    parsed = urlparse(str(url or ""))
    if parsed.netloc.lower() not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return False
    path = parsed.path.rstrip("/").lower()
    if path == "/playlist":
        return bool(parse_qs(parsed.query).get("list"))
    if path == "/watch":
        return False
    return bool(re.match(r"^/(?:@[^/]+|channel/[^/]+|user/[^/]+|c/[^/]+)(?:/(?:videos|shorts|streams|live|featured))?$", path, re.I))


def _discover_youtube_entries(url: str, limit: int = 24) -> list[dict]:
    """Discover recent individual videos from a channel/playlist without downloading media."""
    command = [
        sys.executable, "-m", "yt_dlp", "--flat-playlist", "--dump-single-json", "--skip-download",
        "--no-warnings", "--playlist-end", str(max(1, int(limit))),
        "--extractor-args", "youtubetab:approximate_date", url,
    ]
    completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=180)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"yt-dlp exit {completed.returncode}").strip()
        raise RuntimeError(detail[:500])
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"yt-dlp metadata bukan JSON: {exc}") from exc
    entries = payload.get("entries") or []
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "").strip()
        video_url = str(entry.get("webpage_url") or entry.get("original_url") or "").strip()
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        if not video_url or "youtube.com/watch" not in video_url:
            continue
        result.append({
            "url": video_url,
            "id": video_id,
            "name": str(entry.get("title") or video_id or video_url),
            "duration": entry.get("duration"),
            "upload_date": entry.get("upload_date"),
            "view_count": entry.get("view_count"),
        })
    return result


def _record(
    path: Path,
    workspace: str,
    url: str,
    source_type: str,
    status: str = "downloaded",
    error: str | None = None,
    metadata: dict | None = None,
    source_id: str | None = None,
) -> dict:
    item = {
        "source_id": source_id or _source_id(url),
        "url": url,
        "source_reference": url,
        "source_type": source_type,
        "created_at": now_iso(),
        "status": status,
        "path": os.path.relpath(path, workspace) if status == "downloaded" and path.exists() else None,
    }
    if metadata:
        item["source_metadata"] = metadata
    if status == "downloaded" and path.exists():
        item.update({"bytes": path.stat().st_size, "sha256": sha256_file(str(path))})
    elif error:
        item["reason"] = error
    return item


def main() -> None:
    ap = argparse.ArgumentParser(description="Harvest campaign rules and assets")
    ap.add_argument("plan", help="campaign plan.json")
    ap.add_argument("--workspace", default="data/jobs")
    ap.add_argument("--no-download", action="store_true", help="write rules/material manifest only")
    args = ap.parse_args()

    plan = read_json(args.plan)
    ws = create_workspace(args.workspace, plan)
    write_json(os.path.join(ws["path"], "plan.json"), plan)
    materials = os.path.join(ws["path"], "materials")
    os.makedirs(materials, exist_ok=True)

    records: list[dict] = []
    discovered: list[str] = []
    source_metadata: dict[str, dict] = {}
    source_priority: dict[str, tuple] = {}
    tracker_records = 0
    unresolved_references: list[dict] = []
    reference_manifest: list[dict] = []
    source_manifest: list[dict] = []
    asset_manifest: list[dict] = []

    production = plan.get("production") or {}\n    material_policy = production.get("material_policy") if isinstance(production.get("material_policy"), dict) else {}\n    material_policy_errors = []\n    try:\n        from core.material_acquisition import normalize_material_policy, validate_material_policy\n        material_policy = normalize_material_policy(material_policy)\n        material_policy_errors = validate_material_policy(material_policy)\n    except Exception as exc:\n        material_policy_errors = [f"material_policy_validation_error:{str(exc)[:160]}"]\n    write_json(os.path.join(materials, "MATERIAL_ACQUISITION_PLAN.json"), material_policy)\n    references = list(production.get("asset_urls") or [])\n    # Material intelligence can introduce campaign-specific named references.\n    # These are symbolic discovery intents, not proof of a source. Existing\n    # deterministic reference resolution remains responsible for verification.\n    for required in material_policy.get("required_assets") or []:\n        methods = required.get("discovery_methods") or material_policy.get("discovery_methods") or []\n        identity = required.get("identity") or {}\n        if "named_search" in methods and identity:\n            artist = identity.get("artist") or identity.get("creator") or identity.get("brand")\n            work = identity.get("work") or identity.get("title") or identity.get("name")\n            if work:\n                label = "Official Video" if any("official" in str(x).lower() for x in (required.get("intent"), required.get("preferred_sources"))) else "Video"\n                value = " - ".join(str(x).strip() for x in (artist, work) if str(x).strip())\n                references.append(f"{label}: {value}")\n    references = list(dict.fromkeys(str(value).strip() for value in references if str(value).strip()))\n    explicit_reference_values = [str(value).strip() for value in references if str(value).strip()]
    campaign_context = plan.get("campaign") or {}
    generated_policy_references = {
        f'{"Official Video" if any("official" in str(x).lower() for x in (required.get("intent"), required.get("preferred_sources"))) else "Video"}: {" - ".join(str(x).strip() for x in ((required.get("identity") or {}).get("artist") or (required.get("identity") or {}).get("creator") or (required.get("identity") or {}).get("brand"), (required.get("identity") or {}).get("work") or (required.get("identity") or {}).get("title") or (required.get("identity") or {}).get("name")) if str(x).strip())}'
        for required in material_policy.get("required_assets") or []
        if "named_search" in (required.get("discovery_methods") or material_policy.get("discovery_methods") or [])
        and ((required.get("identity") or {}).get("work") or (required.get("identity") or {}).get("title") or (required.get("identity") or {}).get("name"))
    }
    for raw_reference in explicit_reference_values:
        if raw_reference in generated_policy_references and is_symbolic_reference(raw_reference):
            resolution = resolve_named_youtube_reference(
                raw_reference,
                campaign_title=str(campaign_context.get("title") or ""),
                brand=str(campaign_context.get("brand") or ""),
            )
            reference_manifest.append({
                "reference": raw_reference,
                "kind": "POLICY_NAMED_SEARCH",
                "role": "PRIMARY_SOURCE_CANDIDATE",
                "reference_kind": "NAMED_MEDIA",
                "status": resolution.get("status"),
                "resolution": resolution,
                "url": str((resolution.get("candidate") or {}).get("url") or "") or None,
            })
            resolved_url = str((resolution.get("candidate") or {}).get("url") or "")
            if resolved_url:
                discovered.append(resolved_url)
            else:
                unresolved_references.append({
                    "reference": raw_reference,
                    "kind": "POLICY_NAMED_SEARCH",
                    "status": "UNRESOLVED",
                    "reason": resolution.get("reason") or "unresolved_named_media_reference",
                    "best_candidate": resolution.get("best_candidate"),
                })
            continue
        if is_symbolic_reference(raw_reference):
            resolved_url, mapping = _resolve_symbolic_asset(plan, raw_reference)
            reference_manifest.append({
                "reference": raw_reference,
                "kind": "SYMBOLIC_ASSET_REFERENCE",
                "role": "PRIMARY_SOURCE_CANDIDATE",
                "reference_kind": "SYMBOLIC_ASSET",
                "status": "RESOLVED" if resolved_url else "UNRESOLVED",
                "resolution": mapping,
                "url": resolved_url,
            })
            if resolved_url:
                discovered.append(resolved_url)
            else:
                unresolved_references.append({
                    "reference": raw_reference,
                    "kind": "SYMBOLIC_ASSET_REFERENCE",
                    "role": "PRIMARY_SOURCE_CANDIDATE",
                    "status": "UNRESOLVED",
                    "reason": "UNRESOLVED_SYMBOLIC_ASSET",
                    **mapping,
                })
            continue
    for url in references:
        if is_symbolic_reference(str(url)):
            continue
        discovered.append(url)
        if is_google_sheet_url(url):
            try:
                rows = fetch_sheet_rows(url)
                tracker_records += len(rows)
                sheet_name = f"reference-{len(list(Path(materials).glob('reference-*.json'))) + 1:02d}.json"
                Path(materials, sheet_name).write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                records.append(_record(Path(materials, sheet_name), ws["path"], url, "google_sheet"))
                for candidate in discover_sheet_assets(rows):
                    candidate_url = candidate["url"]
                    source_metadata.setdefault(candidate_url, {
                        "tracker_url": url,
                        "row_number": candidate["row_number"],
                        "row": candidate["metadata"],
                    })
                    source_priority.setdefault(candidate_url, tuple(candidate["priority"]))
                    if candidate_url not in discovered:
                        discovered.append(candidate_url)
            except GoogleSheetError as exc:
                unresolved_references.append(url)
                records.append(_record(
                    Path(materials, "unreadable-google-sheet.txt"),
                    ws["path"],
                    url,
                    "google_sheet",
                    "failed",
                    str(exc),
                ))
        elif "docs.google.com/document/" in url:
            text, error = _reference_text(url)
            name = f"reference-{len(list(Path(materials).glob('reference-*.txt'))) + 1:02d}.txt"
            Path(materials, name).write_text(
                text if text else f"Unable to read reference: {error}\n",
                encoding="utf-8",
            )
            status = "downloaded" if text else "failed"
            records.append(_record(Path(materials, name), ws["path"], url, "google_doc", status, error))
            if text:
                extracted = extract_document_references(text)
                reference_manifest.extend([
                    {**item, "origin": url, "reference_kind": "EXPLICIT_URL"}
                    for item in extracted.get("urls", [])
                ])
                for symbolic in extracted.get("symbolic_assets", []):
                    symbolic_value = str(symbolic.get("reference") or "").strip()
                    resolved_url, mapping = _resolve_symbolic_asset(plan, symbolic_value)
                    reference_entry = {
                        **symbolic,
                        "reference": symbolic_value,
                        "kind": "SYMBOLIC_ASSET_REFERENCE",
                        "reference_kind": "SYMBOLIC_ASSET",
                        "status": "RESOLVED" if resolved_url else "UNRESOLVED",
                        "resolution": mapping,
                        "url": resolved_url,
                        "origin": url,
                    }
                    reference_manifest.append(reference_entry)
                    if resolved_url and resolved_url not in discovered:
                        discovered.append(resolved_url)
                    elif not resolved_url:
                        unresolved_references.append({
                            **symbolic,
                            "reference": symbolic_value,
                            "kind": "SYMBOLIC_ASSET_REFERENCE",
                            "status": "UNRESOLVED",
                            "reason": "UNRESOLVED_SYMBOLIC_ASSET",
                            "origin": url,
                            **mapping,
                        })
                for item in extracted.get("urls", []):
                    candidate_url = item["url"]
                    if item.get("role") == "REFERENCE_ONLY":
                        continue
                    if candidate_url not in discovered:
                        discovered.append(candidate_url)
                campaign = plan.get("campaign") or {}
                named_limit = max(0, _env_int("CLIPPER_NAMED_REFERENCE_MAX", 3))
                for named in extracted.get("named_media", [])[:named_limit]:
                    resolution = resolve_named_youtube_reference(
                        named.get("value", ""),
                        campaign_title=str(campaign.get("title") or ""),
                        brand=str(campaign.get("brand") or ""),
                    )
                    reference_entry = {
                        **named,
                        "origin": url,
                        "reference_kind": "NAMED_MEDIA",
                        "resolution": resolution,
                    }
                    reference_manifest.append(reference_entry)
                    if resolution.get("status") == "verified_candidate":
                        candidate_url = str((resolution.get("candidate") or {}).get("url") or "")
                        if candidate_url and candidate_url not in discovered:
                            discovered.append(candidate_url)
                    else:
                        unresolved_references.append({
                            "reference": named.get("value"),
                            "kind": "NAMED_MEDIA",
                            "role": named.get("role"),
                            "origin": url,
                            "line_number": named.get("line_number"),
                            "status": "UNRESOLVED",
                            "reason": resolution.get("reason") or "unresolved_named_media_reference",
                            "best_candidate": resolution.get("best_candidate"),
                        })

    media_candidates: dict[str, dict] = {}
    for url in discovered:
        host = urlparse(url).netloc.lower()
        if "drive.google.com/file/d/" in url or "drive.google.com/open?id=" in url:
            media_candidates.setdefault(url, {"url": url, "priority": source_priority.get(url, (0, 0, 0, 0))})
        elif "/folders/" in url and "drive.google.com" in host:
            media_candidates.setdefault(url, {"url": url, "priority": source_priority.get(url, (0, 0, 0, 0))})
        elif "youtube.com/" in url or "youtu.be/" in url or "vimeo.com/" in url:
            media_candidates.setdefault(url, {"url": url, "priority": source_priority.get(url, (0, 0, 0, 0))})
        elif Path(urlparse(url).path).suffix.lower() in DIRECT_EXTENSIONS:
            media_candidates.setdefault(url, {"url": url, "priority": source_priority.get(url, (0, 0, 0, 0))})

    for url, metadata in source_metadata.items():
        if url in media_candidates:
            media_candidates[url]["metadata"] = metadata

    for item in reference_manifest:
        candidate_url = str(item.get("url") or "")
        if candidate_url and candidate_url in media_candidates:
            media_candidates[candidate_url]["reference_role"] = item.get("role") or "AMBIGUOUS_REFERENCE"

    # YouTube channel/playlist references are source collections, not downloadable videos.
    # Expand them into individual video URLs during metadata-only discovery.
    expanded_candidates: dict[str, dict] = {}
    for url, candidate in list(media_candidates.items()):
        if not _is_youtube_collection_url(url):
            expanded_candidates[url] = candidate
            continue
        try:
            entries = _discover_youtube_entries(url, _env_int("CLIPPER_YOUTUBE_DISCOVERY_LIMIT", 24))
        except Exception as exc:
            candidate["collection_error"] = str(exc)[:500]
            expanded_candidates[url] = candidate
            continue
        for entry in entries:
            video_url = entry["url"]
            item = dict(candidate)
            item["url"] = video_url
            item["name"] = entry.get("name")
            item["metadata"] = {**(candidate.get("metadata") or {}), "youtube_parent_source": url, "youtube_entry": entry}
            expanded_candidates.setdefault(video_url, item)
    media_candidates = expanded_candidates

    ordered_candidates = sorted(
        media_candidates.values(),
        key=lambda item: (
            tuple(item.get("priority") or (0, 0, 0, 0)),
            1 if "drive.google.com" in item["url"] else 0,
        ),
        reverse=True,
    )
    unique_candidates = []
    seen_source_ids = set()
    for candidate in ordered_candidates:
        source_id = normalize_source_asset_id(candidate.get("url"))
        if source_id in seen_source_ids:
            continue
        seen_source_ids.add(source_id)
        candidate["source_asset_id"] = source_id
        unique_candidates.append(candidate)
    # Download every discovered campaign source. The worker applies max_sources
    # later only to transcription/rendering, so no campaign material is silently skipped at intake.
    selected_candidates = unique_candidates

    video_count = 0
    downloaded_bytes = 0
    downloaded_assets = 0
    failed_assets = 0
    deferred_assets = 0
    download_limit = max(0, _env_int("CLIPPER_DOWNLOAD_MAX_ASSETS", DEFAULT_DOWNLOAD_MAX_ASSETS))
    download_budget = max(0, _env_int("CLIPPER_DOWNLOAD_MAX_BYTES", DEFAULT_DOWNLOAD_MAX_BYTES))
    disk_margin = max(0, _env_int("CLIPPER_DISK_SAFETY_MARGIN", DEFAULT_DISK_SAFETY_MARGIN))
    manual_lines = [
        "# Asset and rules intake", "",
        "Discovery is metadata-first. Only a bounded, prioritized subset is downloaded.",
        "All discovered source references remain auditable in source_manifest/asset_manifest.", "",
        "## Authorized sources", "",
    ]
    download_queue: list[dict] = []
    seen_asset_ids: set[str] = set()

    for index, candidate in enumerate(unique_candidates, 1):
        url = str(candidate["url"])
        metadata = candidate.get("metadata") or {}
        host = urlparse(url).netloc.lower()
        label = f"source-{index:02d}"
        source_id = candidate.get("source_asset_id") or _source_id(url)
        source_type = _source_type(url, host)
        provisional_asset_id, policy_match_reason = match_candidate(
            material_policy,
            {"source_type": source_type, "source_url": url, "reference_role": candidate.get("reference_role")},
        )
        source_entry = {
            "source_id": source_id,
            "policy_asset_id": provisional_asset_id,
            "policy_match": policy_match_reason,
            "reference_role": candidate.get("reference_role") or "PRIMARY_SOURCE",
            "source_type": source_type,
            "source_reference": url,
            "source_url": url,
            "discovered": True,
            "accessible": False,
            "downloaded": False,
            "local_path": None,
            "local_paths": [],
            "mime_type": None,
            "size_bytes": None,
            "duration": None,
            "asset_count": 0,
            "media_asset_count": 0,
            "downloaded_asset_count": 0,
            "deferred_asset_count": 0,
            "failed_asset_count": 0,
            "status": "discovered",
            "media_validation": None,
            "error_code": None,
            "error_message": None,
        }

        if args.no_download:
            if "/folders/" in url and "drive.google.com" in host and google_drive_configured():
                status, error, children = discover_folder_oauth(url)
                source_entry.update({
                    "accessible": status == "discovered",
                    "asset_count": len(children),
                    "media_asset_count": sum(1 for child in children if str(child.get("mimeType") or "").startswith("video/") or Path(str(child.get("name") or "")).suffix.lower() in VIDEO_EXTENSIONS),
                    "status": status,
                    "error_message": error,
                })
                if error:
                    source_entry.update({"status": "inaccessible", "error_code": "drive_discovery_failed"})
                for child in children:
                    child_id = str(child.get("id") or "")
                    name = str(child.get("name") or "")
                    mime = str(child.get("mimeType") or "")
                    is_video = mime.startswith("video/") or Path(name).suffix.lower() in VIDEO_EXTENSIONS
                    can_download = child.get("capabilities", {}).get("canDownload", True) is not False
                    asset_manifest.append({
                        "asset_id": child_id,
                        "source_id": source_id,
                        "source_type": "google_drive_asset",
                        "source_reference": url,
                        "source_url": f"https://drive.google.com/file/d/{child_id}/view" if child_id else url,
                        "name": name,
                        "mime_type": mime,
                        "size_bytes": int(child.get("size") or 0),
                        "modified_time": child.get("modifiedTime"),
                        "discovered": True,
                        "accessible": bool(can_download),
                        "downloaded": False,
                        "local_path": None,
                        "asset_kind": "video" if is_video else "other",
                        "status": "READY_FOR_DOWNLOAD" if is_video and can_download else "SKIPPED_NON_MEDIA" if not is_video else "INACCESSIBLE",
                        "error_code": None if is_video and can_download else "non_video" if not is_video else "access_denied",
                        "error_message": None if is_video and can_download else "not a video asset" if not is_video else "Drive asset cannot be downloaded",
                    })
            else:
                source_entry.update({"status": "deferred", "error_code": "download_disabled", "error_message": "download disabled by flag"})
            source_manifest.append(source_entry)
            continue

        if "/folders/" in url and "drive.google.com" in host:
            if not google_drive_configured():
                source_entry.update({"status": "inaccessible", "error_code": "drive_oauth_required", "error_message": "Drive folder discovery requires OAuth credentials for metadata-first intake"})
                source_manifest.append(source_entry)
                manual_lines += [f"- {url} — OAuth Drive diperlukan untuk discovery metadata-first", ""]
                continue
            status, error, children = discover_folder_oauth(url)
            source_entry.update({
                "accessible": status == "discovered",
                "status": "discovered" if status == "discovered" else "inaccessible",
                "asset_count": len(children),
                "media_asset_count": 0,
                "error_code": None if not error else "drive_discovery_failed",
                "error_message": error,
            })
            if error:
                source_manifest.append(source_entry)
                manual_lines += [f"- {url} — {error}", ""]
                continue
            for child in children:
                child_id = str(child.get("id") or "")
                name = str(child.get("name") or "")
                mime = str(child.get("mimeType") or "")
                is_video = mime.startswith("video/") or Path(name).suffix.lower() in VIDEO_EXTENSIONS
                can_download = child.get("capabilities", {}).get("canDownload", True) is not False
                if is_video:
                    source_entry["media_asset_count"] += 1
                duplicate = child_id in seen_asset_ids if child_id else False
                if child_id:
                    seen_asset_ids.add(child_id)
                asset_entry = {
                    "asset_id": child_id,
                    "reference_role": candidate.get("reference_role") or "PRIMARY_SOURCE",
                    "source_id": source_id,
                    "source_type": "google_drive_asset",
                    "source_reference": url,
                    "source_url": f"https://drive.google.com/file/d/{child_id}/view" if child_id else url,
                    "name": name,
                    "mime_type": mime,
                    "size_bytes": int(child.get("size") or 0),
                    "modified_time": child.get("modifiedTime"),
                    "discovered": True,
                    "accessible": bool(can_download),
                    "downloaded": False,
                    "local_path": None,
                    "asset_kind": "video" if is_video else "other",
                    "status": "SKIPPED_DUPLICATE" if duplicate else "READY_FOR_DOWNLOAD" if is_video and can_download else "SKIPPED_NON_MEDIA" if not is_video else "INACCESSIBLE",
                    "error_code": "duplicate_asset" if duplicate else None if is_video and can_download else "non_video" if not is_video else "access_denied",
                    "error_message": "duplicate Drive asset reference" if duplicate else None if is_video and can_download else "not a video asset" if not is_video else "Drive asset cannot be downloaded",
                }
                asset_manifest.append(asset_entry)
                if is_video and can_download and not duplicate and child_id:
                    queue_item = dict(child)
                    queue_item["url"] = url
                    queue_item["priority"] = candidate.get("priority") or ()
                    download_queue.append({
                        "kind": "drive",
                        "source_id": source_id,
                        "source_entry": source_entry,
                        "asset_entry": asset_entry,
                        "item": queue_item,
                        "base_priority": 20,
                    })
        else:
            is_youtube = "youtube.com/" in url or "youtu.be/" in url
            is_drive = "drive.google.com" in host
            is_video = is_youtube or is_drive or Path(urlparse(url).path).suffix.lower() in VIDEO_EXTENSIONS
            asset_entry = {
                "asset_id": source_id,
                "policy_asset_id": provisional_asset_id,
                "reference_role": candidate.get("reference_role") or "PRIMARY_SOURCE",
                "source_id": source_id,
                "source_type": source_type,
                "source_reference": url,
                "source_url": url,
                "name": Path(urlparse(url).path).name or label,
                "mime_type": None,
                "size_bytes": None,
                "modified_time": None,
                "discovered": True,
                "accessible": False,
                "downloaded": False,
                "local_path": None,
                "asset_kind": "video" if is_video else "other",
                "status": "READY_FOR_DOWNLOAD" if is_video else "SKIPPED_NON_MEDIA",
                "error_code": None if is_video else "non_video",
                "error_message": None if is_video else "not a supported media URL",
            }
            asset_manifest.append(asset_entry)
            source_entry["asset_count"] = 1
            source_entry["media_asset_count"] = 1 if is_video else 0
            if is_video and not _is_youtube_collection_url(url):
                download_queue.append({
                    "kind": "youtube" if is_youtube else "drive_file" if is_drive else "direct",
                    "source_id": source_id,
                    "source_entry": source_entry,
                    "asset_entry": asset_entry,
                    "item": {
                        "url": url,
                        "priority": candidate.get("priority") or (),
                        "name": asset_entry["name"],
                        "mimeType": "video/*" if is_video else "",
                    },
                    "base_priority": 60 if is_youtube else 55 if is_drive else 35,
                })

        source_manifest.append(source_entry)

    # Complete discovery is finished before any media download.
    # Give each distinct top-level source one opportunity before filling the
    # remaining slots by metadata score. This prevents a large Drive folder from
    # starving a separate authorized YouTube source.
    ranked_queue = sorted(
        download_queue,
        key=lambda entry: (
            _asset_priority({**entry["item"], "url": entry["item"].get("url"), "_base_priority": entry.get("base_priority", 0)}),
            str(entry["asset_entry"].get("asset_id") or ""),
        ),
        reverse=True,
    )
    fair_queue: list[dict] = []
    seen_queue_sources: set[str] = set()
    for entry in ranked_queue:
        source_id = str(entry.get("source_id") or "")
        if source_id in seen_queue_sources:
            continue
        seen_queue_sources.add(source_id)
        fair_queue.append(entry)
    fair_queue.extend(entry for entry in ranked_queue if entry not in fair_queue)

    for entry in fair_queue:
        asset_entry = entry["asset_entry"]
        source_entry = entry["source_entry"]
        item = entry["item"]
        if download_limit > 0 and downloaded_assets >= download_limit:
            asset_entry.update({"status": "DEFERRED_RESOURCE_BUDGET", "error_code": "download_asset_limit", "error_message": f"download asset limit {download_limit} reached"})
            source_entry["deferred_asset_count"] += 1
            deferred_assets += 1
            continue
        required_size = int(item.get("size") or 0)
        unknown_reserve = max(512 * 1024 * 1024, _env_int("CLIPPER_UNKNOWN_DOWNLOAD_RESERVE", DEFAULT_UNKNOWN_DOWNLOAD_RESERVE))
        estimated_size = required_size if required_size > 0 else unknown_reserve
        remaining_budget = max(0, download_budget - downloaded_bytes) if download_budget > 0 else 0
        if download_budget > 0 and estimated_size > remaining_budget:
            asset_entry.update({"status": "DEFERRED_RESOURCE_BUDGET", "error_code": "download_bytes_budget", "error_message": f"download requires reservation {estimated_size} bytes but only {remaining_budget} bytes remain"})
            source_entry["deferred_asset_count"] += 1
            deferred_assets += 1
            continue

        destination = os.path.join(
            ws["assets"],
            f"asset-{downloaded_assets + 1:03d}{Path(str(asset_entry.get('name') or 'asset.mp4')).suffix.lower() or '.mp4'}",
        )
        kind = entry["kind"]
        if kind == "drive":
            dl_status, dl_error, actual_size = download_asset_oauth(
                str(item.get("id") or asset_entry.get("asset_id")),
                destination,
                required_size=required_size,
                safety_margin=disk_margin,
            )
        elif kind == "youtube":
            dl_status, dl_error = download_youtube(
                str(item.get("url")), destination, required_size=0, safety_margin=disk_margin, max_bytes=remaining_budget
            )
            actual_size = Path(destination).stat().st_size if dl_status == "downloaded" and Path(destination).exists() else 0
        elif kind == "drive_file":
            dl_status, dl_error = download_file_oauth(str(item.get("url")), destination, max_bytes=remaining_budget)
            actual_size = Path(destination).stat().st_size if dl_status == "downloaded" and Path(destination).exists() else 0
        else:
            dl_status, dl_error = download_direct(str(item.get("url")), destination, safety_margin=disk_margin, max_bytes=remaining_budget)
            actual_size = Path(destination).stat().st_size if dl_status == "downloaded" and Path(destination).exists() else 0

        if dl_status == "downloaded" and Path(destination).exists() and Path(destination).stat().st_size > 0:
            rel = os.path.relpath(destination, ws["path"])
            media_validation = validate_video_file(destination)
            asset_entry.update({
                "accessible": True,
                "downloaded": True,
                "status": "READY_FOR_PROCESSING" if media_validation.get("status") == "pass" else "INVALID_MEDIA",
                "local_path": rel,
                "size_bytes": Path(destination).stat().st_size,
                "actual_size_bytes": actual_size,
                "media_validation": media_validation,
            })
            if media_validation.get("status") == "pass":
                source_entry.update({
                    "accessible": True,
                    "downloaded": True,
                    "downloaded_asset_count": int(source_entry.get("downloaded_asset_count") or 0) + 1,
                })
                source_entry["local_paths"].append(rel)
                if str(asset_entry.get("asset_kind")) == "video":
                    video_count += 1
            else:
                asset_entry["error_code"] = "invalid_media"
                asset_entry["error_message"] = "; ".join(media_validation.get("issues") or ["downloaded file is not a usable video"])
                source_entry["failed_asset_count"] += 1
                failed_assets += 1
                manual_lines += [f"- {source_entry['source_reference']} / {asset_entry.get('name') or asset_entry['asset_id']} — {asset_entry['error_message']}", ""]
            records.append(_record(
                Path(destination), ws["path"],
                str(item.get("url") or source_entry["source_reference"]),
                entry["kind"],
                "downloaded" if media_validation.get("status") == "pass" else "failed",
                asset_entry.get("error_message"),
                item,
                asset_entry["asset_id"],
            ))
            downloaded_bytes += actual_size
            downloaded_assets += 1
            continue
        if dl_status == "deferred":
            budget_error = dl_error == "DEFERRED_DOWNLOAD_BYTE_BUDGET"
            asset_entry.update({"status": "DEFERRED_RESOURCE_BUDGET" if budget_error else "DEFERRED_DISK_BUDGET", "error_code": dl_error or "DEFERRED_DISK_BUDGET", "error_message": "download byte budget is insufficient for this asset" if budget_error else "runner disk budget is insufficient for this asset"})
            source_entry["deferred_asset_count"] += 1
            deferred_assets += 1
            continue
        asset_entry.update({"status": "DOWNLOAD_FAILED", "error_code": dl_error or "download_failed", "error_message": dl_error or "asset download failed"})
        source_entry["failed_asset_count"] += 1
        failed_assets += 1
        records.append(_record(Path(destination), ws["path"], str(item.get("url") or source_entry["source_reference"]), entry["kind"], "failed", dl_error, item, asset_entry["asset_id"]))
        manual_lines += [f"- {source_entry['source_reference']} / {asset_entry.get('name') or asset_entry['asset_id']} — {dl_error or 'download failed'}", ""]

    for source_entry in source_manifest:
        if source_entry.get("status") == "inaccessible":
            continue
        downloaded_count = int(source_entry.get("downloaded_asset_count") or 0)
        deferred_count = int(source_entry.get("deferred_asset_count") or 0)
        failed_count = int(source_entry.get("failed_asset_count") or 0)
        media_count = int(source_entry.get("media_asset_count") or 0)
        if downloaded_count:
            source_entry["status"] = "downloaded" if downloaded_count >= media_count and media_count else "partially_downloaded"
        elif failed_count:
            source_entry["status"] = "failed"
        elif deferred_count:
            source_entry["status"] = "deferred"
        elif media_count == 0:
            source_entry["status"] = "no_media"

    # Enforce the policy contract after acquisition. Partial downloads are not success.
    minimums = required_asset_minimums(material_policy)
    policy_results = []
    for item in asset_manifest:
        policy_id = item.get("policy_asset_id")
        if not policy_id:
            continue
        policy_results.append({
            "asset_id": policy_id,
            "status": "accessible" if item.get("status") == "READY_FOR_PROCESSING" else "manual_required" if item.get("status") in {"INACCESSIBLE", "DOWNLOAD_FAILED"} else "unresolved",
            "source_url": item.get("source_url"),
            "provider": item.get("source_type"),
            "evidence": item.get("media_validation"),
            "local_path": item.get("local_path"),
            "sha256": item.get("sha256"),
        })
    from core.material_acquisition import acquisition_status
    policy_status = acquisition_status(policy_results, material_policy) if minimums else "needs_review"
    discovered_media_asset_count = sum(1 for item in asset_manifest if item.get("asset_kind") == "video")
    accessible_media_asset_count = sum(1 for item in asset_manifest if item.get("asset_kind") == "video" and item.get("accessible"))
    deferred_media_asset_count = sum(1 for item in asset_manifest if item.get("asset_kind") == "video" and str(item.get("status", "")).startswith("DEFERRED"))
    failed_media_asset_count = sum(1 for item in asset_manifest if item.get("asset_kind") == "video" and item.get("status") in {"DOWNLOAD_FAILED", "INVALID_MEDIA"})
    invalid_media_asset_count = sum(1 for item in asset_manifest if item.get("asset_kind") == "video" and item.get("status") == "INVALID_MEDIA")
    ready_media_asset_count = sum(1 for item in asset_manifest if item.get("asset_kind") == "video" and item.get("status") == "READY_FOR_PROCESSING")
    rules = plan.get("source_of_truth") or {}
    rules_path = Path(materials, "RULES_SNAPSHOT.md")
    requirements = rules.get("requirements") or []
    rules_path.write_text(
        "# Campaign Rules Snapshot\n\n## Description\n\n"
        + str(rules.get("description") or "-")
        + "\n\n## Mandatory requirements\n\n"
        + "\n".join(f"- [{'x' if r.get('isMandatory') else ' '}] {r.get('text')}" for r in requirements)
        + "\n",
        encoding="utf-8",
    )
    records.append(_record(rules_path, ws["path"], "plan.source_of_truth", "rules_snapshot"))

    manifest = {
        "schema_version": 4,
        "job_id": ws["job_id"],
        "campaign": plan.get("campaign"),
        "rules_snapshot": os.path.relpath(rules_path, ws["path"]),
        "material_acquisition": {
            "policy": material_policy,
            "policy_validation_errors": material_policy_errors,
            "status": "needs_review" if material_policy_errors else policy_status,
            "required_minimums": minimums,
            "results": policy_results,
            "plan_fingerprint": __import__("core.material_acquisition", fromlist=["material_plan_fingerprint"]).material_plan_fingerprint(material_policy),
        },
        "assets": records,
        "source_manifest": source_manifest,
        "asset_manifest": asset_manifest,
        "reference_manifest": reference_manifest,
        "discovery": {
            "reference_count": len(references),
            "explicit_url_count": sum(1 for item in reference_manifest if item.get("reference_kind") == "EXPLICIT_URL"),
            "named_reference_count": sum(1 for item in reference_manifest if item.get("reference_kind") == "NAMED_MEDIA"),
            "primary_source_count": sum(1 for item in reference_manifest if item.get("role") in {"PRIMARY_SOURCE", "PRIMARY_SOURCE_CANDIDATE"}),
            "reference_only_count": sum(1 for item in reference_manifest if item.get("role") == "REFERENCE_ONLY"),
            "tracker_rows": tracker_records,
            "discovered_media_sources": len(media_candidates),
            "selected_media_sources": len(selected_candidates),
            "deduplicated_media_sources": len(unique_candidates),
            "discovered_asset_count": len(asset_manifest),
            "discovered_media_asset_count": discovered_media_asset_count,
            "accessible_asset_count": sum(1 for item in asset_manifest if item.get("accessible")),
            "accessible_media_asset_count": accessible_media_asset_count,
            "downloaded_asset_count": downloaded_assets,
            "downloaded_media_asset_count": video_count,
            "ready_for_processing_asset_count": ready_media_asset_count,
            "invalid_media_asset_count": invalid_media_asset_count,
            "deferred_asset_count": deferred_assets,
            "deferred_media_asset_count": deferred_media_asset_count,
            "failed_asset_count": failed_assets,
            "failed_media_asset_count": failed_media_asset_count,
            "download_limits": {"max_assets": download_limit, "max_bytes": download_budget, "disk_safety_margin": disk_margin},
            "downloaded_bytes": downloaded_bytes,
            "unresolved_references": unresolved_references,
            "reference_manifest_count": len(reference_manifest),
            "inaccessible_source_count": sum(1 for item in source_manifest if not item.get("accessible") and item.get("status") in {"inaccessible", "failed"}),
            "asset_preflight": {
                "references_discovered": len(references) + len(reference_manifest) + len(unresolved_references),
                "explicit_urls": sum(1 for item in reference_manifest if item.get("reference_kind") == "EXPLICIT_URL"),
                "named_references": sum(1 for item in reference_manifest if item.get("reference_kind") == "NAMED_MEDIA"),
                "primary_sources": sum(1 for item in reference_manifest if item.get("role") in {"PRIMARY_SOURCE", "PRIMARY_SOURCE_CANDIDATE"}),
                "reference_only_sources": sum(1 for item in reference_manifest if item.get("role") == "REFERENCE_ONLY"),
                "unresolved_references": len(unresolved_references),
                "inaccessible_sources": sum(1 for item in source_manifest if not item.get("accessible") and item.get("status") in {"inaccessible", "failed"}),
                "video_assets_discovered": discovered_media_asset_count,
                "accessible_video_assets": accessible_media_asset_count,
                "download_attempted": downloaded_assets + failed_assets,
                "downloaded": downloaded_assets,
                "download_failed": failed_assets,
                "deferred": deferred_media_asset_count,
                "valid_media": ready_media_asset_count,
                "invalid_media": invalid_media_asset_count,
                "downloaded_bytes": downloaded_bytes,
                "ready_for_processing": ready_media_asset_count,
            },
        },
        "updated_at": now_iso(),
    }
    write_json(os.path.join(ws["path"], "assets.json"), manifest)
    Path(ws["path"], "MANUAL_ASSETS.md").write_text("\n".join(manual_lines) + "\n", encoding="utf-8")
    downloaded = sum(1 for r in records if r["status"] == "downloaded")
    failed = sum(1 for r in records if r["status"] == "failed")
    print(f"OK: workspace {ws['path']}")
    print(
        f"records: {len(records)} | downloaded: {downloaded} | failed: {failed} "
        f"| tracker_rows: {tracker_records} | media_sources: {len(media_candidates)} "
        f"| selected: {len(unique_candidates)} | video_sources: {video_count} | downloaded_assets: {downloaded_assets} | deferred_assets: {deferred_assets} | failed_assets: {failed_assets} | downloaded_bytes: {downloaded_bytes}"
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
