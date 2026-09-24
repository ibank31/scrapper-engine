#!/usr/bin/env python3
"""Harvest campaign rules and publicly authorized media into an auditable workspace."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.fetch import DEFAULT_HEADERS, FetchError, fetch_bytes
from core.google_drive import configured as google_drive_configured, download_file_oauth, download_folder_oauth
from core.google_sheets import GoogleSheetError, discover_sheet_assets, fetch_sheet_rows, is_google_sheet_url
from core.job_workspace import create_workspace, now_iso, read_json, sha256_file, write_json
from core.candidate_identity import normalize_source_asset_id

DIRECT_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".wav", ".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".webp", ".srt", ".ass"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
URL_RE = re.compile(r"https?://[^\s<>\]\)\"]+", re.I)
MAX_VIDEO_SOURCES = 3


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


def download_youtube(url: str, destination: str) -> tuple[str, str | None]:
    try:
        command = [
            sys.executable, "-m", "yt_dlp", "--no-playlist", "--max-filesize", "800M",
            "--download-sections", "*0-300", "--force-keyframes-at-cuts",
            "-f", "bv*[height<=1080]+ba/b[height<=1080]", "--merge-output-format", "mp4",
            "-o", destination, url,
        ]
        subprocess.run(command, check=True, text=True, timeout=900)
        if os.path.exists(destination) and os.path.getsize(destination) > 0:
            return "downloaded", None
        return "failed", "yt-dlp produced no file"
    except Exception as exc:
        return "failed", str(exc)[:300]


def download_drive(url: str, destination: str, folder: bool = False) -> tuple[str, str | None]:
    try:
        if google_drive_configured():
            if folder:
                status, error, _ = download_folder_oauth(
                    url,
                    destination,
                    max_files=max(1, int(os.getenv("GOOGLE_DRIVE_MAX_FILES", "3"))),
                )
                return status, error
            return download_file_oauth(url, destination)
        timeout = max(30, int(os.getenv("GOOGLE_DRIVE_PUBLIC_TIMEOUT_SECONDS", "180")))
        command = [sys.executable, "-m", "gdown"]
        if folder:
            os.makedirs(destination, exist_ok=True)
            command += ["--folder", url, "-O", destination, "--remaining-ok"]
        else:
            command += [url, "-O", destination, "--fuzzy"]
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=timeout)
        if completed.returncode != 0:
            return "failed", (completed.stderr or completed.stdout or f"gdown exit {completed.returncode}")[:300]
        if folder:
            return ("downloaded", None) if any(Path(destination).rglob("*")) else ("failed", "empty Drive folder")
        return ("downloaded", None) if os.path.exists(destination) and os.path.getsize(destination) > 0 else ("failed", "empty Drive file")
    except Exception as exc:
        return "failed", str(exc)[:300]


def download_direct(url: str, destination: str) -> tuple[str, str | None]:
    try:
        data = fetch_bytes(url, headers=DEFAULT_HEADERS, retries=3, timeout=180, min_bytes=1)
        with open(destination, "wb") as fh:
            fh.write(data)
        return ("downloaded", None) if os.path.getsize(destination) else ("failed", "empty response")
    except (FetchError, OSError, Exception) as exc:
        return "failed", str(exc)[:300]


def _media_files(root: str) -> list[Path]:
    return [p for p in Path(root).rglob("*") if p.is_file() and p.suffix.lower() in DIRECT_EXTENSIONS]


def _record(
    path: Path,
    workspace: str,
    url: str,
    source_type: str,
    status: str = "downloaded",
    error: str | None = None,
    metadata: dict | None = None,
) -> dict:
    item = {
        "url": url,
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
    ap.add_argument("--max-video-sources", type=int, default=MAX_VIDEO_SOURCES)
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
    unresolved_references: list[str] = []

    references = (plan.get("production") or {}).get("asset_urls") or []
    for url in references:
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
                discovered.extend(u for u in URL_RE.findall(text) if u.rstrip(".,;") not in discovered)

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

    ordered_candidates = sorted(
        media_candidates.values(),
        key=lambda item: (
            tuple(item.get("priority") or (0, 0, 0, 0)),
            1 if "drive.google.com" in item["url"] else 0,
        ),
        reverse=True,
    )
    max_sources = max(1, args.max_video_sources)
    unique_candidates = []
    seen_source_ids = set()
    for candidate in ordered_candidates:
        source_id = normalize_source_asset_id(candidate.get("url"))
        if source_id in seen_source_ids:
            continue
        seen_source_ids.add(source_id)
        candidate["source_asset_id"] = source_id
        unique_candidates.append(candidate)
    selected_candidates = unique_candidates[:max_sources]

    video_count = 0
    manual_lines = [
        "# Asset and rules intake", "",
        "Rules snapshot and discovered material are stored in materials/ and assets/.",
        "", "## Authorized sources", "",
    ]
    if not selected_candidates:
        manual_lines += ["No supported media source was discovered from the campaign references.", ""]

    for index, candidate in enumerate(selected_candidates, 1):
        url = candidate["url"]
        metadata = candidate.get("metadata")
        host = urlparse(url).netloc.lower()
        label = f"source-{index:02d}"
        if args.no_download:
            records.append(_record(Path(ws["assets"], label + ".mp4"), ws["path"], url, "source", "needs_manual_download", "download disabled by flag", metadata))
            manual_lines += [f"- {url} — download disabled", ""]
            continue

        if "/folders/" in url and "drive.google.com" in host:
            target = os.path.join(ws["assets"], label)
            status, error = download_drive(url, target, folder=True)
            folder_files = _media_files(target) if status == "downloaded" else []
            if folder_files:
                video_count += len([p for p in folder_files if p.suffix.lower() in VIDEO_EXTENSIONS])
                records.extend(_record(p, ws["path"], url, "google_drive_folder", metadata=metadata) for p in folder_files)
            else:
                records.append(_record(Path(target), ws["path"], url, "google_drive_folder", "failed", error or "no media files", metadata))
        else:
            destination = os.path.join(ws["assets"], label + ".mp4")
            if "youtube.com/" in url or "youtu.be/" in url:
                status, error = download_youtube(url, destination)
                source_type = "youtube_preapproved"
            elif "drive.google.com" in host:
                status, error = download_drive(url, destination)
                source_type = "google_drive_file"
            else:
                status, error = download_direct(url, destination)
                source_type = "direct_media"
            records.append(_record(Path(destination), ws["path"], url, source_type, status, error, metadata))
            if status == "downloaded":
                video_count += 1
            else:
                manual_lines += [f"- {url} — {error}", ""]

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
        "schema_version": 3,
        "job_id": ws["job_id"],
        "campaign": plan.get("campaign"),
        "rules_snapshot": os.path.relpath(rules_path, ws["path"]),
        "assets": records,
        "discovery": {
            "reference_count": len(references),
            "tracker_rows": tracker_records,
            "discovered_media_sources": len(media_candidates),
            "selected_media_sources": len(selected_candidates),
            "deduplicated_media_sources": len(unique_candidates),
            "unresolved_references": unresolved_references,
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
        f"| selected: {len(selected_candidates)} | video_sources: {video_count}"
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
