#!/usr/bin/env python3
"""Build a human-friendly review queue from rendered clips and validation results."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _caption(plan: dict, candidate: dict) -> str:
    campaign = plan.get("campaign") or {}
    production = plan.get("production") or {}
    parts = []
    title = str(campaign.get("title") or campaign.get("brand") or "")
    if title:
        parts.append(title)
    if production.get("required_handles"):
        parts.extend(production["required_handles"])
    if production.get("cta_urls"):
        parts.extend(production["cta_urls"])
    return " ".join(parts) + ("\n\n" + candidate.get("text", "").strip() if candidate.get("text") else "")


def _thumbnail(video: str, output: str) -> None:
    command = ["ffmpeg", "-y", "-ss", "1", "-i", video, "-frames:v", "1", "-vf", "scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2", output]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _checklist(plan: dict, validation: dict) -> list[str]:
    production = plan.get("production") or {}
    tasks = ["Review the full video for factual accuracy, pacing, and platform suitability."]
    if production.get("watermark_required"):
        tasks.append("Confirm the official watermark is present in the required position, opacity, and duration.")
    if production.get("no_third_party_watermark"):
        tasks.append("Confirm no third-party watermark is visible.")
    if production.get("official_audio_required"):
        tasks.append("Attach the official campaign sound in the native platform composer if required.")
    if production.get("required_handles"):
        tasks.append("Add required handles in the platform's native tagging field.")
    if production.get("cta_urls"):
        tasks.append("Add the required CTA in the location stated by the campaign.")
    if production.get("prohibited"):
        tasks.append("Confirm the clip does not contain any prohibited content or format.")
    tasks.extend(validation.get("review") or [])
    return list(dict.fromkeys(tasks))


def build_queue(plan: dict, candidates: dict, validation: dict, rendered_dir: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    validation_by_path = {os.path.abspath(x["path"]): x for x in validation.get("results", [])}
    queue = []
    index_lines = ["# Review Queue", "", "Pilih hanya clip yang lolos pemeriksaan teknis dan review manual campaign.", "", "| Rank | Status | Video | Thumbnail |", "|---:|---|---|---|"]
    candidate_by_rank = {int(x.get("rank", 0)): x for x in candidates.get("candidates", [])}
    for video in sorted(Path(rendered_dir).glob("*.mp4")):
        result = validation_by_path.get(str(video.resolve()), validation_by_path.get(str(video)))
        if not result:
            continue
        rank = int(video.stem.split("-")[-1]) if video.stem.split("-")[-1].isdigit() else len(queue) + 1
        candidate = candidate_by_rank.get(rank, {})
        status = result.get("status", "needs_review")
        if status == "fail":
            queue_status = "blocked"
        else:
            queue_status = "pending_review"
        target_video = os.path.join(output_dir, video.name)
        shutil.copy2(video, target_video)
        thumbnail = os.path.join(output_dir, video.stem + ".jpg")
        try:
            _thumbnail(target_video, thumbnail)
        except Exception as exc:
            thumbnail = None
            result = dict(result)
            result.setdefault("review", []).append(f"thumbnail generation failed: {exc}")
        item = {
            "rank": rank,
            "status": queue_status,
            "video": os.path.relpath(target_video, output_dir),
            "thumbnail": os.path.relpath(thumbnail, output_dir) if thumbnail else None,
            "score": candidate.get("score"),
            "candidate": candidate,
            "validation": result,
            "caption_draft": _caption(plan, candidate),
            "checklist": _checklist(plan, result),
        }
        queue.append(item)
        index_lines.append(f"| {rank} | **{queue_status}** | [{video.name}]({video.name}) | {('[' + Path(thumbnail).name + '](' + Path(thumbnail).name + ')') if thumbnail else '-'} |")
        item_md = os.path.join(output_dir, f"clip-{rank:03d}.md")
        with open(item_md, "w", encoding="utf-8") as fh:
            fh.write(f"# Clip {rank:03d}\n\n- Status: **{queue_status}**\n- Score: `{candidate.get('score', '-')}`\n- Video: `{video.name}`\n\n## Caption draft\n\n{item['caption_draft'] or '-'}\n\n## Checklist\n\n")
            fh.write("\n".join(f"- [ ] {task}" for task in item["checklist"]))
            fh.write("\n\n## Validation\n\n```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```\n")
    payload = {"schema_version": 1, "campaign": plan.get("campaign"), "policy": plan.get("automation_policy"), "items": queue}
    with open(os.path.join(output_dir, "review.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(os.path.join(output_dir, "INDEX.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(index_lines) + "\n")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Build review queue")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--validation", required=True)
    ap.add_argument("--rendered-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    plan = json.load(open(args.plan, encoding="utf-8"))
    candidates = json.load(open(args.candidates, encoding="utf-8"))
    validation = json.load(open(args.validation, encoding="utf-8"))
    payload = build_queue(plan, candidates, validation, args.rendered_dir, args.out_dir)
    print("OK:", args.out_dir, "| items:", len(payload["items"]))


if __name__ == "__main__":
    main()
