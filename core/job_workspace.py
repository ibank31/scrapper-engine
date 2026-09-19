#!/usr/bin/env python3
"""Filesystem state for campaign-aware clipping jobs."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any


def slug(value: Any, fallback: str = "campaign") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-.")
    return (text[:80] or fallback)


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_workspace(root: str, plan: dict[str, Any]) -> dict[str, str]:
    campaign = plan.get("campaign") or {}
    job_id = slug(campaign.get("id") or campaign.get("title"))
    path = os.path.join(os.path.expanduser(root), job_id)
    assets = os.path.join(path, "assets")
    outputs = os.path.join(path, "outputs")
    review = os.path.join(path, "review")
    for directory in (path, assets, outputs, review):
        os.makedirs(directory, exist_ok=True)
    return {"job_id": job_id, "path": path, "assets": assets, "outputs": outputs, "review": review}


def write_json(path: str, value: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
