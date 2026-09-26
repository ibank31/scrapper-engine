#!/usr/bin/env python3
"""Daily live campaign sync + Gemini AI + readiness ranking + optional auto-queue."""
from __future__ import annotations
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fetch import fetch_text, fetch_bytes
from core.nextjs_flight import decode_blob
from core.campaign_ai import analyze_campaigns, rules_fingerprint
from core.campaign_priority import score_campaign
from core.campaign_readiness import STATUS_KETAT, STATUS_SIAP, apply_readiness, readiness_sort_key
from core.campaign_rules import compile_plan
from core.campaign_exclusions import excluded_campaign_terms
from core.material_acquisition import build_legacy_compatible_policy, material_plan_fingerprint, validate_material_policy
from modules.reward_campaign.pull_detail import extract_detail

DOC_ID_RE = re.compile(r"docs\.google\.com/document/d/([A-Za-z0-9_-]+)", re.I)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _headers(token: str) -> dict[str, str]:
    return {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "x-worker-token": token,
    }

def _fetch_detail(campaign: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
    cid = str(campaign.get("id") or "")
    if not cid:
        return cid, None, "missing campaign id"
    try:
        html = fetch_text("https://contentrewards.com/discover/" + cid, retries=1)
        return cid, extract_detail(decode_blob(html)), None
    except Exception as exc:
        return cid, None, str(exc)[:300]

def _collect_doc_ids(campaign: dict[str, Any]) -> list[str]:
    blob_parts: list[str] = [json.dumps(campaign.get("resources") or [], ensure_ascii=False)]
    blob_parts.append(str(campaign.get("description") or ""))
    for req in campaign.get("requirements") or []:
        blob_parts.append(json.dumps(req, ensure_ascii=False) if isinstance(req, dict) else str(req))
    text = "\n".join(blob_parts)
    return list(dict.fromkeys(DOC_ID_RE.findall(text)))[:3]

def _fetch_public_docs(campaign: dict[str, Any]) -> None:
    """Best-effort public Google Docs export for rules text (no login)."""
    chunks: list[str] = []
    for doc_id in _collect_doc_ids(campaign):
        try:
            raw = fetch_bytes(
                f"https://docs.google.com/document/d/{doc_id}/export?format=txt",
                retries=1,
                timeout=45,
                min_bytes=20,
            )
            text = raw.decode("utf-8", "ignore").strip()
            if text:
                chunks.append(text[:12000])
        except Exception as exc:
            chunks.append(f"FAIL {doc_id}: {str(exc)[:120]}")
    if chunks:
        campaign["docs_text"] = "\n\n".join(chunks)

def _hydrate(campaign: dict[str, Any]) -> dict[str, Any]:
    _, detail, error = _fetch_detail(campaign)
    if detail:
        dc = detail.get("campaign") or {}
        static = detail.get("staticDetails") or {}
        campaign["description"] = dc.get("description") or campaign.get("description") or ""
        campaign["requirements"] = static.get("requirements") or []
        campaign["resources"] = static.get("resources") or []
        campaign["payouts"] = static.get("payouts") or []
        # Prefer explicit content type from live payload when present
        for key in ("contentType", "campaignContentType", "content_type"):
            if dc.get(key):
                campaign["content_type"] = dc.get(key)
                break
        campaign["detail_fetched_at"] = _now()
        campaign.pop("detail_fetch_error", None)
        _fetch_public_docs(campaign)
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

def _cache_is_current(previous: dict[str, Any] | None, rules_hash: str) -> bool:
    """Return True only for intelligence produced by the current evidence contract."""
    if not previous or previous.get("rules_hash") != rules_hash or not previous.get("ai_rules_json"):
        return False
    try:
        cached = json.loads(previous["ai_rules_json"]) if isinstance(previous["ai_rules_json"], str) else previous["ai_rules_json"]
    except (TypeError, ValueError):
        return False
    if not isinstance(cached, dict) or cached.get("schema_version") != 2:
        return False
    if not cached.get("source_hash") or not cached.get("source_ledger"):
        return False
    contract = cached.get("evidence_contract")
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        return False
    if not isinstance(contract.get("verified"), list) or not isinstance(contract.get("unverified"), list):
        return False
    if (cached.get("rules") or {}).get("material_policy") is None:
        return False
    return True


def _target_campaign_ids(value: str | None = None) -> set[str]:
    raw = value if value is not None else os.getenv("CLIPPER_CAMPAIGN_IDS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _campaigns_needing_ai(
    campaigns: list[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    *,
    force_ai: bool,
    target_ids: set[str],
) -> list[dict[str, Any]]:
    """Return only campaigns eligible for AI analysis in this run.

    When targeted migration is requested, non-target campaigns are never sent to
    the model, even when their cache is stale. This keeps migration bounded and
    prevents a one-campaign repair from silently becoming a corpus migration.
    """
    candidates: list[dict[str, Any]] = []
    for campaign in campaigns:
        cid = str(campaign.get("id") or "")
        if not cid or (target_ids and cid not in target_ids):
            continue
        rh = rules_fingerprint(campaign)
        previous = existing.get(cid)
        if force_ai or not _cache_is_current(previous, rh):
            candidates.append(campaign)
    return candidates


def _apply_ai(campaign: dict[str, Any], ai: dict[str, Any] | None, previous: dict[str, Any] | None, rh: str) -> None:
    if ai:
        campaign["ai_rules"] = ai
        campaign["ai_rules_status"] = "pass" if float(ai.get("confidence") or 0) >= 0.70 and not _critical(ai.get("ambiguities") or []) else "needs_review"
        campaign["ai_analyzed_at"] = _now()
        campaign["rules_hash"] = rh
        campaign["ai_fit_score"] = (ai.get("campaign_fit") or {}).get("score")
        return
    if previous and _cache_is_current(previous, rh):
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

def _auto_queue(api: str, token: str, campaigns: list[dict[str, Any]]) -> None:
    """Optional: queue only siap/ketat clipping. Default off for user-driven flow."""
    if os.getenv("CLIPPER_AUTO_QUEUE", "0").strip() in {"0", "false", "no", ""}:
        print("Auto-queue off (user chooses campaign). Set CLIPPER_AUTO_QUEUE=1 to enable.")
        return
    max_jobs = max(0, min(3, int(os.getenv("CLIPPER_AUTO_QUEUE_MAX", "1"))))
    if max_jobs == 0:
        return
    ranked = sorted(
        [
            c for c in campaigns
            if str(c.get("status") or "active").lower() == "active"
            and c.get("is_clipping")
            and c.get("readiness_status") in {STATUS_SIAP, STATUS_KETAT}
        ],
        key=readiness_sort_key,
    )
    queued = 0
    for c in ranked:
        if queued >= max_jobs:
            break
        cid = str(c.get("id") or "")
        if not cid:
            continue
        try:
            r = requests.post(f"{api}/api/campaigns/{cid}/jobs", headers=_headers(token), timeout=30)
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
            d = requests.post(f"{api}/api/jobs/{job_id}/run", headers=_headers(token), timeout=30)
            print(f"auto-queued {cid} status={c.get('readiness_status')} job={job_id} dispatch={d.status_code}")
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

    excluded_count = 0
    for campaign in campaigns:
        matches = excluded_campaign_terms(campaign)
        if matches:
            campaign["status"] = "blocked"
            campaign["excluded"] = True
            campaign["exclusion_reason"] = "excluded campaign category: " + ", ".join(matches)
            campaign["flags"] = list(dict.fromkeys((campaign.get("flags") or []) + ["EXCLUDED:GAMBLING_OR_MONEY_GAME"]))
            excluded_count += 1
    print(f"Excluded by deterministic policy: {excluded_count}")

    # Do not fetch details, download docs, or spend AI quota on excluded rows.
    active = [c for c in campaigns if str(c.get("status") or "active").lower() == "active"]
    detail_workers = max(1, min(6, int(os.getenv("CLIPPER_DETAIL_WORKERS", "5"))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=detail_workers) as pool:
        hydrated = list(pool.map(_hydrate, active))
    inactive = [c for c in campaigns if str(c.get("status") or "active").lower() != "active"]
    campaigns = hydrated + inactive

    existing = _fetch_existing(api, token)
    force_ai = os.getenv("CLIPPER_FORCE_AI", "0").strip().lower() in {"1", "true", "yes"}
    target_ids = _target_campaign_ids()
    hashes: dict[str, str] = {
        str(c.get("id") or ""): rules_fingerprint(c)
        for c in campaigns
        if c.get("id")
    }
    candidates = _campaigns_needing_ai(campaigns, existing, force_ai=force_ai, target_ids=target_ids)
    for c in campaigns:
        cid = str(c.get("id") or "")
        if not cid or cid in {str(item.get("id") or "") for item in candidates}:
            continue
        previous = existing.get(cid)
        _apply_ai(c, None, previous, hashes.get(cid, ""))

    print(f"AI analysis needed: {len(candidates)} / {len(campaigns)}")
    ai_results: dict[str, dict[str, Any]] = {}
    if candidates:
        try:
            batch_size = max(2, min(10, int(os.getenv("CLIPPER_AI_BATCH_SIZE", "8"))))
            ai_results = analyze_campaigns(candidates, batch_size=batch_size)
        except Exception as exc:
            print("(!) Gemini AI unavailable:", str(exc)[:300])

    readiness_counts: dict[str, int] = {}
    for c in campaigns:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        previous = existing.get(cid)
        if cid in ai_results:
            _apply_ai(c, ai_results[cid], previous, hashes.get(cid, ""))
        elif not c.get("ai_rules"):
            _apply_ai(c, None, previous, hashes.get(cid, ""))

        detail = _build_detail(c)
        plan = compile_plan(detail)
        plan["rules_hash"] = hashes.get(cid)
        plan["ai_rules_status"] = c.get("ai_rules_status")
        c["plan_json"] = plan
        c.update(score_campaign(c))
        apply_readiness(c)
        readiness_counts[c.get("readiness_status") or "?"] = readiness_counts.get(c.get("readiness_status") or "?", 0) + 1

        if c.get("detail_fetch_error"):
            c["flags"] = list(dict.fromkeys((c.get("flags") or []) + ["DETAIL:needs_review"]))

    campaigns.sort(key=readiness_sort_key)
    print("Readiness:", readiness_counts)

    sync_campaigns = [c for c in campaigns if str(c.get("id") or "") in target_ids] if target_ids else campaigns
    if target_ids:
        print(f"Targeted campaign sync: {len(sync_campaigns)} / {len(target_ids)} requested")

    data["updated"] = _now()
    data["campaigns"] = campaigns
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    response = requests.post(api + "/api/campaigns/sync", headers=_headers(token), json={"campaigns": sync_campaigns}, timeout=180)
    response.raise_for_status()
    print("Synced campaigns:", response.json())

    _auto_queue(api, token, campaigns)

if __name__ == "__main__":
    main()
