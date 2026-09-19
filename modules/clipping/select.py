#!/usr/bin/env python3
"""Rank non-overlapping clip candidates from a transcript."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.clip_candidates import select_candidates


def main() -> None:
    ap = argparse.ArgumentParser(description="Select highlight candidates")
    ap.add_argument("transcript", help="transcript.json")
    ap.add_argument("--plan", default=None, help="optional campaign plan.json")
    ap.add_argument("--min-seconds", type=float, default=20)
    ap.add_argument("--max-seconds", type=float, default=60)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    transcript = json.load(open(args.transcript, encoding="utf-8"))
    candidates = select_candidates(transcript, args.min_seconds, args.max_seconds, args.limit)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.transcript)), "candidates.json")
    payload = {"schema_version": 1, "transcript": transcript.get("input"), "candidates": candidates}
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
