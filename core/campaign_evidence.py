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

SCHEMA_VERSION = 1


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_documents(campaign: dict[str, Any]) -> list[dict[str, str]]:
    """Return deterministic source documents from the campaign payload."""
    docs: list[dict[str, str]] = []

    def add(source_type: str, text: Any, location: str = "") -> None:
        normalized = _norm_text(text)
        if normalized:
            docs.append({
                "source_type": source_type,
                "location": location,
                "text": normalized,
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
        "documents": [
            {
                "source_type": doc["source_type"],
                "location": doc["location"],
                "text_hash": hashlib.sha256(doc["text"].encode("utf-8")).hexdigest(),
                "text_length": len(doc["text"]),
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


def verify_ai_evidence(
    campaign: dict[str, Any],
    evidence: list[Any],
) -> dict[str, Any]:
    """Verify all AI evidence and report coverage without changing the rules."""
    source_hash = source_fingerprint(campaign)
    verified: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []

    for item in evidence:
        if not isinstance(item, dict):
            unverified.append({
                "status": "unverified",
                "reason": "malformed_evidence",
                "raw": item,
            })
            continue
        result = verify_quote(campaign, item.get("quote"), source_hash=source_hash)
        result["rule_path"] = str(item.get("rule_path") or "")
        if result["status"] == "verified":
            verified.append(result)
        else:
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
