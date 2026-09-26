#!/usr/bin/env python3
"""Controlled real-source acquisition smoke test.

This script exercises the provider boundary without touching Cloudflare, D1,
R2, production jobs, or campaign state. It resolves a named media reference,
downloads only a short preview segment, validates the resulting container, and
removes the temporary media before exit.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from core.material_references import resolve_named_youtube_reference
from core.media_validation import validate_video_file


def _download(url: str, destination: Path, max_bytes: int = 300 * 1024 * 1024) -> None:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--retries",
        "3",
        "--fragment-retries",
        "3",
        "--extractor-retries",
        "2",
        "--socket-timeout",
        "30",
        "--download-sections",
        "*0-30",
        "--force-keyframes-at-cuts",
        "-f",
        "bv*[height<=720]+ba/b[height<=720]",
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        f"{max_bytes}B",
        "-o",
        str(destination),
        url,
    ]
    subprocess.run(command, check=True, text=True, timeout=600)


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled real-source acquisition smoke")
    parser.add_argument("--reference", default=os.environ.get("CLIPPER_LIVE_REFERENCE", "Dardan - Erinnerung (Official Video)"))
    parser.add_argument("--campaign-title", default=os.environ.get("CLIPPER_LIVE_CAMPAIGN", "Dardan Music Clipping"))
    parser.add_argument("--brand", default=os.environ.get("CLIPPER_LIVE_BRAND", "Clipping Outlaws"))
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="clipper-source-smoke-"))
    result = {
        "schema_version": 1,
        "reference": args.reference,
        "campaign_title": args.campaign_title,
        "brand": args.brand,
        "resolution": None,
        "download": {"status": "not_attempted"},
        "media_validation": None,
        "ready_for_processing": False,
    }
    try:
        resolution = resolve_named_youtube_reference(
            args.reference,
            campaign_title=args.campaign_title,
            brand=args.brand,
        )
        result["resolution"] = resolution
        if resolution.get("status") != "verified_candidate":
            result["download"] = {
                "status": "blocked",
                "reason": resolution.get("reason") or "reference_unresolved",
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2

        url = str((resolution.get("candidate") or {}).get("url") or "")
        target = root / "source.mp4"
        result["download"] = {"status": "attempted", "url": url}
        _download(url, target)
        validation = validate_video_file(target)
        result["download"].update({
            "status": "downloaded",
            "bytes": target.stat().st_size if target.exists() else 0,
        })
        result["media_validation"] = validation
        result["ready_for_processing"] = validation.get("status") == "pass"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready_for_processing"] else 3
    except Exception as exc:
        result["download"] = {
            "status": "failed",
            "reason": f"{type(exc).__name__}: {str(exc)[:400]}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 4
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
