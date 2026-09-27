#!/usr/bin/env python3
"""Deterministic CA-04 Production Contract Compiler.

The compiler consumes only the canonical CA-03 reconciliation output.  It does
not resolve campaign meaning, select clips, resolve assets, or call an AI
provider.  Every compiled requirement keeps the reconciled rule identity and
its evidence/source lineage.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

SCHEMA_VERSION = 1
_REQUIREMENT_LEVELS = {"mandatory", "optional", "unknown"}
_INTERPRETATIONS = {"explicit", "inferred", "conflicting", "ambiguous", "unsupported", "manual_required"}


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


def _path(rule: dict[str, Any]) -> str:
    return _norm(rule.get("source_rule_path") or rule.get("path")).lower().removeprefix("rules.")


def _leaf(rule: dict[str, Any]) -> str:
    return _path(rule).split(".")[-1]


def _domain(rule: dict[str, Any]) -> str:
    path = _path(rule)
    root = path.split(".")[0]
    if root in {"production", "material", "posting", "content", "safety", "platform", "audience"}:
        return root
    return {
        "asset_sources": "material", "material_policy": "material",
        "cta_required": "posting", "cta_text": "posting", "handles": "posting",
        "hashtags": "posting", "disclosures": "posting", "posting_rules": "posting",
        "account_rules": "posting", "native_tags": "posting", "sound_policy": "posting", "audio_policy": "posting",
        "subtitle_required": "production", "subtitle_style": "production",
        "subtitle_delivery_profile": "production", "min_duration_seconds": "production",
        "max_duration_seconds": "production", "aspect_ratio": "production",
        "official_audio_required": "production", "watermark_required": "production",
        "third_party_watermark_allowed": "production", "platforms": "platform",
        "source_policy": "content", "allowed_content": "content", "prohibited_content": "content",
    }.get(_leaf(rule), "content")


def _scope(rule: dict[str, Any]) -> dict[str, list[str]]:
    raw = rule.get("scope") if isinstance(rule.get("scope"), dict) else {}
    return {dimension: sorted({_norm(x).lower() if dimension != "audiences" else _norm(x) for x in raw.get(dimension, []) or [] if _norm(x)}) for dimension in ("platforms", "languages", "audiences")}


def _required(rule: dict[str, Any]) -> bool | None:
    level = _norm(rule.get("requirement_level")).lower()
    if level == "mandatory":
        return True
    if level == "optional":
        return False
    return None


def _provenance(rule: dict[str, Any]) -> dict[str, Any]:
    level = _norm(rule.get("requirement_level")).lower() or "unknown"
    interpretation = _norm(rule.get("interpretation_type")).lower() or "manual_required"
    return {
        "rule_id": str(rule.get("rule_id") or ""),
        "reconciliation_rule_id": str(rule.get("rule_id") or ""),
        "brain_rule_ids": sorted(str(x) for x in rule.get("brain_rule_ids") or []),
        "evidence_ids": sorted(str(x) for x in rule.get("evidence_ids") or []),
        "source_references": deepcopy(rule.get("source_references") or []),
        "requirement_level": level if level in _REQUIREMENT_LEVELS else "unknown",
        "interpretation_type": interpretation if interpretation in _INTERPRETATIONS else "manual_required",
        "resolution": deepcopy(rule.get("resolution") or {}),
        "scope": _scope(rule),
    }


def _requirement(rule: dict[str, Any], field: str | None = None, value: Any = None) -> dict[str, Any]:
    result = {"field": field or _leaf(rule), "value": _canonical(rule.get("value") if value is None else value), "required": _required(rule), "scope": _scope(rule), "provenance": _provenance(rule)}
    if result["value"] is None or result["value"] == "":
        result.pop("value")
    return result


def _duration(value: Any) -> dict[str, Any] | None:
    text = _norm(value)
    if not text:
        return None
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if not nums:
        return None
    constraint: dict[str, Any] = {}
    if len(nums) >= 2 or re.search(r"\b(?:to|through|and|-|–)\b|\d\s*[-–]\s*\d", text, re.I):
        constraint["min"] = min(nums[0], nums[1])
        constraint["max"] = max(nums[0], nums[1])
    else:
        constraint["exact"] = nums[0]
    return constraint


def _rule_list(rules: list[dict[str, Any]], domains: set[str], leaves: set[str] | None = None) -> list[dict[str, Any]]:
    selected = [rule for rule in rules if _domain(rule) in domains and (leaves is None or _leaf(rule) in leaves)]
    return sorted(selected, key=lambda rule: (_path(rule), _key(_scope(rule)), _key(rule.get("value")), str(rule.get("rule_id") or "")))


def _compile_requirements(rules: list[dict[str, Any]], domains: set[str], leaves: set[str] | None = None, aliases: dict[str, str] | None = None) -> list[dict[str, Any]]:
    output = []
    for rule in _rule_list(rules, domains, leaves):
        field = (aliases or {}).get(_leaf(rule), _leaf(rule))
        item = _requirement(rule, field)
        if field == "duration":
            constraint = _duration(rule.get("value"))
            if constraint:
                item.pop("value", None)
                item["constraint"] = constraint
        output.append(item)
    return output


def _scoped(items: list[dict[str, Any]], key: str) -> Any:
    scoped: dict[str, list[dict[str, Any]]] = {}
    global_items: list[dict[str, Any]] = []
    for item in items:
        platforms = item.get("scope", {}).get("platforms", [])
        if platforms:
            for platform in platforms:
                scoped.setdefault(platform, []).append(deepcopy(item))
        else:
            global_items.append(item)
    if not scoped:
        return items
    result: dict[str, Any] = {}
    if global_items:
        result["global"] = global_items
    result.update({platform: values for platform, values in sorted(scoped.items())})
    return result


def _issues(reconciliation: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    for error in reconciliation.get("integrity_errors") or []:
        code = str(error)
        issues.append({
            "issue_id": _hash("contract-issue-v1:", {"integrity_error": code}),
            "severity": "critical", "type": "integrity_failure", "rule_id": code,
            "evidence_ids": [], "reason": code, "resolution": "manual_required",
        })
    for finding in reconciliation.get("findings") or []:
        if not isinstance(finding, dict) or finding.get("status") != "unresolved":
            continue
        severity = "critical" if str(finding.get("severity") or "").upper() == "CRITICAL" else "warning"
        issues.append({
            "issue_id": _hash("contract-issue-v1:", {"finding_id": finding.get("finding_id"), "status": finding.get("status")}),
            "severity": severity, "type": str(finding.get("code") or "unresolved_requirement"),
            "rule_id": str(finding.get("finding_id") or ""), "evidence_ids": sorted(str(x) for x in finding.get("evidence_ids") or []),
            "reason": _norm(finding.get("reason") or "Reconciliation finding remains unresolved."), "resolution": "manual_required",
        })
    for conflict in reconciliation.get("conflicts") or []:
        if isinstance(conflict, dict) and conflict.get("status") == "unresolved" and conflict.get("critic_finding_id") is None:
            issues.append({
                "issue_id": _hash("contract-issue-v1:", {"conflict_id": conflict.get("conflict_id")}),
                "severity": "critical" if str(conflict.get("severity") or "").upper() == "CRITICAL" else "warning",
                "type": str(conflict.get("kind") or "unresolved_conflict"), "rule_id": str(conflict.get("conflict_id") or ""),
                "evidence_ids": sorted(str(x) for x in conflict.get("evidence_ids") or []),
                "reason": _norm(conflict.get("reason") or "Reconciliation conflict remains unresolved."), "resolution": "manual_required",
            })
    return sorted({str(item["issue_id"]): item for item in issues}.values(), key=lambda item: item["issue_id"])


def compile_production_contract(reconciliation: dict[str, Any]) -> dict[str, Any]:
    """Compile a CA-03 reconciliation into a deterministic execution contract."""
    source = reconciliation if isinstance(reconciliation, dict) else {}
    rules = [item for item in source.get("rules") or [] if isinstance(item, dict)]
    campaign_id = str(source.get("campaign_id") or "")
    source_hash = str(source.get("source_hash") or "")
    brain_id = str(source.get("brain_id") or "")
    critic_id = str(source.get("critic_id") or "")
    reconciliation_id = str(source.get("reconciliation_id") or "")
    identity = {"campaign_id": campaign_id, "source_hash": source_hash, "brain_id": brain_id, "reconciliation_id": reconciliation_id, "schema_version": SCHEMA_VERSION}
    integrity_errors = list(source.get("integrity_errors") or [])
    if not all(identity.values()):
        integrity_errors.append("missing_reconciliation_identity")
    if source.get("schema_version") != 1:
        integrity_errors.append("invalid_reconciliation_schema")

    production = {"requirements": _compile_requirements(rules, {"production", "platform"}, {"min_duration_seconds", "max_duration_seconds", "aspect_ratio", "platforms", "subtitle_required", "subtitle_style", "subtitle_delivery_profile", "official_audio_required", "watermark_required", "third_party_watermark_allowed", "source_policy", "language", "hook", "context", "content_requirements", "forbidden_content", "visual_requirements", "brand_requirements", "cta_required", "cta_text", "handles", "hashtags", "disclosures"}, {"min_duration_seconds": "duration", "max_duration_seconds": "duration"})}
    # Combine min/max duration rules into one bounded requirement while preserving both provenance records.
    duration_rules = [r for r in rules if _leaf(r) in {"min_duration_seconds", "max_duration_seconds"}]
    if duration_rules:
        mins = [int(r["value"]) for r in duration_rules if _leaf(r) == "min_duration_seconds" and str(r.get("value")).isdigit()]
        maxs = [int(r["value"]) for r in duration_rules if _leaf(r) == "max_duration_seconds" and str(r.get("value")).isdigit()]
        duration = {"field": "duration_seconds", "required": any(_required(r) is True for r in duration_rules), "constraint": {}, "scope": {}, "provenance": [_provenance(r) for r in duration_rules]}
        if mins: duration["constraint"]["min"] = max(mins)
        if maxs: duration["constraint"]["max"] = min(maxs)
        production["requirements"] = [item for item in production["requirements"] if item["field"] != "duration"]
        production["requirements"].append(duration)
        production["requirements"].sort(key=lambda item: (item["field"], _key(item.get("scope")), _key(item.get("value"))))
    production["requirements"] = _scoped(production["requirements"], "platform")

    material_items = _compile_requirements(rules, {"material"}, {"asset_sources", "material_policy", "asset_roles", "asset_constraints", "required_assets", "preferred_assets", "fallback_assets", "missing_asset_policy"})
    material = {"requirements": material_items, "required_assets": [], "preferred_assets": [], "fallback_assets": [], "asset_roles": [], "asset_constraints": [], "missing_asset_policy": "unspecified"}
    for item in material_items:
        field = item["field"]
        if field in material and field != "requirements":
            target = item.get("value")
            material[field] = target if isinstance(target, list) else [target] if target is not None else []
    material["asset_requirements"] = [{**item, "resolution_status": "unresolved"} for item in material_items if item["field"] in {"asset_sources", "required_assets", "preferred_assets", "fallback_assets", "asset_roles"}]

    clip = {"requirements": _compile_requirements(rules, {"content", "production", "platform", "audience"}, {"min_duration_seconds", "max_duration_seconds", "platforms", "source_policy", "allowed_content", "prohibited_content", "topic_terms", "hook", "context", "language", "campaign_relevance", "platform_fit", "distinctness", "risk"}, {"min_duration_seconds": "duration", "max_duration_seconds": "duration", "prohibited_content": "forbidden_content"})}
    clip_duration_rules = [r for r in rules if _leaf(r) in {"min_duration_seconds", "max_duration_seconds"}]
    if clip_duration_rules:
        clip_duration = {"field": "duration_seconds", "required": any(_required(r) is True for r in clip_duration_rules), "constraint": {}, "scope": {}, "provenance": [_provenance(r) for r in clip_duration_rules]}
        mins = [int(r["value"]) for r in clip_duration_rules if _leaf(r) == "min_duration_seconds" and str(r.get("value")).isdigit()]
        maxs = [int(r["value"]) for r in clip_duration_rules if _leaf(r) == "max_duration_seconds" and str(r.get("value")).isdigit()]
        if mins: clip_duration["constraint"]["min"] = max(mins)
        if maxs: clip_duration["constraint"]["max"] = min(maxs)
        clip["requirements"] = [item for item in clip["requirements"] if item["field"] != "duration"]
        clip["requirements"].append(clip_duration)
        clip["requirements"].sort(key=lambda item: (item["field"], _key(item.get("scope")), _key(item.get("value"))))
    clip["requirements"] = _scoped(clip["requirements"], "platform")

    posting_items = _compile_requirements(rules, {"posting", "platform"}, {"platforms", "cta_required", "cta_text", "handles", "hashtags", "disclosures", "posting_rules", "account_rules", "sound_policy", "native_tags", "subtitle_delivery_profile", "caption_requirements", "schedule_intent", "audio_policy", "subtitle_delivery", "native_tag_requirements"})
    posting = {"requirements": posting_items, "platforms": [], "caption_requirements": [], "cta": [], "hashtags": [], "handles": [], "disclosure": [], "audio_policy": [], "subtitle_delivery": [], "native_tag_requirements": [], "schedule_intent": []}
    for item in posting_items:
        field = item["field"]
        aliases = {"cta_text": "cta", "disclosures": "disclosure", "sound_policy": "audio_policy", "native_tags": "native_tag_requirements", "posting_rules": "caption_requirements", "account_rules": "handles"}
        target = aliases.get(field, field)
        if target in posting:
            posting[target].append(item)
    posting["handles"] = _scoped(posting["handles"], "handles")
    posting["hashtags"] = _scoped(posting["hashtags"], "hashtags")
    posting["cta"] = _scoped(posting["cta"], "cta")

    compliance_fields = {"duration", "content", "campaign_relevance", "caption", "cta", "handles", "hashtags", "disclosure", "subtitle", "audio", "platform", "artifact", "distinctness"}
    compliance = {"checks": [{"check": item["field"], "required": item.get("required"), "scope": item.get("scope", {}), "provenance": item.get("provenance")} for item in _compile_requirements(rules, {"production", "material", "content", "posting", "platform", "audience"}) if item["field"] in compliance_fields]}
    compliance["checks"].sort(key=lambda item: (item["check"], _key(item.get("scope")), _key(item.get("provenance"))))

    issues = _issues(source, rules)
    def _unresolved(provenance: Any) -> bool:
        values = provenance if isinstance(provenance, list) else [provenance]
        return any(isinstance(item, dict) and item.get("resolution", {}).get("status") == "unresolved" for item in values)

    unresolved_mandatory = any(item.get("required") is True and _unresolved(item.get("provenance")) for item in production.get("requirements", []) if isinstance(item, dict))
    status = "blocked" if integrity_errors or str(source.get("status")) == "blocked" or any(item["severity"] == "critical" for item in issues) or unresolved_mandatory else "review" if issues or str(source.get("status")) == "review" else "ready"
    contract = {"schema_version": SCHEMA_VERSION, "contract_id": "", **identity, "critic_id": critic_id, "status": status, "production": production, "material": material, "clip": clip, "posting": posting, "compliance": compliance, "dependencies": ["material", "clip", "production", "compliance", "posting"], "issues": issues, "summary": {"mandatory_requirements": sum(item.get("required") is True for item in production.get("requirements", []) if isinstance(item, dict)), "unresolved_requirements": sum(_unresolved(item.get("provenance")) for item in production.get("requirements", []) if isinstance(item, dict)), "issue_count": len(issues)}}
    identity_payload = {key: contract[key] for key in ("campaign_id", "source_hash", "brain_id", "reconciliation_id", "schema_version")}
    contract["contract_id"] = _hash("production-contract-v1:", identity_payload)
    return contract


__all__ = ["SCHEMA_VERSION", "compile_production_contract"]
