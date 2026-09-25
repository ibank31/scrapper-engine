#!/usr/bin/env python3
"""Rank non-overlapping clip candidates from a transcript."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.clip_candidates import segment_transcript, select_candidates, select_candidates_for_bands
from core.media_signals import source_quality_preflight


def main() -> None:
    ap = argparse.ArgumentParser(description="Select highlight candidates")
    ap.add_argument("transcript", help="transcript.json")
    ap.add_argument("--plan", default=None, help="optional campaign plan.json")
    ap.add_argument("--min-seconds", type=float, default=20)
    ap.add_argument("--max-seconds", type=float, default=60)
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--source", default=None, help="optional source media for quality and scene/audio signals")
    ap.add_argument("--bands-json", default=None)
    ap.add_argument("--media-top-n", type=int, default=24)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    transcript = json.load(open(args.transcript, encoding="utf-8"))
    plan = json.load(open(args.plan, encoding="utf-8")) if args.plan else None
    if args.bands_json:
        bands = json.loads(args.bands_json)
        candidates, diagnostics = select_candidates_for_bands(transcript, bands, args.limit, source_path=args.source, plan=plan, media_top_n=args.media_top_n)
    else:
        candidates = select_candidates(transcript, args.min_seconds, args.max_seconds, args.limit, source_path=args.source, plan=plan)
        diagnostics = {"bands": [], "candidate_pool_count": len(candidates), "candidate_count": len(candidates), "media_analyzed": len(candidates)}
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.transcript)), "candidates.json")
    units = segment_transcript(transcript)
    transcript_span = max((float(segment.get("end", 0)) for segment in transcript.get("segments", [])), default=0.0)
    payload = {
        "schema_version": 2,
        "transcript": transcript.get("input"),
        "source_quality": source_quality_preflight(args.source, transcript) if args.source else None,
        "selection": {
            "min_seconds": args.min_seconds,
            "max_seconds": args.max_seconds,
            "single_pass": bool(args.bands_json),
            "diagnostics": diagnostics,
            "max_gap_seconds": 3.0,
            "production_policy": "campaign-aware hook/context/payoff/pacing ranking",
            "transcript_span_seconds": round(transcript_span, 3),
            "unit_count": len(units),
            "candidate_count": len(candidates),
            "reason_if_empty": "no contiguous transcript window within duration bounds and pause budget" if not candidates else None,
        },
        "candidates": candidates,
    }
    json.dump(payload, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    md = out.rsplit(".", 1)[0] + ".md"
    lines = ["# Clip Candidates", "", f"Source: `{transcript.get('input')}`", "", "| Rank | Score | Time | Duration | Reason |", "|---:|---:|---|---:|---|"]
    for item in candidates:
        lines.append(f"| {item['rank']} | {item['score']} | {item['start']:.1f}s–{item['end']:.1f}s | {item['duration']:.1f}s | {', '.join(item['reasons']) or '-'} |")
        lines += ["", f"> {item['text']}", ""]
    open(md, "w", encoding="utf-8").write("\n".join(lines))
    print("OK:", out, "| candidates:", len(candidates))


if __name__ == "__main__":
    main()
