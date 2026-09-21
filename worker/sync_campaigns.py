#!/usr/bin/env python3
"""Daily live campaign sync + offline AI campaign intelligence + auto-queue."""
from __future__ import annotations
import concurrent.futures
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fetch import fetch_text
from core.nextjs_flight import decode_blob
from core.campaign_ai import analyze_campaigns, rules_fingerprint
from core.campaign_priority import score_campaign
from core.campaign_rules import compile_plan
from modules.reward_campaign.pull_detail import extract_detail

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _headers(token: str) -> dict[str, str]:
    return {"content-type": "application/json", "x-worker-token": token}

def _fetch_detail(campaign: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
    cid = str(campaign.get("id") or "")
    if not cid:
        return cid, None, "missing campaign id"
    try:
        html = fetch_text("https://contentrewards.com/discover/" + cid, retries=1)
        return cid, extract_detail(decode_blob(html)), None
    except Exception as exc:
        return cid, None, str(exc)[:300]

def _hydrate(campaign: dict[str, Any]) -> dict[str, Any]:
    _, detail, error = _fetch_detail(campaign)
    if detail:
        dc = detail.get("campaign") or {}
        static = detail.get("staticDetails") or {}
        campaign["description"] = dc.get("description") or campaign.get("description") or ""
        campaign["requirements"] = static.get("requirements") or []
        campaign["resources"] = static.get("resources") or []
        campaign["payouts"] = static.get("payouts") or []
        campaign["detail_fetched_at"] = _now()
        campaign.pop("detail_fetch_error", None)
    else:
        campaign["detail_fetch_error"] = error or "unknown detail error"
        campaign.setdefault("requirements", [])
        campaign.setdefault("resources", [])
        campaign.setdefault("payouts", [])
    return campaign

def _fetch_existing(api: str, token: str) -> dict[str, dict[str, Any]]:
    try:
        response = requests.get(api + "/api/campaign-intelligence", headers=_headers(token), timeout=60)
        response.raise_for_status()
        rows = response.json().get("campaigns", [])
        return {str(row.get("id")): row for row in rows if row.get("id")}
    except Exception as exc:
        print("(!) existing intelligence unavailable:", str(exc)[:200])
        return {}

def _build_detail(campaign: dict[str, Any]) -> dict[str, Any]:
    c = dict(campaign)
    c["socialPlatforms"] = c.get("platforms") or []
    c["campaignType"] = c.get("type")
    return {
        "campaign": c,
        "staticDetails": {
            "requirements": c.get("requirements") or [],
            "resources": c.get("resources") or [],
            "payouts": c.get("payouts") or [],
        },
        "ai_rules": c.get("ai_rules") or {},
    }

def _critical(ambiguities: list[Any]) -> bool:
    return any("critical" in str(x).lower() for x in ambiguities)

def _apply_ai(campaign: dict[str, Any], ai: dict[str, Any] | None, previous: dict[str, Any] | None, rh: str) -> None:
    if ai:
        campaign["ai_rules"] = ai
        campaign["ai_rules_status"] = "pass" if float(ai.get("confidence") or 0) >= 0.70 and not _critical(ai.get("ambiguities") or []) else "needs_review"
        campaign["ai_analyzed_at"] = _now()
        campaign["rules_hash"] = rh
        campaign["ai_fit_score"] = (ai.get("campaign_fit") or {}).get("score")
        return
    if previous and previous.get("rules_hash") == rh and previous.get("ai_rules_json"):
        try:
            cached = json.loads(previous["ai_rules_json"]) if isinstance(previous["ai_rules_json"], str) else previous["ai_rules_json"]
            campaign["ai_rules"] = cached
            campaign["ai_rules_status"] = previous.get("ai_rules_status") or "needs_review"
            campaign["ai_analyzed_at"] = previous.get("ai_analyzed_at")
            campaign["rules_hash"] = rh
            campaign["ai_fit_score"] = (cached.get("campaign_fit") or {}).get("score")
            return
        except Exception:
            pass
    campaign["ai_rules"] = {}
    campaign["ai_rules_status"] = "needs_review"
    campaign["ai_analyzed_at"] = None
    campaign["rules_hash"] = rh
    campaign["ai_fit_score"] = None

def _has_public_material_hint(campaign: dict[str, Any]) -> bool:
    """Heuristic: campaign lists Drive/YouTube/direct media or Google Docs links."""
    blobs: list[str] = []
    for key in ("resources", "requirements"):
        for item in campaign.get(key) or []:
            if isinstance(item, dict):
                blobs.append(json.dumps(item, ensure_ascii=False))
            else:
                blobs.append(str(item))
    plan = campaign.get("plan_json") or {}
    prod = plan.get("production") if isinstance(plan, dict) else {}
    for url in (prod or {}).get("asset_urls") or []:
        blobs.append(str(url))
    text = " ".join(blobs).lower()
    markers = (
        "drive.google.com",
        "docs.google.com",
        "youtube.com",
        "youtu.be",
        ".mp4",
        ".mov",
        "frame.io",
        "dropbox.com",
    )
    return any(m in text for m in markers)

def _auto_queue(api: str, token: str, campaigns: list[dict[str, Any]]) -> None:
    """Queue top scored campaigns that look processable — human only reviews later."""
    if os.getenv("CLIPPER_AUTO_QUEUE", "1").strip() in {"0", "false", "no"}:
        print("Auto-queue disabled by CLIPPER_AUTO_QUEUE")
        return
    max_jobs = max(0, min(3, int(os.getenv("CLIPPER_AUTO_QUEUE_MAX", "1"))))
    if max_jobs == 0:
        return
    # Prefer high score + material hints; skip explicit AI hard-fail.
    ranked = sorted(
        [c for c in campaigns if str(c.get("status") or "active").lower() == "active"],
        key=lambda c: float(c.get("score") or 0),
        reverse=True,
    )
    queued = 0
    for c in ranked:
        if queued >= max_jobs:
            break
        cid = str(c.get("id") or "")
        if not cid:
            continue
        ai_status = str(c.get("ai_rules_status") or "").lower()
        if ai_status in {"fail", "rejected", "blocked"}:
            continue
        if not _has_public_material_hint(c):
            continue
        try:
            r = requests.post(
                f"{api}/api/campaigns/{cid}/jobs",
                headers=_headers(token),
                timeout=30,
            )
            if r.status_code not in (200, 201):
                print(f"(!) queue create failed {cid}: HTTP {r.status_code} {r.text[:120]}")
                continue
            body = r.json()
            job = body.get("job") or {}
            job_id = job.get("id")
            if not job_id:
                continue
            if body.get("deduped"):
                print(f"skip already open job for {cid}: {job_id}")
                continue
            # Dispatch GitHub worker immediately when possible
            d = requests.post(
                f"{api}/api/jobs/{job_id}/run",
                headers=_headers(token),
                timeout=30,
            )
            print(f"auto-queued {cid} job={job_id} dispatch={d.status_code}")
            queued += 1
        except Exception as exc:
            print(f"(!) auto-queue error {cid}: {str(exc)[:200]}")
    print(f"Auto-queue finished: {queued} job(s)")

def main() -> None:
    api = os.environ["CLIPPER_API_URL"].rstrip("/")
    token = os.environ["CLIPPER_WORKER_TOKEN"]

    subprocess.run([sys.executable, "run.py", "reward_campaign"], cwd=ROOT, check=True)
    data_path = ROOT / "data/reward_campaign/campaigns.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    campaigns = data.get("campaigns", [])
    print(f"Scraped {len(campaigns)} campaigns")

    active = [c for c in campaigns if str(c.get("status") or "active").lower() == "active"]
    detail_workers = max(1, min(6, int(os.getenv("CLIPPER_DETAIL_WORKERS", "5"))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=detail_workers) as pool:
        hydrated = list(pool.map(_hydrate, active))
    inactive = [c for c in campaigns if c not in active]
    campaigns = hydrated + inactive

    existing = _fetch_existing(api, token)
    candidates: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for c in campaigns:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        rh = rules_fingerprint(c)
        hashes[cid] = rh
        previous = existing.get(cid)
        if previous and previous.get("rules_hash") == rh and previous.get("ai_rules_json"):
            _apply_ai(c, None, previous, rh)
        else:
            candidates.append(c)

    print(f"AI analysis needed: {len(candidates)} / {len(campaigns)}")
    ai_results: dict[str, dict[str, Any]] = {}
    if candidates:
        try:
            batch_size = max(2, min(10, int(os.getenv("CLIPPER_AI_BATCH_SIZE", "8"))))
            ai_results = analyze_campaigns(candidates, batch_size=batch_size)
        except Exception as exc:
            print("(!) local AI unavailable:", str(exc)[:300])

    for c in campaigns:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        previous = existing.get(cid)
        if cid in ai_results:
            _apply_ai(c, ai_results[cid], previous, hashes[cid])
        elif not c.get("ai_rules"):
            _apply_ai(c, None, previous, hashes[cid])

        detail = _build_detail(c)
        plan = compile_plan(detail)
        plan["rules_hash"] = hashes[cid]
        plan["ai_rules_status"] = c.get("ai_rules_status")
        c["plan_json"] = plan
        c.update(score_campaign(c))

        if c.get("detail_fetch_error"):
            c["flags"] = list(dict.fromkeys((c.get("flags") or []) + ["DETAIL:needs_review"]))

    data["updated"] = _now()
    data["campaigns"] = campaigns
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    response = requests.post(api + "/api/campaigns/sync", headers=_headers(token), json={"campaigns": campaigns}, timeout=180)
    response.raise_for_status()
    print("Synced campaigns:", response.json())

    # Machine path: after intelligence is fresh, queue top processable campaigns.
    _auto_queue(api, token, campaigns)

if __name__ == "__main__":
    main()
