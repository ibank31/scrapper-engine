#!/usr/bin/env python3
"""Deterministic CA-05 Material Intelligence / Material Plan compiler.

CA-05 turns the CA-04 material contract into an executable material plan. It
never invents assets, treats URLs as acquired, resolves ambiguity, selects
clips, or calls an LLM.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

SCHEMA_VERSION = 1
ASSET_STATES = {"required", "discovered", "candidate", "verified", "acquired", "ready", "rejected", "missing", "unresolved", "blocked"}
ROLES = {"primary_source", "supporting_footage", "brand_identity", "proof", "reference", "background", "audio", "visual_reference", "campaign_document", "unknown"}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return _norm(value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return value


def _key(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_key(value).encode("utf-8")).hexdigest()


def _scope(item: Mapping[str, Any]) -> dict[str, list[str]]:
    raw = item.get("scope") if isinstance(item.get("scope"), Mapping) else {}
    return {
        dimension: sorted({_norm(value).lower() if dimension != "audiences" else _norm(value) for value in raw.get(dimension, []) or [] if _norm(value)})
        for dimension in ("platforms", "languages", "audiences")
    }


def _required(item: Mapping[str, Any]) -> bool | None:
    level = _norm(item.get("requirement_level") or ("mandatory" if item.get("required") is True else "optional" if item.get("required") is False else "unknown")).lower()
    return True if level == "mandatory" else False if level == "optional" else None


def _level(item: Mapping[str, Any]) -> str:
    required = _required(item)
    return "mandatory" if required is True else "optional" if required is False else "unknown"


def _interpretation(item: Mapping[str, Any]) -> str:
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    value = _norm(item.get("interpretation_type") or provenance.get("interpretation_type")).lower()
    return value if value in {"explicit", "inferred", "conflicting", "ambiguous", "unsupported", "manual_required"} else "manual_required"


def _provenance(item: Mapping[str, Any]) -> dict[str, Any]:
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    return {
        "production_contract_requirement_id": str(item.get("requirement_id") or item.get("material_requirement_id") or ""),
        "reconciliation_rule_id": str(provenance.get("reconciliation_rule_id") or provenance.get("rule_id") or ""),
        "rule_id": str(provenance.get("rule_id") or ""),
        "brain_rule_ids": sorted(str(value) for value in provenance.get("brain_rule_ids") or []),
        "evidence_ids": sorted(str(value) for value in provenance.get("evidence_ids") or []),
        "source_references": deepcopy(provenance.get("source_references") or []),
        "source_hash": str(provenance.get("source_hash") or ""),
        "requirement_level": _level(item),
        "interpretation_type": _interpretation(item),
        "resolution": deepcopy(provenance.get("resolution") or {}),
        "scope": _scope(item),
    }


def _values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _category(field: str, value: Any) -> str:
    text = _norm(value).lower()
    if "logo" in text or field in {"asset_roles", "brand_assets"} and "brand" in text:
        return "logo" if "logo" in text else "brand_assets"
    if "screenshot" in text:
        return "screenshots"
    if "audio" in text or "music" in text or "voice" in text:
        return "audio"
    if "document" in text or field in {"documents", "campaign_document"}:
        return "documents"
    if "reference" in text or field in {"visual_references", "reference_material"}:
        return "reference_material"
    if field in {"asset_sources", "required_assets", "preferred_assets", "fallback_assets"}:
        return "source_footage" if "footage" in text or "video" in text or "clip" in text else "campaign_material"
    return field or "material"


def _role(item: Mapping[str, Any], value: Any) -> str:
    field = _norm(item.get("field")).lower()
    if field not in {"asset_roles", "role", "material_role"}:
        return "unknown"
    role = _norm(value).lower().replace(" ", "_")
    return role if role in ROLES else "unknown"


def _requirement_items(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    material = contract.get("material") if isinstance(contract.get("material"), Mapping) else {}
    raw = material.get("asset_requirements") if isinstance(material.get("asset_requirements"), list) else []
    if not raw:
        raw = material.get("requirements") if isinstance(material.get("requirements"), list) else []
    items: list[dict[str, Any]] = []
    for raw_item in raw:
        if not isinstance(raw_item, Mapping):
            continue
        field = _norm(raw_item.get("field") or "material")
        values = _values(raw_item.get("value"))
        if not values:
            values = [None]
        for value in values:
            item = dict(raw_item)
            item["field"] = field
            item["value"] = value
            items.append(item)
    return items


def _requirement_id(contract: Mapping[str, Any], item: Mapping[str, Any], index: int) -> str:
    return _hash("material-requirement-v1:", {
        "campaign_id": contract.get("campaign_id"), "production_contract_id": contract.get("contract_id"),
        "field": item.get("field"), "value": item.get("value"), "scope": _scope(item),
        "provenance": _provenance(item), "index": index,
    })


def _production_requirement_id(contract: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    return _hash("production-requirement-v1:", {
        "production_contract_id": contract.get("contract_id"), "field": item.get("field"),
        "value": item.get("value"), "scope": _scope(item),
    })


def _candidate_requirement_id(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("material_requirement_id") or candidate.get("requirement_id") or "")


def _candidate_matches(candidate: Mapping[str, Any], requirement: Mapping[str, Any]) -> bool:
    explicit = _candidate_requirement_id(candidate)
    if explicit:
        return explicit == str(requirement.get("material_requirement_id"))
    wanted = _norm(requirement.get("value")).lower()
    haystack = " ".join(_norm(candidate.get(key)).lower() for key in ("source_url", "url", "name", "title", "intent", "reference_role"))
    return bool(wanted and wanted in haystack)


def _state(candidate: Mapping[str, Any]) -> str:
    value = _norm(candidate.get("status") or "discovered").lower()
    return value if value in ASSET_STATES else "discovered"


def _asset_fingerprint(campaign_id: str, candidate: Mapping[str, Any], role: str) -> str:
    supplied = _norm(candidate.get("fingerprint") or candidate.get("asset_fingerprint"))
    if supplied:
        return supplied
    content_hash = _norm(candidate.get("content_hash") or candidate.get("checksum") or candidate.get("sha256"))
    source_url = _norm(candidate.get("source_url") or candidate.get("url"))
    identity = content_hash or source_url or _key({key: candidate.get(key) for key in ("name", "title", "source_type")})
    return _hash("asset-fingerprint-v1:", {"campaign_id": campaign_id, "identity": identity, "role": role})


def _issue(issue_type: str, severity: str, requirement: Mapping[str, Any] | None, reason: str, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    rid = str((requirement or {}).get("material_requirement_id") or "")
    evidence = sorted(str(value) for value in (evidence_ids or (requirement or {}).get("provenance", {}).get("evidence_ids", []) or []))
    issue_id = _hash("material-issue-v1:", {"type": issue_type, "severity": severity, "requirement_id": rid, "reason": reason, "evidence_ids": evidence})
    return {"issue_id": issue_id, "type": issue_type, "severity": severity, "material_requirement_id": rid, "evidence_ids": evidence, "reason": reason, "resolution": "manual_required"}


def material_plan_is_current(plan: Mapping[str, Any] | None, production_contract: Mapping[str, Any] | None) -> bool:
    if not isinstance(plan, Mapping) or not isinstance(production_contract, Mapping):
        return False
    return all([
        plan.get("schema_version") == SCHEMA_VERSION,
        bool(plan.get("material_plan_id")),
        plan.get("campaign_id") == production_contract.get("campaign_id"),
        plan.get("source_hash") == production_contract.get("source_hash"),
        plan.get("brain_id") == production_contract.get("brain_id"),
        plan.get("reconciliation_id") == production_contract.get("reconciliation_id"),
        plan.get("production_contract_id") == production_contract.get("contract_id"),
        isinstance(plan.get("requirements"), list),
        isinstance(plan.get("assets"), list),
    ])


def compile_material_plan(production_contract: Mapping[str, Any], candidates: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Compile material requirements and optional discovered candidates read-only."""
    contract = production_contract if isinstance(production_contract, Mapping) else {}
    campaign_id = str(contract.get("campaign_id") or "")
    source_hash = str(contract.get("source_hash") or "")
    brain_id = str(contract.get("brain_id") or "")
    reconciliation_id = str(contract.get("reconciliation_id") or "")
    production_contract_id = str(contract.get("contract_id") or "")
    integrity_errors: list[str] = []
    if contract.get("schema_version") != 1:
        integrity_errors.append("invalid_production_contract_schema")
    if not all((campaign_id, source_hash, brain_id, reconciliation_id, production_contract_id)):
        integrity_errors.append("missing_production_contract_identity")

    requirements: list[dict[str, Any]] = []
    for index, raw in enumerate(_requirement_items(contract), 1):
        provenance = _provenance(raw)
        provenance["source_hash"] = source_hash
        requirement_id = _requirement_id(contract, raw, index)
        requirement = {
            "material_requirement_id": requirement_id,
            "production_contract_requirement_id": _production_requirement_id(contract, raw),
            "field": _norm(raw.get("field") or "material"),
            "category": _category(_norm(raw.get("field") or "material"), raw.get("value")),
            "role": _role(raw, raw.get("value")),
            "value": _canonical(raw.get("value")),
            "required": _required(raw),
            "requirement_level": _level(raw),
            "interpretation_type": _interpretation(raw),
            "scope": _scope(raw),
            "constraints": deepcopy(raw.get("constraint") or raw.get("constraints") or {}),
            "provenance": provenance,
            "resolution_status": "unresolved",
            "fallback_policy": "explicit_only",
        }
        requirements.append(requirement)

    candidates = [item for item in (candidates or []) if isinstance(item, Mapping)]
    assets: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    seen_fingerprints: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        matches = [requirement for requirement in requirements if _candidate_matches(candidate, requirement)]
        if not matches:
            issues.append(_issue("unbound_candidate", "warning", None, "Candidate was not bound to an explicit material requirement."))
            continue
        for requirement in matches:
            role = _role(requirement, requirement.get("value"))
            fingerprint = _asset_fingerprint(campaign_id, candidate, role)
            if fingerprint in seen_fingerprints:
                existing = seen_fingerprints[fingerprint]
                existing["material_requirement_ids"] = sorted(set(existing["material_requirement_ids"] + [requirement["material_requirement_id"]]))
                continue
            asset = {
                "asset_id": _hash("asset-v1:", {"fingerprint": fingerprint}),
                "material_requirement_ids": [requirement["material_requirement_id"]],
                "fingerprint": fingerprint,
                "status": _state(candidate),
                "source_url": _norm(candidate.get("source_url") or candidate.get("url")) or None,
                "source_type": _norm(candidate.get("source_type")) or None,
                "role": role,
                "scope": _scope(candidate) if isinstance(candidate.get("scope"), Mapping) else requirement["scope"],
                "content_hash": _norm(candidate.get("content_hash") or candidate.get("checksum") or candidate.get("sha256")) or None,
                "provenance": deepcopy(candidate.get("provenance") or {"material_requirement_id": requirement["material_requirement_id"], "evidence_ids": requirement["provenance"]["evidence_ids"], "source_references": requirement["provenance"]["source_references"]}),
            }
            assets.append(asset)
            seen_fingerprints[fingerprint] = asset

    by_requirement = {requirement["material_requirement_id"]: [] for requirement in requirements}
    for asset in assets:
        for requirement_id in asset["material_requirement_ids"]:
            by_requirement.setdefault(requirement_id, []).append(asset)

    acquisition_plan: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    material = contract.get("material") if isinstance(contract.get("material"), Mapping) else {}
    explicit_fallbacks = material.get("fallback_assets") if isinstance(material.get("fallback_assets"), list) else []
    for requirement in requirements:
        available = by_requirement.get(requirement["material_requirement_id"], [])
        ready_states = {"verified", "acquired", "ready"}
        if any(asset["status"] in ready_states for asset in available):
            requirement["resolution_status"] = "resolved"
        elif available:
            requirement["resolution_status"] = "candidate"
        elif requirement["required"] is True:
            requirement["resolution_status"] = "missing"
            issues.append(_issue("missing_mandatory_material", "critical", requirement, "Mandatory material has no discovered candidate."))
        elif requirement["required"] is None:
            requirement["resolution_status"] = "unresolved"
            issues.append(_issue("unknown_material_requirement", "warning", requirement, "Material requirement semantics remain unknown; it was not promoted to mandatory."))
        else:
            requirement["resolution_status"] = "unresolved"
        strategy = "manual_upload"
        value = _norm(requirement.get("value"))
        if value.startswith("http://") or value.startswith("https://"):
            strategy = "official_url"
        elif requirement["field"] in {"asset_sources", "required_assets", "preferred_assets"}:
            strategy = "campaign_source"
        acquisition_plan.append({
            "material_requirement_id": requirement["material_requirement_id"], "strategy": strategy,
            "priority": 1 if requirement["required"] is True else 2,
            "required": requirement["required"], "verification": "source_and_content_verification_required",
            "fallback_policy": "explicit_only", "scope": requirement["scope"],
        })
        resolved_lineage = str(requirement["provenance"].get("resolution", {}).get("status") or "").lower() == "resolved"
        if requirement["required"] is True and requirement["interpretation_type"] in {"conflicting", "ambiguous", "unsupported", "manual_required"} and not resolved_lineage:
            issues.append(_issue("mandatory_material_ambiguity", "critical", requirement, "Mandatory material requirement cannot be safely executed without manual resolution."))
        elif requirement["interpretation_type"] in {"conflicting", "ambiguous", "unsupported", "manual_required"} and not resolved_lineage:
            issues.append(_issue("material_ambiguity", "warning", requirement, "Material requirement interpretation remains explicit and requires review."))

    for value in explicit_fallbacks:
        fallbacks.append({"value": _canonical(value), "relationship": "fallback", "authorized": True, "policy": "campaign_explicit", "scope": {"platforms": [], "languages": [], "audiences": []}})

    for error in integrity_errors:
        issues.append(_issue("integrity_failure", "critical", None, error))
    issues = sorted({item["issue_id"]: item for item in issues}.values(), key=lambda item: item["issue_id"])
    if integrity_errors or any(item["severity"] == "critical" for item in issues):
        status = "blocked"
    elif issues or any(item["resolution_status"] in {"candidate", "unresolved"} for item in requirements):
        status = "review"
    else:
        status = "ready"

    summary = {
        "requirement_count": len(requirements),
        "mandatory_requirements": sum(item["required"] is True for item in requirements),
        "optional_requirements": sum(item["required"] is False for item in requirements),
        "unknown_requirements": sum(item["required"] is None for item in requirements),
        "resolved_requirements": sum(item["resolution_status"] == "resolved" for item in requirements),
        "missing_requirements": sum(item["resolution_status"] == "missing" for item in requirements),
        "asset_count": len(assets),
        "duplicate_assets": len(candidates) - len(assets) if len(candidates) >= len(assets) else 0,
        "issue_count": len(issues),
    }
    plan = {
        "schema_version": SCHEMA_VERSION, "material_plan_id": "", "campaign_id": campaign_id,
        "source_hash": source_hash, "brain_id": brain_id, "reconciliation_id": reconciliation_id,
        "production_contract_id": production_contract_id, "status": status,
        "requirements": sorted(requirements, key=lambda item: item["material_requirement_id"]),
        "assets": sorted(assets, key=lambda item: item["asset_id"]),
        "acquisition_plan": sorted(acquisition_plan, key=lambda item: item["material_requirement_id"]),
        "fallbacks": sorted(fallbacks, key=_key), "constraints": sorted([item for item in requirements if item["constraints"]], key=lambda item: item["material_requirement_id"]),
        "issues": issues, "summary": summary,
    }
    plan["material_plan_id"] = _hash("material-plan-v1:", plan)
    return plan


__all__ = ["SCHEMA_VERSION", "ASSET_STATES", "compile_material_plan", "material_plan_is_current"]
