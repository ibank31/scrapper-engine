#!/usr/bin/env python3
"""Evidence contracts for campaign intelligence.

This module keeps source provenance deterministic and independent from any
specific LLM provider. AI may propose evidence quotes; this module verifies
whether those quotes actually exist in the supplied campaign sources.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SOURCE_PRIORITY = {"source_of_truth": 100, "documents": 90, "requirement": 80, "description": 70}

SCHEMA_VERSION = 1


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_documents(campaign: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic source documents from the campaign payload."""
    docs: list[dict[str, Any]] = []

    def add(source_type: str, text: Any, location: str = "") -> None:
        normalized = _norm_text(text)
        if normalized:
            meta = campaign.get("source_metadata", {})
            meta = meta.get(location, {}) if isinstance(meta, dict) and isinstance(meta.get(location, {}), dict) else {}
            docs.append({
                "source_type": source_type,
                "location": location,
                "text": normalized,
                "source_url": str(meta.get("source_url") or "") or None,
                "source_timestamp": str(meta.get("source_timestamp") or "") or None,
                "extraction_method": str(meta.get("extraction_method") or "structured_text_normalization"),
                "source_priority": int(meta.get("source_priority", SOURCE_PRIORITY.get(source_type, 0))),
            })

    add("description", campaign.get("description"))
    requirements = campaign.get("requirements") or []
    for index, item in enumerate(requirements):
        text = item.get("text") if isinstance(item, dict) else item
        add("requirement", text, f"requirements[{index}]")

    add("documents", campaign.get("docs_text") or campaign.get("documents"))

    source_of_truth = campaign.get("source_of_truth")
    if isinstance(source_of_truth, dict):
        add("source_of_truth", source_of_truth.get("docs_text"), "docs_text")
        add("source_of_truth", source_of_truth.get("description"), "description")

    return docs


def _source_references(campaign: dict[str, Any]) -> list[dict[str, Any]]:
    values = campaign.get("source_urls") or campaign.get("asset_urls") or []
    refs = []
    for index, value in enumerate(values):
        if isinstance(value, dict):
            url = str(value.get("url") or "").strip()
            timestamp = str(value.get("fetched_at") or value.get("timestamp") or "").strip() or None
        else:
            url = str(value or "").strip()
            timestamp = None
        if url:
            refs.append({"source_id": f"source-url-{index + 1}", "url": url, "timestamp": timestamp})
    return refs


