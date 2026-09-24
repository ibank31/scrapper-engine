#!/usr/bin/env python3
"""Run a legal, synthetic 20–30 second known-good clipping trace locally."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.campaign_rules import compile_plan
from core.clip_candidates import select_candidates
from core.output_selection import select_required_output_pair
from modules.clipping.validate import check_video


def word_timestamps(sentences: list[tuple[float, str]]) -> dict:
    segments = []
    for start, sentence in sentences:
        words = sentence.split()
        step = 17.0 / max(1, len(words))
        timed = []
        for index, word in enumerate(words):
            left = start + index * step
            right = start + (index + 1) * step - 0.15
            timed.append({"start": round(left, 3), "end": round(right, 3), "word": word})
        segments.append({"start": start, "end": start + 17.0, "text": sentence, "words": timed})
    return {"segments": segments, "language": "en", "fixture": "synthetic-legal-spoken-moment-v1"}


def build_detail() -> dict:
    return {
        "campaign": {"id": "fixture-campaign-001", "title": "Known Good Founder Education", "brand": "Fixture Brand", "status": "active", "socialPlatforms": ["tiktok", "instagram"]},
        "description": "Create short educational clips for founders and students.",
        "docs_text": "Clip Length: 15–30 seconds. Use a complete spoken moment. Target two audiences: founders and students.",
        "requirements": [{"text": "Use vertical 9:16 video with readable burned-in subtitles.", "isMandatory": True}],
        "ai_rules": {"confidence": 0.99, "rules": {"min_duration_seconds": 15, "max_duration_seconds": 30, "subtitle_required": True, "subtitle_delivery_profile": "burned_in", "audience_tiers": {"tier_1": {"terms": ["founders", "startup"]}, "tier_2": {"terms": ["students", "learning"]}}}},
    }


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    plan = compile_plan(build_detail())
    plan_path = output / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    transcript = word_timestamps([
        (0.0, "Founders can build a better startup by testing one small customer problem first. The lesson is simple: listen, measure, and improve before scaling."),
        (20.0, "Students can learn faster by turning every assignment into a small experiment. The answer is to ask a clear question, test it, and reflect on the result."),
    ])
    transcript_path = output / "transcript.json"
    transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source = output / "source.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "38", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", str(source)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    candidates = select_candidates(transcript, min_seconds=15, max_seconds=30, limit=12, source_path=str(source), plan=plan)
    for item in candidates:
        item["source"] = str(source)
        item["source_asset_id"] = "fixture-source-001"
        item["source_hash"] = source_hash
    pair = select_required_output_pair(candidates, plan["output_contract"])
    if not pair["ok"]:
        raise SystemExit(f"known-good fixture selection failed: {json.dumps(pair, indent=2)}")
    selected = pair["selected"]
    for rank, item in enumerate(selected, 1):
        item["rank"] = rank
    candidates_path = output / "candidates.json"
    candidates_path.write_text(json.dumps({"candidates": selected}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_dir = output / "renders"
    subprocess.run([sys.executable, "modules/clipping/render.py", str(source), str(candidates_path), "--transcript", str(transcript_path), "--plan", str(plan_path), "--out-dir", str(render_dir), "--static-crop", "--preset", "veryfast", "--crf", "28"], cwd=ROOT, check=True)
    validation = []
    for item in selected:
        path = render_dir / f"clip-{int(item['rank']):03d}.mp4"
        result = check_video(str(path), plan, candidate=item)
        validation.append(result)
        if result["status"] == "fail":
            raise SystemExit(f"known-good fixture validation failed: {json.dumps(result, indent=2)}")
    manifest = {"schema_version": 1, "fixture": "known-good-v1", "legal_basis": "synthetic testsrc2 video and generated transcript; no third-party media", "intake": {"source": str(source), "source_hash": source_hash, "duration_seconds": 38, "content_type": "video/mp4"}, "transcript": {"path": str(transcript_path), "segments": len(transcript["segments"])}, "candidate": {"count": len(candidates), "selected": selected}, "selection": pair["diagnostics"], "render": {"directory": str(render_dir), "artifacts": [str(render_dir / f"clip-{int(item['rank']):03d}.mp4") for item in selected]}, "validation": {"results": validation}, "review_manifest": {"status": "pending_review", "items": [{"rank": item["rank"], "candidate_id": item.get("candidate_id"), "tier": item.get("tier"), "artifact": str(render_dir / f"clip-{int(item['rank']):03d}.mp4"), "human_review_required": True} for item in selected]}}
    manifest_path = output / "review-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="scrapper-known-good-") as temp:
        result = run(Path(args.out) if args.out else Path(temp) / "trace")
        print(json.dumps({"fixture": result["fixture"], "selected": result["selection"].get("actual_selected"), "validation": [x["status"] for x in result["validation"]["results"]], "manifest": str(Path(args.out) / "review-manifest.json") if args.out else "temporary trace"}, indent=2))


if __name__ == "__main__":
    main()
