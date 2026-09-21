#!/usr/bin/env python3
"""Offline campaign intelligence using a free local open-weight model."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

import requests

MODEL_REPO = os.getenv("SCRAPPER_AI_MODEL_REPO", "mmnga/Qwen3-4B-Instruct-2507-gguf")
MODEL_FILE = os.getenv("SCRAPPER_AI_MODEL_FILE", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
MODEL_SHA256 = os.getenv("SCRAPPER_AI_MODEL_SHA256", "01217501dd8c6741c544c32eb0d18b08e27b95475e1270e955da707fa2821e2c")
MODEL_URL = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILE}?download=true"
CACHE_DIR = Path(os.getenv("SCRAPPER_AI_CACHE", Path.home() / ".cache" / "scrapper-engine"))
MODEL_PATH = CACHE_DIR / MODEL_FILE

DEFAULT_PROFILE = {
    "preferred_topics": ["technology","artificial intelligence","software","coding","developer","business","education","science","creator","podcast","gaming"],
    "preferred_platforms": ["tiktok","youtube","instagram"],
    "preferred_workflow": ["official footage","provided clips","content bank","approved campaign assets","short-form clipping"],
    "excluded_topics": ["gambling","casino","adult content","nicotine","illegal drugs","weapons","fraud"],
}

def _load_profile() -> dict[str, Any]:
    path = Path(os.getenv("SCRAPPER_AI_PROFILE", "config/campaign_ai_profile.json"))
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else DEFAULT_PROFILE
    except Exception:
        return DEFAULT_PROFILE

def rules_fingerprint(campaign: dict[str, Any]) -> str:
    payload = {
        "title": campaign.get("title"), "brand": campaign.get("brand"),
        "description": campaign.get("description"), "platforms": campaign.get("platforms"),
        "type": campaign.get("type"), "requirements": campaign.get("requirements") or [],
        "resources": campaign.get("resources") or [], "payouts": campaign.get("payouts") or [],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def ensure_model() -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        digest = hashlib.sha256()
        with MODEL_PATH.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() == MODEL_SHA256:
            return str(MODEL_PATH)
        MODEL_PATH.unlink(missing_ok=True)
    tmp = MODEL_PATH.with_suffix(".download")
    print(f"AI: downloading {MODEL_REPO}/{MODEL_FILE} (~2.5 GB, cached after first run)")
    digest = hashlib.sha256()
    response = requests.get(MODEL_URL, stream=True, timeout=60)
    response.raise_for_status()
    with tmp.open("wb") as fh:
        for chunk in response.iter_content(1024 * 1024):
            if not chunk:
                continue
            fh.write(chunk)
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != MODEL_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"AI model checksum mismatch: {actual}")
    tmp.replace(MODEL_PATH)
    return str(MODEL_PATH)

def load_llm():
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise RuntimeError("llama-cpp-python belum terpasang") from exc
    model_path = ensure_model()
    threads = max(2, min(4, os.cpu_count() or 4))
    return Llama(model_path=model_path, n_ctx=16384, n_threads=threads, n_batch=256, n_gpu_layers=0, verbose=False)

def _json_from_text(text: str) -> Any:
    clean = text.strip()
    fence = chr(96) * 3
    if clean.startswith(fence):
        clean = clean[len(fence):]
        if clean.lstrip().lower().startswith("json"):
            clean = clean.lstrip()[4:]
        clean = clean.strip()
        if clean.endswith(fence):
            clean = clean[:-len(fence)].strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    starts = [p for p in (clean.find("{"), clean.find("[")) if p >= 0]
    start = min(starts, default=-1)
    if start < 0:
        raise ValueError("AI output is not JSON")
    for end in range(len(clean), start, -1):
        try:
            return json.loads(clean[start:end].strip())
        except json.JSONDecodeError:
            continue
    raise ValueError("AI output contains no valid JSON object")

def _num(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _int_or_none(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None

def normalize_ai_result(item: dict[str, Any], campaign_id: str) -> dict[str, Any]:
    rules = item.get("rules") if isinstance(item.get("rules"), dict) else {}
    fit = item.get("campaign_fit") if isinstance(item.get("campaign_fit"), dict) else {}
    fit_score = _num(fit.get("score"))
    if fit_score is not None:
        fit_score = max(0.0, min(1.0, fit_score))
    confidence = max(0.0, min(1.0, _num(item.get("confidence"), 0.0) or 0.0))
    return {
        "schema_version": 1, "campaign_id": campaign_id,
        "campaign_fit": {"score": fit_score, "label": str(fit.get("label") or "unknown"), "reason": str(fit.get("reason") or "")},
        "rules": {
            "source_policy": str(rules.get("source_policy") or "campaign_defined"),
            "platforms": list(rules.get("platforms") or []),
            "aspect_ratio": rules.get("aspect_ratio"),
            "min_duration_seconds": _int_or_none(rules.get("min_duration_seconds")),
            "max_duration_seconds": _int_or_none(rules.get("max_duration_seconds")),
            "subtitle_required": bool(rules.get("subtitle_required")),
            "subtitle_style": str(rules.get("subtitle_style") or "campaign_defined"),
            "watermark_required": bool(rules.get("watermark_required")),
            "third_party_watermark_allowed": bool(rules.get("third_party_watermark_allowed")),
            "official_audio_required": bool(rules.get("official_audio_required")),
            "cta_required": bool(rules.get("cta_required")),
            "cta_text": rules.get("cta_text"),
            "handles": list(rules.get("handles") or []),
            "hashtags": list(rules.get("hashtags") or []),
            "disclosures": list(rules.get("disclosures") or []),
            "topic_terms": list(rules.get("topic_terms") or []),
            "allowed_content": list(rules.get("allowed_content") or []),
            "prohibited_content": list(rules.get("prohibited_content") or []),
            "asset_sources": list(rules.get("asset_sources") or []),
            "posting_rules": list(rules.get("posting_rules") or []),
            "account_rules": list(rules.get("account_rules") or []),
        },
        "ambiguities": [str(x) for x in (item.get("ambiguities") or [])],
        "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
        "confidence": confidence,
    }

def _campaign_prompt_payload(campaign: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_id": campaign.get("id"), "title": campaign.get("title"), "brand": campaign.get("brand"),
        "category": campaign.get("category"), "type": campaign.get("type"), "platforms": campaign.get("platforms") or [],
        "description": campaign.get("description") or "", "requirements": campaign.get("requirements") or [],
        "resources": campaign.get("resources") or [], "payouts": campaign.get("payouts") or [],
    }

def _prompt(batch: Iterable[dict[str, Any]]) -> str:
    profile = _load_profile()
    return """You are the campaign-intelligence layer of a clipping production engine.
