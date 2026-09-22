#!/usr/bin/env python3
"""Validate rendered clips against technical and campaign-aware gates."""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from fractions import Fraction

from core.relevance import check_candidate


def probe(path: str) -> dict:
    command = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def check_video(path: str, plan: dict | None, relevance: dict | None = None) -> dict:
    issues: list[str] = []
    review: list[str] = []
    try:
        data = probe(path)
    except Exception as exc:
        return {"path": path, "status": "fail", "issues": [f"ffprobe failed: {exc}"], "review": []}
    videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    audios = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if not videos:
        issues.append("video stream missing")
    else:
        video = videos[0]
        if int(video.get("width") or 0) != 1080 or int(video.get("height") or 0) != 1920:
            issues.append(f"expected 1080x1920, got {video.get('width')}x{video.get('height')}")
        if video.get("codec_name") != "h264":
            issues.append(f"expected h264 video, got {video.get('codec_name')}")
        if video.get("sample_aspect_ratio") not in {None, "1:1"}:
            issues.append(f"expected square pixels, got SAR {video.get('sample_aspect_ratio')}")
        try:
            fps = float(Fraction(video.get("r_frame_rate", "0/1")))
            if fps < 23 or fps > 60:
                issues.append(f"unsupported frame rate: {fps:.2f}")
        except (ValueError, ZeroDivisionError):
            issues.append("invalid frame rate")
    if not audios:
        issues.append("audio stream missing")
    elif audios[0].get("codec_name") != "aac":
        issues.append(f"expected aac audio, got {audios[0].get('codec_name')}")
    elif str(audios[0].get("sample_rate") or "") != "48000":
        issues.append(f"expected 48 kHz audio, got {audios[0].get('sample_rate')} Hz")
    production = (plan or {}).get("production") or {}
    if production.get("watermark_required"):
        review.append("visually verify the official watermark asset, position, opacity, and full-duration coverage")
    if production.get("no_third_party_watermark"):
        review.append("visually verify no third-party watermark is visible")
    if production.get("official_audio_required"):
        review.append("attach the official platform sound during manual posting and verify it is primary audio")
    if production.get("required_handles"):
        review.append("verify required handles/tags in native platform fields")
    if production.get("cta_urls"):
        review.append("verify CTA placement in bio, caption, or pinned comment as specified")
    if relevance:
        if relevance.get("status") == "blocked":
            issues.append("campaign relevance failed: " + str(relevance.get("reason")))
        elif relevance.get("status") == "uncertain":
            review.append("campaign relevance is uncertain; human must verify topic and brand context")
    status = "fail" if issues else ("needs_review" if review else "pass")
    return {"path": path, "status": status, "issues": issues, "review": review, "relevance": relevance, "metadata": data.get("format", {})}


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate rendered clips")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--video", action="append", default=[])
    ap.add_argument("--glob", dest="glob_pattern", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--candidates", default=None)
    args = ap.parse_args()
    plan = json.load(open(args.plan, encoding="utf-8")) if args.plan else None
    candidates = json.load(open(args.candidates, encoding="utf-8")) if args.candidates else {"candidates": []}
    relevance_by_rank = {int(x.get("rank", 0)): check_candidate(plan or {}, x) for x in candidates.get("candidates", [])}
    paths = list(args.video)
    if args.glob_pattern:
        paths.extend(sorted(glob.glob(args.glob_pattern)))
    if not paths:
        raise SystemExit("kasih --video PATH atau --glob PATTERN")
    results = []
    for path in paths:
        stem = os.path.basename(path).split(".", 1)[0].split("-")[-1]
        try:
            relevance = relevance_by_rank.get(int(stem))
        except ValueError:
            relevance = None
        results.append(check_video(path, plan, relevance))
    payload = {"schema_version": 1, "plan": args.plan, "results": results}
    out = args.out or "validation.json"
    json.dump(payload, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    md = out.rsplit(".", 1)[0] + ".md"
    lines = ["# Clip Validation", "", "| File | Status | Issues | Manual review |", "|---|---|---|---|"]
    for result in results:
        lines.append(f"| `{result['path']}` | **{result['status']}** | {'; '.join(result['issues']) or '-'} | {'; '.join(result['review']) or '-'} |")
    open(md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("OK:", out, "|", ", ".join(f"{r['status']}={sum(x['status'] == r['status'] for x in results)}" for r in results))
    raise SystemExit(1 if any(r["status"] == "fail" for r in results) else 0)


if __name__ == "__main__":
    main()
