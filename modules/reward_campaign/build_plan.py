#!/usr/bin/env python3
"""Compile campaign rules into a machine-readable production plan.

Usage:
  python run.py reward_plan data/reward_campaign/flight.txt --local
  python run.py reward_plan path/to/detail.json --json
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.campaign_rules import compile_plan, plan_markdown
from core.nextjs_flight import decode_blob
from modules.reward_campaign.pull_detail import extract_detail


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("kasih file HTML/Flight atau detail.json")
    path = args[0]
    if path.lower().endswith(".json"):
        detail = json.load(open(path, encoding="utf-8"))
    else:
        raw = open(path, encoding="utf-8").read()
        blob = raw if ("staticDetails" in raw and '"campaign"' in raw) else decode_blob(raw)
        detail = extract_detail(blob)
    plan = compile_plan(detail)
    out_dir = os.path.dirname(path) or "."
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", os.path.splitext(os.path.basename(path))[0])
    json_path = os.path.join(out_dir, stem + ".plan.json")
    md_path = os.path.join(out_dir, stem + ".PLAN.md")
    json.dump(plan, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(md_path, "w", encoding="utf-8").write(plan_markdown(plan))
    print("OK:", json_path)
    print("OK:", md_path)
    print("assets:", len(plan["production"]["asset_urls"]), "| gates:", sum(g["required"] for g in plan["gates"]))


if __name__ == "__main__":
    main()