Read each campaign independently. Extract only what is supported by supplied text. Never invent a rule.
Identify every explicit production or posting rule that can affect clip validity.
Record CRITICAL ambiguity only when an unknown could change asset selection, edit/render decisions, or posting compliance.
Decide campaign_fit using this operator profile:
""" + json.dumps(profile, ensure_ascii=False) + """
Return ONLY JSON in this shape:
{"campaigns":[{"campaign_id":"...","campaign_fit":{"score":0.0,"label":"high|medium|low","reason":"..."},"rules":{
"source_policy":"official_only|provided_only|campaign_defined|unknown","platforms":[],"aspect_ratio":"9:16|null",
"min_duration_seconds":null,"max_duration_seconds":null,"subtitle_required":false,"subtitle_style":"campaign_defined",
"watermark_required":false,"third_party_watermark_allowed":false,"official_audio_required":false,
"cta_required":false,"cta_text":null,"handles":[],"hashtags":[],"disclosures":[],"topic_terms":[],
"allowed_content":[],"prohibited_content":[],"asset_sources":[],"posting_rules":[],"account_rules":[]},
"ambiguities":[],"evidence":[{"rule_path":"rules.aspect_ratio","quote":"source wording"}],"confidence":0.0}]}
Campaigns:
""" + json.dumps([_campaign_prompt_payload(x) for x in batch], ensure_ascii=False)

def analyze_campaigns(campaigns: list[dict[str, Any]], batch_size: int = 8) -> dict[str, dict[str, Any]]:
    if not campaigns:
        return {}
    llm = load_llm()
    results: dict[str, dict[str, Any]] = {}
    batch_size = max(1, batch_size)
    for start in range(0, len(campaigns), batch_size):
        batch = campaigns[start:start + batch_size]
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "Return strict JSON only. Do not explain outside JSON."},
                {"role": "user", "content": _prompt(batch)},
            ],
            temperature=0.1, top_p=0.8,
            max_tokens=min(6500, max(900, len(batch) * 800)),
            response_format={"type": "json_object"},
        )
        parsed = _json_from_text(response["choices"][0]["message"]["content"])
        items = parsed.get("campaigns", []) if isinstance(parsed, dict) else []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            cid = str(raw.get("campaign_id") or "")
            if cid:
                results[cid] = normalize_ai_result(raw, cid)
        for campaign in batch:
            cid = str(campaign.get("id") or "")
            if cid not in results:
                results[cid] = {
                    "schema_version": 1, "campaign_id": cid,
                    "campaign_fit": {"score": None, "label": "unknown", "reason": "AI omitted this campaign"},
                    "rules": {
                        "source_policy": "unknown", "platforms": campaign.get("platforms") or [],
                        "aspect_ratio": None, "min_duration_seconds": None, "max_duration_seconds": None,
                        "subtitle_required": False, "subtitle_style": "campaign_defined",
                        "watermark_required": False, "third_party_watermark_allowed": False,
                        "official_audio_required": False, "cta_required": False, "cta_text": None,
                        "handles": [], "hashtags": [], "disclosures": [], "topic_terms": [],
                        "allowed_content": [], "prohibited_content": [], "asset_sources": [],
                        "posting_rules": [], "account_rules": [],
                    },
                    "ambiguities": ["CRITICAL: AI omitted this campaign"], "evidence": [], "confidence": 0.0,
                }
    return results

__all__ = ["analyze_campaigns", "normalize_ai_result", "rules_fingerprint"]
