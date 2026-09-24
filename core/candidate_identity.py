"""Deterministic candidate identity, audience tiers, and source evidence helpers."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


CANDIDATE_ID_VERSION = "candidate-v1"
TIER_CLASSIFIER_VERSION = "audience-v1"


def canonical_hash(value: Any) -> str:
    """Hash JSON-stable data so equivalent payloads receive the same identity."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_source_asset_id(source: str | None) -> str:
    """Normalize URLs and local paths without treating query noise as a new asset."""
    raw = str(source or "").strip()
    if not raw:
        return "unknown-source"
    if "://" in raw:
        parts = urlsplit(raw)
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if not key.lower().startswith(("utm_", "fbclid", "gclid"))]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))
    return str(Path(raw).as_posix()).lower()


def transcript_hash(transcript: dict[str, Any]) -> str:
    """Hash the full transcript, preserving word timing and speaker evidence."""
    return canonical_hash(transcript)


def _terms(profile: Any) -> list[str]:
    if isinstance(profile, dict):
        values = profile.get("terms") or profile.get("keywords") or profile.get("topics") or []
    elif isinstance(profile, list):
        values = profile
    else:
        values = []
    return [str(value).strip().lower() for value in values if str(value).strip()]


def classify_candidate_tier(candidate: dict[str, Any], plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify by explicit audience rules only; never use campaign metadata flags."""
    production = (plan or {}).get("production") or {}
    profiles = production.get("audience_tiers") or {}
    text = " ".join(str(candidate.get("text") or "").lower().split())
    if not isinstance(profiles, dict) or not profiles.get("tier_1") or not profiles.get("tier_2"):
        return {"tier": "unknown", "classifier_version": TIER_CLASSIFIER_VERSION, "reason": "audience_rules_not_structured", "matches": {}}

    matches = {
        tier: [term for term in _terms(profiles.get(tier)) if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)]
        for tier in ("tier_1", "tier_2")
    }
    scores = {tier: len(values) for tier, values in matches.items()}
    if scores["tier_1"] == scores["tier_2"] or max(scores.values()) == 0:
        return {"tier": "unknown", "classifier_version": TIER_CLASSIFIER_VERSION, "reason": "audience_match_ambiguous" if max(scores.values()) else "audience_match_missing", "matches": matches}
    tier = "tier_1" if scores["tier_1"] > scores["tier_2"] else "tier_2"
    return {"tier": tier, "classifier_version": TIER_CLASSIFIER_VERSION, "reason": "explicit_audience_terms_matched", "matches": matches}


def build_candidate_identity(
    candidate: dict[str, Any],
    source_asset_id: str | None,
    source_hash: str | None,
    transcript_digest: str,
    rules_hash: str | None = None,
) -> dict[str, Any]:
    """Return stable identity fields without changing selection or ranking."""
    normalized_source = normalize_source_asset_id(source_asset_id)
    start = round(float(candidate.get("start") or 0), 3)
    end = round(float(candidate.get("end") or 0), 3)
    identity_payload = {
        "version": CANDIDATE_ID_VERSION,
        "source_asset_id": normalized_source,
        "source_hash": source_hash or "unknown-source-hash",
        "transcript_hash": transcript_digest,
        "start": start,
        "end": end,
    }
    return {
        "candidate_id": f"{CANDIDATE_ID_VERSION}:{canonical_hash(identity_payload)[:32]}",
        "source_asset_id": normalized_source,
        "source_hash": source_hash,
        "transcript_hash": transcript_digest,
        "start": start,
        "end": end,
        "rules_hash": rules_hash,
        "identity_version": CANDIDATE_ID_VERSION,
    }


def annotate_candidate(
    candidate: dict[str, Any],
    source_asset_id: str | None,
    source_hash: str | None,
    transcript: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach identity and audience classification while preserving the candidate payload."""
    annotated = dict(candidate)
    identity = build_candidate_identity(candidate, source_asset_id, source_hash, transcript_hash(transcript), (plan or {}).get("rules_hash"))
    classification = classify_candidate_tier(candidate, plan)
    annotated.update(identity)
    annotated["tier"] = classification["tier"]
    annotated["tier_evidence"] = classification
    annotated["selection_rationale"] = list(candidate.get("reasons") or [])
    return annotated


def deduplicate_source_records(records: list[dict[str, Any]], max_sources: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deduplicate preflight records before applying the source limit.

    Returns selected records and the complete evidence list, including duplicates
    and sources excluded only because the configured source limit was reached.
    """
    unique: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for record in records:
        item = dict(record)
        quality = item.get("quality") or {}
        source_hash = quality.get("duplicate_hash") or item.get("source_hash")
        item["source_asset_id"] = normalize_source_asset_id(item.get("source") or item.get("url"))
        if source_hash and source_hash in seen:
            item["duplicate_of"] = seen[source_hash]
            item["excluded_before_source_limit"] = True
        elif source_hash:
            seen[source_hash] = str(item.get("source") or item.get("url") or item["source_asset_id"])
            unique.append(item)
        else:
            unique.append(item)
        evidence.append(item)

    selected: list[dict[str, Any]] = []
    for item in unique:
        if item.get("duplicate_of"):
            continue
        if len(selected) >= max(1, int(max_sources)):
            item["excluded_before_transcription"] = True
            item["exclusion_reason"] = "source_limit"
            continue
        selected.append(item)
    return selected, evidence


__all__ = [
    "CANDIDATE_ID_VERSION",
    "TIER_CLASSIFIER_VERSION",
    "annotate_candidate",
    "build_candidate_identity",
    "canonical_hash",
    "classify_candidate_tier",
    "deduplicate_source_records",
    "normalize_source_asset_id",
    "transcript_hash",
]