def source_fingerprint(campaign: dict[str, Any]) -> str:
    """Stable identity for the rule-bearing source text."""
    payload = [
        {
            "source_type": doc["source_type"],
            "location": doc["location"],
            "text": doc["text"],
        }
        for doc in source_documents(campaign)
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evidence_id(
    *,
    campaign_id: str,
    source_hash: str,
    source_type: str,
    location: str,
    quote: str,
) -> str:
    payload = {
        "campaign_id": str(campaign_id),
        "source_hash": str(source_hash),
        "source_type": str(source_type),
        "location": str(location),
        "quote": _norm_text(quote),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "evidence-v1:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_evidence_ledger(campaign: dict[str, Any]) -> dict[str, Any]:
    """Build the immutable source-side evidence ledger."""
    cid = str(campaign.get("id") or "")
    source_hash = source_fingerprint(campaign)
    documents = source_documents(campaign)
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": cid,
        "source_hash": source_hash,
        "source_references": _source_references(campaign),
        "documents": [
            {
                "source_type": doc["source_type"],
                "location": doc["location"],
                "text_hash": hashlib.sha256(doc["text"].encode("utf-8")).hexdigest(),
                "text_length": len(doc["text"]),
                "source_url": doc["source_url"],
                "source_timestamp": doc["source_timestamp"],
                "extraction_method": doc["extraction_method"],
                "source_priority": doc["source_priority"],
                "span": {"start": 0, "end": len(doc["text"])},
            }
            for doc in documents
        ],
    }


def verify_quote(
    campaign: dict[str, Any],
    quote: Any,
    *,
    source_hash: str | None = None,
) -> dict[str, Any]:
    """Verify an AI-provided quote against the current campaign sources."""
    normalized_quote = _norm_text(quote)
    ledger_hash = source_hash or source_fingerprint(campaign)
    if not normalized_quote:
        return {
            "status": "unverified",
            "reason": "empty_quote",
            "evidence_id": None,
        }

    for doc in source_documents(campaign):
        if normalized_quote.lower() in doc["text"].lower():
            return {
                "status": "verified",
                "source_type": doc["source_type"],
                "location": doc["location"],
                "quote": normalized_quote,
                "source_hash": ledger_hash,
                "source_url": doc["source_url"],
                "source_timestamp": doc["source_timestamp"],
                "extraction_method": doc["extraction_method"],
                "source_priority": doc["source_priority"],
                "span": {"start": doc["text"].lower().find(normalized_quote.lower()), "end": doc["text"].lower().find(normalized_quote.lower()) + len(normalized_quote)},
                "evidence_id": evidence_id(
                    campaign_id=str(campaign.get("id") or ""),
                    source_hash=ledger_hash,
                    source_type=doc["source_type"],
                    location=doc["location"],
                    quote=normalized_quote,
                ),
            }

    return {
        "status": "unverified",
        "reason": "quote_not_found_in_current_sources",
        "quote": normalized_quote,
        "source_hash": ledger_hash,
        "evidence_id": None,
    }


def _rule_path_values(rules: dict[str, Any] | None, rule_path: str) -> list[str]:
    """Return source-bearing atomic rule values for deterministic evidence recovery."""
    if not isinstance(rules, dict):
        return []
    leaf = str(rule_path or "").split(".")[-1]
    if not leaf or leaf not in rules:
        return []
    value = rules.get(leaf)
    values = value if isinstance(value, list) else [value]
    result = []
    for item in values:
        if not isinstance(item, str):
            continue
        normalized = _norm_text(item)
        if len(normalized) < 4:
            continue
        if normalized.lower() in {"unknown", "campaign_defined", "manual_required", "unresolved"}:
            continue
        result.append(normalized)
    if isinstance(value, str):
        normalized = _norm_text(value)
        if len(normalized) < 4 or normalized.lower() in {"unknown", "campaign_defined", "manual_required", "unresolved"}:
            return []
        return [normalized]
    return result


def verify_ai_evidence(
    campaign: dict[str, Any],
    evidence: list[Any],
    *,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify AI evidence and deterministically recover atomic source-backed rule values."""
    source_hash = source_fingerprint(campaign)
    verified: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add_verified(result: dict[str, Any]) -> None:
        evidence_key = result.get("evidence_id")
        if not evidence_key or evidence_key in seen_ids:
            return
        seen_ids.add(evidence_key)
        verified.append(result)

    for item in evidence:
        if not isinstance(item, dict):
            unverified.append({
                "status": "unverified",
                "reason": "malformed_evidence",
                "raw": item,
            })
            continue

        rule_path = str(item.get("rule_path") or "")
        result = verify_quote(campaign, item.get("quote"), source_hash=source_hash)
        result["rule_path"] = rule_path
        if result["status"] == "verified":
            add_verified(result)
            continue

        recovered = False
        for value in _rule_path_values(rules, rule_path):
            atomic = verify_quote(campaign, value, source_hash=source_hash)
            if atomic["status"] == "verified":
                atomic["rule_path"] = rule_path
                add_verified(atomic)
                recovered = True
        if not recovered:
            unverified.append(result)

    total = len(verified) + len(unverified)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_hash": source_hash,
        "verified": verified,
        "unverified": unverified,
        "coverage": (len(verified) / total) if total else 0.0,
    }


__all__ = [
    "SCHEMA_VERSION",
    "build_evidence_ledger",
    "evidence_id",
    "source_documents",
    "source_fingerprint",
    "verify_ai_evidence",
    "verify_quote",
]
