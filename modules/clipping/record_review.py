#!/usr/bin/env python3
"""Record Sorti's approve/reject decision for a reviewed clip.

Two sinks:
1. Local append-only audit log (always written): review-decisions.jsonl
2. Production API (only when --api-base is given and CLIPPER_REVIEW_TOKEN is
   set): POST /api/previews/<id>/review with x-review-token auth.

Recording a decision never publishes anything. Approve only marks the preview
as approved_for_manual_post; Sorti still submits manually to the campaign
platform.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

ACTIONS = {"approve": "approve", "setuju": "approve", "tolak": "reject", "reject": "reject"}


def build_decision(preview_id: str, decision: str, reason: str = "", reviewer: str = "Sorti") -> dict:
    action = ACTIONS.get(decision.strip().lower())
    if not action:
        raise ValueError(f"unknown decision: {decision!r} (use approve/setuju or reject/tolak)")
    if action in ("reject",) and not reason.strip():
        raise ValueError("reject requires a reason")
    return {
        "schema_version": 1,
        "preview_id": preview_id,
        "decision": decision.strip().lower(),
        "action": action,
        "reason": reason.strip(),
        "reviewer": reviewer,
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "published": False,  # decisions never auto-publish
    }


def append_local_log(entry: dict, log_path: str) -> str:
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return log_path


def post_to_api(api_base: str, entry: dict, token: str) -> dict:
    url = api_base.rstrip("/") + f"/api/previews/{entry['preview_id']}/review"
    payload = json.dumps({"action": entry["action"], "reason": entry["reason"], "reviewer": entry["reviewer"]}).encode()
    request = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"content-type": "application/json", "x-review-token": token})
    try:
        response = urllib.request.urlopen(request, timeout=30)
        return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"api review failed: HTTP {exc.code} {exc.read()[:200]!r}") from exc


def main() -> None:
    ap = argparse.ArgumentParser(description="Record a chat review decision for a clip")
    ap.add_argument("--preview-id", required=True)
    ap.add_argument("--decision", required=True, help="approve/setuju or reject/tolak")
    ap.add_argument("--reason", default="", help="required for reject")
    ap.add_argument("--reviewer", default="Sorti")
    ap.add_argument("--log", default=None, help="local audit log path")
    ap.add_argument("--api-base", default=None, help="production API base, e.g. https://clipper-engine.pages.dev")
    args = ap.parse_args()

    entry = build_decision(args.preview_id, args.decision, args.reason, args.reviewer)
    log_path = args.log or os.path.join(os.getcwd(), "review-decisions.jsonl")
    append_local_log(entry, log_path)
    print("OK: recorded locally ->", log_path)

    if args.api_base:
        token = os.environ.get("CLIPPER_REVIEW_TOKEN", "")
        if not token:
            print("WARN: --api-base given but CLIPPER_REVIEW_TOKEN is not set; skipped API call", file=sys.stderr)
            return
        result = post_to_api(args.api_base, entry, token)
        print("OK: api ->", json.dumps(result.get("preview", result), ensure_ascii=False)[:200])


if __name__ == "__main__":
    main()
