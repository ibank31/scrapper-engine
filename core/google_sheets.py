"""Resolve campaign asset trackers stored in Google Sheets."""
from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import urlparse

from core.fetch import DEFAULT_HEADERS, fetch_bytes
from core.google_drive import GoogleDriveClient, configured as google_drive_configured

URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
SHEET_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)", re.I)
MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".wav", ".mp3", ".m4a"}


class GoogleSheetError(RuntimeError):
    """A safe, user-actionable Google Sheets integration failure."""


def extract_sheet_id(url: str) -> str | None:
    match = SHEET_RE.search(str(url or ""))
    return match.group(1) if match else None


def is_google_sheet_url(url: str) -> bool:
    return bool(extract_sheet_id(url))


def _csv_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def _decode_csv(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig", "replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    headers = [str(h or "").strip() for h in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for row in reader:
        normalized = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            normalized[header] = str(row.get(reader.fieldnames[index]) or "").strip()
        if any(normalized.values()):
            rows.append(normalized)
    return rows


def fetch_sheet_rows(url: str) -> list[dict[str, str]]:
    sheet_id = extract_sheet_id(url)
    if not sheet_id:
        raise GoogleSheetError("Google Sheet ID tidak ditemukan")

    errors: list[str] = []
    if google_drive_configured():
        try:
            raw = GoogleDriveClient().export_file(sheet_id, "text/csv")
            rows = _decode_csv(raw)
            if rows:
                return rows
            errors.append("Drive OAuth export menghasilkan sheet kosong")
        except Exception as exc:
            errors.append(str(exc)[:240])

    try:
        raw = fetch_bytes(_csv_url(sheet_id), headers=DEFAULT_HEADERS, retries=2, timeout=60, min_bytes=1)
        rows = _decode_csv(raw)
        if rows:
            return rows
        errors.append("public CSV export menghasilkan sheet kosong")
    except Exception as exc:
        errors.append(str(exc)[:240])

    detail = "; ".join(errors[-2:]) or "tidak ada detail error"
    raise GoogleSheetError(f"Google Sheet tidak dapat dibaca: {detail}")


def _path_suffix(path: str) -> str:
    dot = path.rfind(".")
    return path[dot:] if dot >= 0 else ""


def _media_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    lower = url.lower()
    return (
        ("drive.google.com" in host and ("/file/d/" in path or "/folders/" in path or "id=" in parsed.query))
        or "youtube.com/" in lower
        or "youtu.be/" in lower
        or "vimeo.com/" in lower
        or _path_suffix(path) in MEDIA_EXTENSIONS
    )


def _priority(row: dict[str, str], row_number: int) -> tuple[int, int, int, int]:
    normalized = {str(k).strip().lower(): str(v).strip().lower() for k, v in row.items()}
    hype = normalized.get("hype level", normalized.get("hype", ""))
    hype_score = {"insane": 4, "high": 3, "medium": 2, "low": 1}.get(hype, 0)
    hook_score = int(bool(normalized.get("suggested hook") or normalized.get("hook")))
    value_text = normalized.get("card value", normalized.get("value", ""))
    value_digits = re.sub(r"[^0-9]", "", value_text)
    try:
        value_score = min(int(value_digits), 10_000_000_000) if value_digits else 0
    except ValueError:
        value_score = 0
    return (hype_score, hook_score, value_score, -row_number)


def discover_sheet_assets(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows, 2):
        row_urls: list[str] = []
        for value in row.values():
            for raw_url in URL_RE.findall(str(value or "")):
                url = raw_url.rstrip(".,;:)]}")
                if url and url not in row_urls:
                    row_urls.append(url)
        for url in row_urls:
            if not _media_url(url) or url in seen:
                continue
            seen.add(url)
            discovered.append({
                "url": url,
                "row_number": row_number,
                "metadata": dict(row),
                "priority": _priority(row, row_number),
            })
    discovered.sort(key=lambda item: item["priority"], reverse=True)
    return discovered


__all__ = ["GoogleSheetError", "extract_sheet_id", "is_google_sheet_url", "fetch_sheet_rows", "discover_sheet_assets"]
