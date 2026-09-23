#!/usr/bin/env python3
"""Render reviewable 9:16 clips with face-aware framing and clean captions."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.captioning import write_srt
from core.visual_crop import crop_filter


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Render 9:16 clips for review")
    ap.add_argument("input", help="source video")
    ap.add_argument("candidates", help="candidates.json")
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--watermark", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--no-subtitles", action="store_true")
    ap.add_argument("--force-subtitles", action="store_true", help="add captions as a quality enhancement even when campaign does not require them")
    ap.add_argument("--static-crop", action="store_true", help="disable face tracking for troubleshooting")
    ap.add_argument("--preset", default=os.environ.get("CLIPPER_FFMPEG_PRESET", "medium"), help="x264 preset (veryfast/faster/medium)")
    ap.add_argument("--crf", default=os.environ.get("CLIPPER_FFMPEG_CRF", "19"), help="x264 CRF quality (higher=faster/smaller)")
    args = ap.parse_args()
    payload = json.load(open(args.candidates, encoding="utf-8"))
    transcript = json.load(open(args.transcript, encoding="utf-8")) if args.transcript else None
    plan = json.load(open(args.plan, encoding="utf-8")) if args.plan else None
    production = (plan or {}).get("production") or {}
    # Captions are a machine quality default for spoken short-form video.
    # --no-subtitles remains an explicit troubleshooting escape hatch.
    if not args.no_subtitles and not transcript:
        raise SystemExit("transcript wajib tersedia untuk render normal karena subtitle adalah quality policy")
    subtitles_enabled = bool(transcript and not args.no_subtitles)
    if production.get("watermark_required") and not args.watermark:
        raise SystemExit("campaign mewajibkan watermark, tetapi --watermark belum diberikan")
    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(args.candidates)), "renders")
    os.makedirs(out_dir, exist_ok=True)
    try:
        base_crop = f"{crop_filter(args.input)},setsar=1" if not args.static_crop else "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    except Exception as exc:
        print(f"WARN: face tracking unavailable, using centered crop: {exc}", file=sys.stderr)
        base_crop = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    with tempfile.TemporaryDirectory(prefix="clip-subs-") as temp:
        for item in payload.get("candidates", []):
            rank = int(item.get("rank", 0))
            output = os.path.join(out_dir, f"clip-{rank:03d}.mp4")
            filters = [base_crop]
            subtitle_path = None
            if subtitles_enabled:
                subtitle_path = os.path.join(temp, f"{rank:03d}.srt")
                write_srt(transcript, item, subtitle_path)
                subtitle_style = "FontName=DejaVu Sans,FontSize=42,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=4,Shadow=1,Alignment=2,MarginV=430,MarginL=90,MarginR=90,WrapStyle=2"
                filters.append("subtitles='" + _escape_filter_path(subtitle_path) + "':force_style='" + subtitle_style + "'")
            command = ["ffmpeg", "-y", "-ss", str(item["start"]), "-t", str(item["duration"]), "-i", args.input]
            if args.watermark:
                command += ["-i", args.watermark]
                base = ",".join(filters)
                complex_filter = f"[0:v]{base}[base];[1:v]format=rgba,colorchannelmixer=aa=0.10[wm];[base][wm]overlay=24:24:format=auto:eof_action=repeat[v]"
                command += ["-filter_complex", complex_filter, "-map", "[v]", "-map", "0:a?", "-shortest"]
            else:
                command += ["-vf", ",".join(filters)]
            command += ["-r", "30", "-c:v", "libx264", "-preset", str(args.preset), "-crf", str(args.crf), "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-af", "loudnorm=I=-14:LRA=11:TP=-1.5", "-movflags", "+faststart", output]
            try:
                _run(command)
                print("OK:", output)
            except subprocess.CalledProcessError as exc:
                print("FAIL:", output, file=sys.stderr)
                print(exc.stderr[-1600:] if exc.stderr else "ffmpeg error", file=sys.stderr)
                raise
    print("rendered:", out_dir)


if __name__ == "__main__":
    main()
