#!/usr/bin/env python3
"""Build chat-ready review packages from rendered clips.

One package per render directory: clips are grouped into small batches so the
chat is never flooded. format_chat_message() produces the Indonesian review
message Punny sends alongside the video attachments. Nothing here publishes;
it only prepares the review.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any

DEFAULT_MAX_CLIPS_PER_BATCH = 2


def _load_meta(video_path: str) -> dict[str, Any] | None:
    meta_path = video_path.rsplit(".", 1)[0] + "-meta.json"
    if not os.path.exists(meta_path):
        return None
    try:
        return json.load(open(meta_path, encoding="utf-8"))
    except Exception:
        return None


def build_review_package(render_dir: str, campaign_name: str = "", rule_notes: list[str] | None = None,
                         max_clips_per_batch: int = DEFAULT_MAX_CLIPS_PER_BATCH,
                         preview_ids: dict[int, str] | None = None) -> dict[str, Any]:
    """Collect rendered clips + metadata into a paced review package."""
    videos = sorted(glob.glob(os.path.join(render_dir, "clip-*.mp4")))
    clips: list[dict[str, Any]] = []
    for video_path in videos:
        rank = int(os.path.basename(video_path).split("-")[1].split(".")[0])
        meta = _load_meta(video_path) or {}
        clips.append({
            "rank": rank,
            "video_path": os.path.abspath(video_path),
            "preview_id": (preview_ids or {}).get(rank),
            "title": meta.get("title"),
            "caption": meta.get("caption"),
            "cta": meta.get("cta"),
            "hashtags": meta.get("hashtags") or [],
            "hook_text": meta.get("hook_text"),
        })
    batches = [clips[index:index + max_clips_per_batch] for index in range(0, len(clips), max_clips_per_batch)]
    package = {
        "schema_version": 1,
        "campaign_name": campaign_name,
        "rule_notes": rule_notes or [],
        "clip_count": len(clips),
        "max_clips_per_batch": max_clips_per_batch,
        "clips": clips,
        "batches": [[clip["rank"] for clip in batch] for batch in batches],
    }
    try:
        with open(os.path.join(render_dir, "review-package.json"), "w", encoding="utf-8") as handle:
            json.dump(package, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError:
        pass
    return package


def format_chat_message(package: dict[str, Any], batch_index: int = 0) -> str:
    """Indonesian review message for one batch. Video files go as attachments."""
    ranks = package["batches"][batch_index] if package["batches"] else []
    by_rank = {clip["rank"]: clip for clip in package["clips"]}
    lines = []
    if package.get("campaign_name"):
        lines.append(f"Klip untuk campaign: {package['campaign_name']}")
        lines.append("")
    for rank in ranks:
        clip = by_rank[rank]
        lines.append(f"Klip #{rank}")
        if clip.get("title"):
            lines.append(f"Judul: {clip['title']}")
        if clip.get("caption"):
            lines.append(f"Caption: {clip['caption']}")
        if clip.get("cta"):
            lines.append(f"CTA: {clip['cta']}")
        if clip.get("hashtags"):
            lines.append("Hashtag: " + " ".join(f"#{tag}" for tag in clip["hashtags"]))
        lines.append("")
    notes = package.get("rule_notes") or []
    if notes:
        lines.append("Catatan aturan:")
        lines.extend(f"- {note}" for note in notes)
        lines.append("")
    total_batches = len(package["batches"])
    if total_batches > 1:
        lines.append(f"Batch {batch_index + 1} dari {total_batches}.")
    lines.append("Setuju untuk lanjut, atau tolak? Kamu yang submit manual ke platform campaign.")
    return "\n".join(lines).strip()
