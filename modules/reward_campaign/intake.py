#!/usr/bin/env python3
"""Create a campaign workspace and safely intake campaign-provided assets.

Only ordinary direct HTTP downloads are automated. Links that may require a
login, folder navigation, or platform-specific action are recorded for manual
handling instead of bypassing access controls.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.fetch import DEFAULT_HEADERS, FetchError, fetch_bytes
from core.job_workspace import create_workspace, now_iso, read_json, sha256_file, slug, write_json

DIRECT_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".wav", ".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".webp", ".srt", ".ass"}
MANUAL_HOSTS = ("dropbox.com", "drive.google.com", "docs.google.com", "frame.io", "youtube.com", "youtu.be", "vimeo.com", "tiktok.com")


def _filename(url: str, index: int) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    ext = Path(name).suffix.lower()
    if not name or ext not in DIRECT_EXTENSIONS:
        name = f"asset-{index:03d}.bin"
    return name[:160]


def _manual_reason(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if any(h in host for h in MANUAL_HOSTS):
        return "source may require login, folder navigation, ownership verification, or native platform action"
    return None


def download_direct(url: str, destination: str) -> tuple[str, str | None]:
    """Download one ordinary direct URL and return (status, error)."""
    try:
        data = fetch_bytes(url, headers=DEFAULT_HEADERS, retries=3, timeout=180, min_bytes=1)
        with open(destination, "wb") as fh:
            fh.write(data)
        if os.path.getsize(destination) < 1:
            return "failed", "empty response"
        return "downloaded", None
    except (FetchError, OSError, Exception) as exc:
        return "failed", str(exc)[:300]


def main() -> None:
    ap = argparse.ArgumentParser(description="Campaign asset intake")
    ap.add_argument("plan", help="campaign plan.json produced by reward_plan")
    ap.add_argument("--workspace", default="data/jobs", help="root folder for job workspaces")
    ap.add_argument("--no-download", action="store_true", help="only create manifest and manual instructions")
    args = ap.parse_args()

    plan = read_json(args.plan)
    ws = create_workspace(args.workspace, plan)
    write_json(os.path.join(ws["path"], "plan.json"), plan)
    urls = (plan.get("production") or {}).get("asset_urls") or []
    records: list[dict[str, object]] = []
    manual_lines = [
        f"# Manual asset actions — {plan.get('campaign', {}).get('title') or ws['job_id']}",
        "",
        "These links were not downloaded automatically because they may require login, folder selection, ownership verification, or native platform action.",
        "Download only assets provided or authorized by the campaign, then copy them into the `assets/` folder and update `assets.json`.",
        "",
    ]
    for index, url in enumerate(urls, 1):
        record: dict[str, object] = {"index": index, "url": url, "created_at": now_iso()}
        reason = _manual_reason(url)
        name = _filename(url, index)
        destination = os.path.join(ws["assets"], name)
        if args.no_download:
            reason = reason or "download disabled by flag"
        if reason:
            record.update({"status": "needs_manual_download", "reason": reason, "path": None})
            manual_lines += [f"{index}. `{url}`", f"   - Reason: {reason}", f"   - Save as: `assets/{name}`", ""]
        else:
            status, error = download_direct(url, destination)
            record.update({"status": status, "path": os.path.relpath(destination, ws["path"]) if status == "downloaded" else None})
            if status == "downloaded":
                record["bytes"] = os.path.getsize(destination)
                record["sha256"] = sha256_file(destination)
            else:
                record["error"] = error
                manual_lines += [f"{index}. `{url}`", f"   - Reason: automated download failed: {error}", f"   - Save as: `assets/{name}`", ""]
        records.append(record)

    manifest = {"schema_version": 1, "job_id": ws["job_id"], "campaign": plan.get("campaign"), "updated_at": now_iso(), "assets": records}
    write_json(os.path.join(ws["path"], "assets.json"), manifest)
    with open(os.path.join(ws["path"], "MANUAL_ASSETS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(manual_lines).rstrip() + "\n")
    downloaded = sum(1 for r in records if r["status"] == "downloaded")
    manual = sum(1 for r in records if r["status"] == "needs_manual_download")
    failed = sum(1 for r in records if r["status"] == "failed")
    print(f"OK: workspace {ws['path']}")
    print(f"assets: {len(records)} | downloaded: {downloaded} | manual: {manual} | failed: {failed}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
