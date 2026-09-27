#!/usr/bin/env python3
"""Deterministic CA-06 campaign-aware clip strategy compiler.

This module plans clip segments from the CA-04 production contract and CA-05
material plan. It does not render, download, publish, call an LLM, or invent
timestamps. Missing or ambiguous information remains explicit in the result.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

SCHEMA_VERSION = 1
_READY_ASSET_STATES = {"verified", "acquired", "ready"}
_ROLES = {"hook", "context", "proof", "value", "cta", "transition", "background", "unknown"}
_ROLE_ORDER = {"hook": 10, "context": 20, "proof": 30, "value": 40, "transition": 50, "background": 60, "cta": 70, "unknown": 80}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return _norm(value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    return value


def _key(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_key(value).encode("utf-8")).hexdigest()


def _scope(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, Mapping) else {}
    return {d: sorted({_norm(x).lower() if d != "audiences" else _norm(x) for x in raw.get(d, []) or [] if _norm(x)}) for d in ("platforms", "languages", "audiences")}


def _provenance(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return {
        "material_requirement_id": str(raw.get("material_requirement_id") or ""),
        "production_contract_requirement_id": str(raw.get("production_contract_requirement_id") or ""),
        "reconciliation_rule_id": str(raw.get("reconciliation_rule_id") or raw.get("rule_id") or ""),
        "rule_id": str(raw.get("rule_id") or ""),
        "brain_rule_ids": sorted(str(x) for x in raw.get("brain_rule_ids") or []),
        "evidence_ids": sorted(str(x) for x in raw.get("evidence_ids") or []),
        "source_references": deepcopy(raw.get("source_references") or []),
        "source_hash": str(raw.get("source_hash") or ""),
    }


def _requirements(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    clip = contract.get("clip") if isinstance(contract.get("clip"), Mapping) else {}
    raw = clip.get("requirements") if isinstance(clip.get("requirements"), list) else []
    return [dict(x) for x in raw if isinstance(x, Mapping)]


def _platforms(contract: Mapping[str, Any], material: Mapping[str, Any], hints: list[Any] | None = None) -> list[str]:
    values: set[str] = set()
    for item in _requirements(contract):
        values.update(_scope(item.get("scope")).get("platforms", []))
    for item in material.get("requirements", []) if isinstance(material.get("requirements"), list) else []:
        if isinstance(item, Mapping):
            values.update(_scope(item.get("scope")).get("platforms", []))
    values.update(_scope(material.get("scope")).get("platforms", []))
    if not values:
        posting = contract.get("posting") if isinstance(contract.get("posting"), Mapping) else {}
        raw = posting.get("platforms")
        if isinstance(raw, list):
            values.update(_norm(x).lower() for x in raw if _norm(x))
    values.update(_norm(x).lower() for x in (hints or []) if _norm(x))
    return sorted(values)


def _duration(contract: Mapping[str, Any]) -> dict[str, int | None]:
    minimum = maximum = target = None
    for item in _requirements(contract):
        if item.get("field") not in {"duration", "duration_seconds"}:
            continue
        constraint = item.get("constraint") if isinstance(item.get("constraint"), Mapping) else {}
        if constraint.get("min") is not None:
            minimum = int(constraint["min"])
        if constraint.get("max") is not None:
            maximum = int(constraint["max"])
        if constraint.get("exact") is not None:
            minimum = maximum = int(constraint["exact"])
    if minimum is not None and maximum is not None and minimum > maximum:
        return {"min_seconds": minimum, "max_seconds": maximum, "target_seconds": None}
    return {"min_seconds": minimum, "max_seconds": maximum, "target_seconds": target}


def _role(requirement: Mapping[str, Any], asset: Mapping[str, Any] | None = None) -> str:
    for value in ((asset or {}).get("role"), requirement.get("role"), requirement.get("field")):
        text = _norm(value).lower().replace(" ", "_")
        if text in _ROLES:
            return text
        if text in {"asset_sources", "required_assets", "primary_source", "source_footage"}:
            return "context"
        if "proof" in text or "testimonial" in text:
            return "proof"
    return "unknown"


def _segment_id(requirement_id: str, asset_id: str, role: str, platform: str) -> str:
    return _hash("clip-segment-v1:", {"requirement_id": requirement_id, "asset_id": asset_id, "role": role, "platform": platform})


def _issue(kind: str, severity: str, reason: str, requirement_id: str = "", evidence_ids: list[str] | None = None) -> dict[str, Any]:
    item = {"type": kind, "severity": severity, "reason": reason, "material_requirement_id": requirement_id, "evidence_ids": sorted(str(x) for x in (evidence_ids or [])), "resolution": "manual_required"}
    return {"issue_id": _hash("clip-strategy-issue-v1:", item), **item}


def clip_strategy_is_current(strategy: Mapping[str, Any] | None, production_contract: Mapping[str, Any] | None, material_plan: Mapping[str, Any] | None) -> bool:
    if not isinstance(strategy, Mapping) or not isinstance(production_contract, Mapping) or not isinstance(material_plan, Mapping):
        return False
    return all([
        strategy.get("schema_version") == SCHEMA_VERSION,
        bool(strategy.get("clip_strategy_id")),
        strategy.get("campaign_id") == production_contract.get("campaign_id") == material_plan.get("campaign_id"),
        strategy.get("source_hash") == production_contract.get("source_hash") == material_plan.get("source_hash"),
        strategy.get("brain_id") == production_contract.get("brain_id") == material_plan.get("brain_id"),
        strategy.get("reconciliation_id") == production_contract.get("reconciliation_id") == material_plan.get("reconciliation_id"),
        strategy.get("production_contract_id") == production_contract.get("contract_id"),
        strategy.get("material_plan_id") == material_plan.get("material_plan_id"),
        isinstance(strategy.get("segments"), list), isinstance(strategy.get("issues"), list),
    ])


def compile_clip_strategy(production_contract: Mapping[str, Any], material_plan: Mapping[str, Any], segment_candidates: list[Mapping[str, Any]] | None = None, platform_hints: list[Any] | None = None) -> dict[str, Any]:
    """Compile a strategy from immutable upstream contracts and material state."""
    contract = production_contract if isinstance(production_contract, Mapping) else {}
    plan = material_plan if isinstance(material_plan, Mapping) else {}
    campaign_id = str(contract.get("campaign_id") or plan.get("campaign_id") or "")
    source_hash = str(contract.get("source_hash") or plan.get("source_hash") or "")
    brain_id = str(contract.get("brain_id") or plan.get("brain_id") or "")
    reconciliation_id = str(contract.get("reconciliation_id") or plan.get("reconciliation_id") or "")
    contract_id = str(contract.get("contract_id") or "")
    plan_id = str(plan.get("material_plan_id") or "")
    issues: list[dict[str, Any]] = []
    identity = {"campaign_id": campaign_id, "source_hash": source_hash, "brain_id": brain_id, "reconciliation_id": reconciliation_id, "production_contract_id": contract_id, "material_plan_id": plan_id}
    if not all(identity.values()):
        issues.append(_issue("identity_failure", "critical", "Required upstream identity is missing."))
    if contract.get("schema_version") != 1 or plan.get("schema_version") != 1:
        issues.append(_issue("schema_failure", "critical", "Production contract or material plan schema is invalid."))
    if plan.get("status") == "blocked":
        issues.append(_issue("material_plan_blocked", "critical", "Material plan is blocked; strategy cannot be execution-ready."))

    requirements = [x for x in (plan.get("requirements") or []) if isinstance(x, Mapping)]
    assets = [x for x in (plan.get("assets") or []) if isinstance(x, Mapping)]
    candidates = [x for x in (segment_candidates or []) if isinstance(x, Mapping)]
    platforms = _platforms(contract, plan, platform_hints)
    platform_variants = platforms or ["global"]
    assets_by_req: dict[str, list[Mapping[str, Any]]] = {}
    for asset in assets:
        for rid in asset.get("material_requirement_ids") or []:
            assets_by_req.setdefault(str(rid), []).append(asset)

    segments: list[dict[str, Any]] = []
    for requirement in sorted(requirements, key=lambda x: str(x.get("material_requirement_id") or "")):
        rid = str(requirement.get("material_requirement_id") or "")
        provenance = _provenance(requirement.get("provenance"))
        provenance["material_requirement_id"] = rid
        scope = _scope(requirement.get("scope"))
        scoped_platforms = scope["platforms"] or platform_variants
        matching = assets_by_req.get(rid, [])
        role = _role(requirement)
        if not matching:
            status = "blocked" if requirement.get("required") is True else "review"
            if requirement.get("required") is True:
                issues.append(_issue("missing_mandatory_segment", "critical", "Mandatory material has no usable asset.", rid, provenance["evidence_ids"]))
            elif requirement.get("required") is None:
                issues.append(_issue("unknown_segment_requirement", "warning", "Segment requirement semantics remain unknown.", rid, provenance["evidence_ids"]))
            for platform in scoped_platforms:
                segments.append({"segment_id": _segment_id(rid, "", role, platform), "material_requirement_id": rid, "asset_fingerprint": None, "source_ref": None, "start_seconds": None, "end_seconds": None, "role": role, "required": requirement.get("required"), "platforms": [platform] if platform != "global" else [], "reason": "Material requirement has no selected asset; timestamp is unresolved.", "rule_ids": [provenance["rule_id"]] if provenance["rule_id"] else [], "evidence_ids": provenance["evidence_ids"], "provenance": provenance, "status": status})
            continue
        for asset in sorted(matching, key=lambda x: str(x.get("asset_id") or x.get("fingerprint") or "")):
            asset_status = _norm(asset.get("status")).lower()
            status = "selected" if asset_status in _READY_ASSET_STATES else "review"
            if requirement.get("required") is True and asset_status not in _READY_ASSET_STATES:
                issues.append(_issue("mandatory_asset_not_ready", "critical", "Mandatory asset is not verified/acquired/ready.", rid, provenance["evidence_ids"]))
                status = "blocked"
            asset_prov = _provenance(asset.get("provenance"))
            merged_prov = {key: asset_prov.get(key) or provenance.get(key) for key in provenance}
            for platform in sorted(set(scoped_platforms)):
                candidate = next((x for x in candidates if str(x.get("asset_id") or x.get("asset_fingerprint") or "") in {str(asset.get("asset_id") or ""), str(asset.get("fingerprint") or "")}), {})
                start = candidate.get("start_seconds") if isinstance(candidate.get("start_seconds"), (int, float)) else None
                end = candidate.get("end_seconds") if isinstance(candidate.get("end_seconds"), (int, float)) else None
                if start is None or end is None:
                    timestamp_reason = "Timestamp unavailable; downstream/manual segment localization required."
                    issues.append(_issue("timestamp_unresolved", "warning", timestamp_reason, rid, provenance["evidence_ids"]))
                else:
                    timestamp_reason = "Timestamp supplied by structured segment metadata."
                segments.append({"segment_id": _segment_id(rid, str(asset.get("asset_id") or asset.get("fingerprint") or ""), role, platform), "material_requirement_id": rid, "asset_fingerprint": asset.get("fingerprint"), "source_ref": asset.get("source_url") or asset.get("source_type"), "start_seconds": start, "end_seconds": end, "role": role, "required": requirement.get("required"), "platforms": [platform] if platform != "global" else [], "reason": timestamp_reason, "rule_ids": [merged_prov["rule_id"]] if merged_prov.get("rule_id") else [], "evidence_ids": sorted(set(merged_prov.get("evidence_ids") or provenance.get("evidence_ids") or [])), "provenance": merged_prov, "status": status})

    for candidate in candidates:
        if not candidate.get("asset_id") and not candidate.get("asset_fingerprint"):
            issues.append(_issue("unbound_segment_candidate", "warning", "Segment candidate has no asset identity."))

    segments.sort(key=lambda x: (_ROLE_ORDER.get(x.get("role"), 99), tuple(x.get("platforms") or []), x.get("material_requirement_id") or "", x.get("segment_id") or ""))
    selected = [x for x in segments if x["status"] == "selected"]
    ordering = [x["segment_id"] for x in selected]
    fallbacks = deepcopy(plan.get("fallbacks") or [])
    if fallbacks:
        issues.append(_issue("fallback_available_not_activated", "warning", "Authorized fallback is recorded but was not silently activated."))
    issues = sorted({x["issue_id"]: x for x in issues}.values(), key=lambda x: x["issue_id"])
    status = "blocked" if any(x["severity"] == "critical" for x in issues) else "review" if issues or any(x["status"] == "review" for x in segments) else "ready"
    strategy = {"schema_version": SCHEMA_VERSION, "clip_strategy_id": "", **identity, "status": status, "platforms": platforms, "duration": _duration(contract), "segments": segments, "ordering": ordering, "constraints": deepcopy(contract.get("clip", {}).get("requirements", []) if isinstance(contract.get("clip"), Mapping) else []), "fallbacks": fallbacks, "issues": issues, "summary": {"candidate_segments": len(segments), "selected_segments": len(selected), "rejected_segments": 0, "unresolved_segments": sum(x["status"] in {"review", "blocked"} for x in segments), "platform_variants": len(platforms), "mandatory_segments": sum(x.get("required") is True for x in segments), "provenance_coverage": sum(bool(x.get("evidence_ids")) for x in segments) / max(1, len(segments))}}
    strategy["clip_strategy_id"] = _hash("clip-strategy-v1:", strategy)
    return strategy


__all__ = ["SCHEMA_VERSION", "compile_clip_strategy", "clip_strategy_is_current"]
