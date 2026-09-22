#!/usr/bin/env python3
"""Rank transcript candidates with an optional local GGUF model."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.semantic_ranker import rank_candidates_with_metadata


def main() -> None:
    ap = argparse.ArgumentParser(description="Semantic-rank subtitle candidates locally")
    ap.add_argument("candidates", help="candidates.json")
    ap.add_argument("--plan", required=True, help="campaign plan.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    candidates = json.load(open(args.candidates, encoding="utf-8"))
    plan = json.load(open(args.plan, encoding="utf-8"))
    ranked, runtime = rank_candidates_with_metadata(candidates.get("candidates") or [], plan)
    out = args.out or args.candidates
    payload = dict(candidates)
    payload["semantic_schema_version"] = 1
    payload["semantic_model"] = os.environ.get("CLIPPER_SEMANTIC_MODEL") or "deterministic-fallback"
    payload["semantic_runtime"] = runtime
    payload["candidates"] = ranked
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("OK:", out, "| candidates:", len(ranked), "| engine:", runtime["engine"], "| fallback:", runtime["fallback_used"], "| reason:", runtime["fallback_reason"])


if __name__ == "__main__":
    main()
