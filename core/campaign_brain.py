#!/usr/bin/env python3
"""Canonical Campaign Brain for CA-01.

The Campaign Brain is authoritative campaign intelligence. The legacy
ai_rules.rules object remains a compatibility projection until later
milestones migrate downstream consumers.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from core.campaign_evidence import source_fingerprint

SCHEMA_VERSION = 1
BRAIN_ID_PREFIX = "brain-v1:"
UNKNOWN = {"", "unknown", "campaign_defined", "manual_required", "unresolved", "not_mentioned"}
PLATFORMS = {"instagram", "tiktok", "youtube", "facebook", "x", "twitter", "linkedin", "threads"}
LANGUAGES = {
    "english": "en", "inggris": "en", "indonesian": "id",
    "bahasa indonesia": "id", "indonesia": "id", "spanish": "es",
    "español": "es", "portuguese": "pt", "português": "pt",
    "french": "fr", "german": "de", "japanese": "ja", "korean": "ko",
}
DOMAINS = {
    "source_policy": "content", "platforms": "platform", "aspect_ratio": "production",
    "min_duration_seconds": "production", "max_duration_seconds": "production",
    "subtitle_required": "production", "subtitle_style": "production",
    "watermark_required": "production", "third_party_watermark_allowed": "production",
    "official_audio_required": "production", "cta_required": "posting", "cta_text": "posting",
    "handles": "posting", "hashtags": "posting", "disclosures": "safety",
    "topic_terms": "content", "allowed_content": "content", "prohibited_content": "safety",
    "asset_sources": "material", "posting_rules": "posting", "account_rules": "posting",
    "audience_tiers": "audience", "platform_rules": "platform",
    "subtitle_delivery_profile": "production", "sound_policy": "posting",
    "native_tags": "posting", "material_policy": "material",
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return _norm(value).lower() not in UNKNOWN
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _leaf(path: str) -> str:
    return _norm(path).split(".")[-1].lower()


def _domain(path: str) -> str:
    root = _norm(path).lower().split(".")[0]
    if root in {"production", "material", "posting", "safety", "commercial", "geography", "platform", "audience", "content"}:
        return root
    return DOMAINS.get(_leaf(path), "content")


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return _norm(value)
    if isinstance(value, list):
        return [_canonical(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    return value


def _value_key(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _iter_rules(value: Any, path: str = "rules") -> Iterable[tuple[str, Any]]:
    if not isinstance(value, dict):
        return
    for key in sorted(value):
        child_path = f"{path}.{key}"
        child = value[key]
        if isinstance(child, dict):
            yield from _iter_rules(child, child_path)
        elif isinstance(child, list):
            for index, item in enumerate(child):
                if isinstance(item, dict):
                    yield from _iter_rules(item, f"{child_path}[{index}]")
                elif _meaningful(item):
                    yield child_path, item
        elif _meaningful(child):
            yield child_path, child


def _annotation_path(item: dict[str, Any]) -> str:
    return _norm(item.get("rule_path") or item.get("path") or "")


def _annotation_value(item: dict[str, Any]) -> Any:
    return item.get("value") if "value" in item else item.get("rule_value")


def _path_match(left: str, right: str) -> bool:
    a = _norm(left).lower().removeprefix("rules.")
    b = _norm(right).lower().removeprefix("rules.")
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a) or _leaf(a) == _leaf(b)


def _scope(path: str, annotation: dict[str, Any] | None, quotes: list[str]) -> dict[str, list[str]]:
    raw = annotation.get("scope") if isinstance(annotation, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    platforms = [str(x).strip().lower() for x in raw.get("platforms", []) or [] if str(x).strip()]
    languages = [str(x).strip().lower() for x in raw.get("languages", []) or [] if str(x).strip()]
    audiences = [str(x).strip() for x in raw.get("audiences", []) or [] if str(x).strip()]
    for segment in re.split(r"[.:/\[\]]", path.lower()):
        if segment in PLATFORMS:
            platforms.append(segment)
        if segment in LANGUAGES:
            languages.append(LANGUAGES[segment])
    text = " ".join(quotes).lower()
    for label, code in LANGUAGES.items():
        if re.search(rf"\b{re.escape(label)}\b", text):
            languages.append(code)
    if not languages and re.search(r"\b(gunakan|durasi|detik|wajib|bahasa)\b", text):
        languages.append("id")
    return {
        "platforms": list(dict.fromkeys(platforms)),
        "languages": list(dict.fromkeys(languages)),
        "audiences": list(dict.fromkeys(audiences)),
    }


def _verified_matches(path: str, value: Any, verified: list[dict[str, Any]]) -> list[dict[str, Any]]:
    value_text = _norm(value).lower()
    matches = []
    for item in verified:
        evidence_path = str(item.get("rule_path") or "")
        quote = _norm(item.get("quote"))
        if not _path_match(path, evidence_path):
            continue
        if isinstance(value, bool) or (value_text and (value_text in quote.lower() or quote.lower() in value_text)):
            matches.append(item)
    return matches


def _requirement_level(campaign: dict[str, Any], evidence: list[dict[str, Any]], annotation: dict[str, Any] | None) -> tuple[str, str]:
    requirements = campaign.get("requirements") or []
    for ev in evidence:
        quote = _norm(ev.get("quote")).lower()
        for req in requirements:
            req_text = _norm(req.get("text") if isinstance(req, dict) else req).lower()
            if req_text and (req_text in quote or quote in req_text):
                if not isinstance(req, dict) or bool(req.get("isMandatory", True)):
                    return "mandatory", "campaign_requirement"
                return "optional", "campaign_optional_requirement"
    asserted = _norm((annotation or {}).get("requirement_level")).lower()
    if asserted in {"mandatory", "required", "true"} and evidence:
        return "mandatory", "model_annotation"
    if asserted in {"optional", "false"} and evidence:
        return "optional", "model_annotation"
    return "unknown", "unresolved"


def _interpretation(annotation: dict[str, Any] | None, evidence: list[dict[str, Any]], ai_available: bool) -> str:
    asserted = _norm((annotation or {}).get("interpretation_type")).lower()
    if asserted in {"explicit", "inferred", "conflicting", "ambiguous", "unsupported", "manual_required"}:
        return asserted
    return "explicit" if evidence else ("unsupported" if ai_available else "manual_required")


def _hash_id(prefix: str, payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + "-v1:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_rule(campaign: dict[str, Any], source_hash: str, path: str, value: Any, annotation: dict[str, Any] | None, verified: list[dict[str, Any]], ai_available: bool) -> dict[str, Any] | None:
    if not _meaningful(value):
        return None
    evidence = _verified_matches(path, value, verified)
    interpretation = _interpretation(annotation, evidence, ai_available)
    requirement_level, requirement_basis = _requirement_level(campaign, evidence, annotation)
    if interpretation == "explicit" and not evidence:
        interpretation = "unsupported"
        requirement_level, requirement_basis = "unknown", "unverified"
    status = "supported" if evidence and interpretation not in {"unsupported", "ambiguous", "conflicting", "manual_required"} else interpretation
    scope = _scope(path, annotation, [_norm(x.get("quote")) for x in evidence])
    try:
        priority = int((annotation or {}).get("priority"))
    except (TypeError, ValueError):
        priority = max((int(x.get("source_priority") or 0) for x in evidence), default=0)
    return {
        "rule_id": _hash_id("rule", {
            "campaign_id": str(campaign.get("id") or ""),
            "source_hash": source_hash,
            "path": _norm(path),
            "value": _canonical(value),
            "scope": scope,
        }),
        "domain": _domain(path),
        "key": _leaf(path),
        "source_rule_path": _norm(path),
        "scope": scope,
        "priority": priority,
        "requirement_level": requirement_level,
        "requirement_basis": requirement_basis,
        "value": _canonical(value),
        "value_type": "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "string",
        "interpretation_type": interpretation,
        "status": status,
        "evidence_ids": sorted({str(x.get("evidence_id")) for x in evidence if x.get("evidence_id")}),
        "source_references": sorted([
            {"source_type": str(x.get("source_type") or ""), "location": str(x.get("location") or ""), "source_url": x.get("source_url")}
            for x in evidence
        ], key=lambda x: (x["source_type"], x["location"], str(x["source_url"] or ""))),
    }


def _detect_variants(verified: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in verified:
        path = _norm(item.get("rule_path"))
        quote = _norm(item.get("quote"))
        if path and quote:
            grouped.setdefault(path, []).append(item)
    conflicts, variants = [], []
    for path, items in grouped.items():
        quotes = list(dict.fromkeys(_norm(x.get("quote")) for x in items))
        if len(quotes) < 2:
            continue
        evidence_ids = sorted({str(x.get("evidence_id")) for x in items if x.get("evidence_id")})
        payload = {"rule_path": path, "evidence_ids": evidence_ids}
        if re.search(r"\b(legacy|current|old|new|previous|deprecated|superseded)\b", " ".join(quotes).lower()):
            conflicts.append({
                "conflict_id": _hash_id("conflict", payload),
                "rule_path": path,
                "status": "unresolved",
                "evidence_ids": evidence_ids,
                "quotes": quotes,
                "reason": "source conflict preserved; resolution belongs to CA-03",
            })
        else:
            variants.append({
                "variant_id": _hash_id("variant", payload),
                "rule_path": path,
                "status": "preserved",
                "evidence_ids": evidence_ids,
                "quotes": quotes,
            })
    return conflicts, variants


def build_campaign_brain(
    campaign: dict[str, Any],
    *,
    rules: dict[str, Any] | None,
    rule_annotations: list[Any] | None,
    evidence_contract: dict[str, Any] | None,
    ambiguities: list[Any] | None,
    confidence: float | None,
    campaign_fit: dict[str, Any] | None,
    ai_available: bool = True,
) -> dict[str, Any]:
    campaign_id = str(campaign.get("id") or "")
    source_hash = source_fingerprint(campaign)
    verified = [x for x in ((evidence_contract or {}).get("verified") or []) if isinstance(x, dict)]
    annotations = [x for x in (rule_annotations or []) if isinstance(x, dict) and _annotation_path(x)]
    records: dict[tuple[str, str], dict[str, Any]] = {}

    for path, value in _iter_rules(rules if isinstance(rules, dict) else {}):
        # An unavailable/omitted boolean is not a source fact merely because
        # the compatibility projection defaults it to false.
        if value is False and not _verified_matches(path, value, verified):
            continue
        annotation = next((x for x in annotations if _path_match(path, _annotation_path(x))), None)
        record = _build_rule(campaign, source_hash, path, value, annotation, verified, ai_available)
        if record:
            records[(record["source_rule_path"], _value_key(record["value"]))] = record

    for annotation in annotations:
        value = _annotation_value(annotation)
        if not _meaningful(value):
            continue
        path = _annotation_path(annotation)
        record = _build_rule(campaign, source_hash, path, value, annotation, verified, ai_available)
        if record:
            records[(record["source_rule_path"], _value_key(record["value"]))] = record

    rules_out = sorted(
        records.values(),
        key=lambda x: (x["domain"], x["source_rule_path"], _value_key(x["value"]), tuple(x["scope"]["platforms"]), tuple(x["scope"]["languages"])),
    )
    conflicts, variants = _detect_variants(verified)
    brain = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "source_hash": source_hash,
        "identity": {"campaign_id": campaign_id, "title": campaign.get("title"), "brand": campaign.get("brand"), "type": campaign.get("type")},
        "objective": {
            "declared": campaign.get("objective"),
            "campaign_fit": {
                "score": (campaign_fit or {}).get("score"),
                "label": (campaign_fit or {}).get("label") or "unknown",
                "reason": (campaign_fit or {}).get("reason") or "",
            },
        },
        "reward": {"payouts": campaign.get("payouts") or [], "status": "explicit" if campaign.get("payouts") else "unknown"},
        "platforms": list(dict.fromkeys(_norm(x).lower() for x in campaign.get("platforms") or [] if _norm(x))),
        "rules": rules_out,
        "variants": variants,
        "conflicts": conflicts,
        "ambiguities": [str(x) for x in ambiguities or []],
        "evidence": {
            "schema_version": int((evidence_contract or {}).get("schema_version") or 1),
            "source_hash": source_hash,
            "verified": sorted(verified, key=lambda x: (str(x.get("rule_path") or ""), str(x.get("evidence_id") or ""))),
            "unverified": list((evidence_contract or {}).get("unverified") or []),
            "coverage": float((evidence_contract or {}).get("coverage") or 0.0),
        },
        "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
        "compatibility": {
            "legacy_rules_schema_version": 2,
            "projection": "ai_rules.rules remains a compatibility projection; campaign_brain is authoritative for CA-01+ intelligence.",
        },
    }
    stable = {k: v for k, v in brain.items() if k not in {"brain_id", "confidence"}}
    brain["brain_id"] = _hash_id(BRAIN_ID_PREFIX[:-1], stable)
    return brain


def evaluate_rule_preservation(campaign: dict[str, Any], brain: dict[str, Any]) -> dict[str, Any]:
    """Golden-fixture gate. Production rows without a manifest are not_evaluable."""
    expected = [x for x in campaign.get("expected_evidence") or [] if isinstance(x, dict) and _norm(x.get("quote"))]
    if not expected:
        return {"status": "not_evaluable", "reason": "campaign has no deterministic expected_evidence manifest"}
    brain_rules = [x for x in brain.get("rules") or [] if isinstance(x, dict)]
    verified = [x for x in (brain.get("evidence") or {}).get("verified") or [] if isinstance(x, dict)]
    verified_keys = {(_norm(x.get("rule_path")).lower(), _norm(x.get("quote")).lower()) for x in verified}
    missing = [x for x in expected if (_norm(x.get("rule_path")).lower(), _norm(x.get("quote")).lower()) not in verified_keys]
    mandatory = [x for x in expected if bool(x.get("mandatory"))]
    mandatory_missing = [x for x in mandatory if (_norm(x.get("rule_path")).lower(), _norm(x.get("quote")).lower()) not in verified_keys]

    platform_missing = []
    for item in expected:
        path = _norm(item.get("rule_path")).lower()
        match = re.search(r"\b(" + "|".join(sorted(map(re.escape, PLATFORMS))) + r")\b", path)
        if not match:
            continue
        platform = match.group(1)
        quote = _norm(item.get("quote")).lower()
        if not any(
            _path_match(rule.get("source_rule_path"), path)
            and platform in (rule.get("scope") or {}).get("platforms", [])
            and quote in {
                _norm(ev.get("quote")).lower()
                for ev in verified
                if ev.get("evidence_id") in (rule.get("evidence_ids") or [])
            }
            for rule in brain_rules
        ):
            platform_missing.append(item)

    supported_without_evidence = [x for x in brain_rules if x.get("status") == "supported" and not x.get("evidence_ids")]
    mandatory_without_evidence = [x for x in brain_rules if x.get("requirement_level") == "mandatory" and not x.get("evidence_ids")]
    mandatory_paths = {_norm(x.get("rule_path")).lower() for x in mandatory}
    false_mandatory = [
        x for x in brain_rules
        if x.get("requirement_level") == "mandatory"
        and _norm(x.get("source_rule_path")).lower() not in mandatory_paths
        and not any(
            ev.get("evidence_id") in (x.get("evidence_ids") or [])
            and any(_norm(m.get("quote")).lower() == _norm(ev.get("quote")).lower() and bool(m.get("mandatory")) for m in expected)
            for ev in verified
        )
    ]
    failed = bool(missing or platform_missing or supported_without_evidence or mandatory_without_evidence or false_mandatory)
    return {
        "status": "fail" if failed else "pass",
        "expected_count": len(expected),
        "preserved_count": len(expected) - len(missing),
        "mandatory_expected": len(mandatory),
        "mandatory_preserved": len(mandatory) - len(mandatory_missing),
        "missing": missing,
        "mandatory_missing": mandatory_missing,
        "platform_missing": platform_missing,
        "supported_without_evidence": supported_without_evidence,
        "mandatory_without_evidence": mandatory_without_evidence,
        "false_mandatory": false_mandatory,
        "silent_rule_loss": len(missing),
        "critical_rule_preservation": (len(mandatory) - len(mandatory_missing)) / len(mandatory) if mandatory else 1.0,
        "mandatory_rule_preservation": (len(mandatory) - len(mandatory_missing)) / len(mandatory) if mandatory else 1.0,
    }


__all__ = ["SCHEMA_VERSION", "build_campaign_brain", "evaluate_rule_preservation"]
