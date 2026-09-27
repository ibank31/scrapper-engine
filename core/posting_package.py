#!/usr/bin/env python3
"""Deterministic CA-07 posting-package compiler.

The compiler consumes authoritative posting requirements from the production
contract plus the already-produced clip strategy and campaign source fields.
It never calls an LLM, invents copy, publishes, or mutates its inputs.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

SCHEMA_VERSION = 1
_STATUSES = {"ready", "review", "blocked"}
_PLATFORMS = {"instagram", "tiktok", "youtube", "facebook", "x", "twitter", "linkedin", "threads"}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return _norm(value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return value


def _key(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_key(value).encode("utf-8")).hexdigest()


def _scope(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, Mapping) else {}
    return {dimension: sorted({_norm(x).lower() if dimension != "audiences" else _norm(x) for x in raw.get(dimension, []) or [] if _norm(x)}) for dimension in ("platforms", "languages", "audiences")}


def _provenance(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return {
        "production_contract_requirement_id": str(raw.get("production_contract_requirement_id") or raw.get("requirement_id") or ""),
        "reconciliation_rule_id": str(raw.get("reconciliation_rule_id") or raw.get("rule_id") or ""),
        "rule_id": str(raw.get("rule_id") or ""),
        "brain_rule_ids": sorted(str(x) for x in raw.get("brain_rule_ids") or []),
        "evidence_ids": sorted(str(x) for x in raw.get("evidence_ids") or []),
        "source_references": deepcopy(raw.get("source_references") or []),
        "source_hash": str(raw.get("source_hash") or ""),
        "requirement_level": str(raw.get("requirement_level") or "unknown"),
        "interpretation_type": str(raw.get("interpretation_type") or "manual_required"),
        "resolution": deepcopy(raw.get("resolution") or {}),
        "scope": _scope(raw.get("scope")),
    }


def _item(field: str, value: Any, required: bool | None, provenance: Any, scope: Any = None, *, manual_required: bool = False) -> dict[str, Any]:
    prov = _provenance(provenance)
    if scope is not None:
        prov["scope"] = _scope(scope)
    result = {"field": field, "value": _canonical(value), "required": required, "scope": prov["scope"], "provenance": prov}
    if manual_required:
        result["manual_required"] = True
    return result


def _flatten_scoped(value: Any, field: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if not isinstance(value, Mapping):
        return []
    output: list[dict[str, Any]] = []
    for platform in sorted(value):
        for item in value[platform] if isinstance(value[platform], list) else []:
            if isinstance(item, Mapping):
                copied = dict(item)
                copied["scope"] = {**_scope(copied.get("scope")), "platforms": [platform] if platform != "global" else _scope(copied.get("scope"))["platforms"]}
                output.append(copied)
    return output


def _posting_items(contract: Mapping[str, Any], field: str) -> list[dict[str, Any]]:
    posting = contract.get("posting") if isinstance(contract.get("posting"), Mapping) else {}
    raw = posting.get(field)
    return [dict(item) for item in _flatten_scoped(raw, field)]


def _platforms(contract: Mapping[str, Any], strategy: Mapping[str, Any], campaign: Mapping[str, Any]) -> list[str]:
    values: set[str] = set()
    for source in (campaign.get("platforms"), strategy.get("platforms")):
        values.update(_norm(x).lower() for x in source or [] if _norm(x))
    posting = contract.get("posting") if isinstance(contract.get("posting"), Mapping) else {}
    values.update(_norm(x).lower() for x in posting.get("platforms") or [] if _norm(x))
    for field in ("cta", "hashtags", "handles", "disclosure", "audio_policy", "subtitle_delivery", "native_tag_requirements", "schedule_intent"):
        for item in _posting_items(contract, field):
            values.update(_scope(item.get("scope")).get("platforms", []))
    return sorted(values or {"global"})


def _campaign_fields(campaign: Mapping[str, Any], platform: str) -> dict[str, Any]:
    """Read only explicit campaign-provided posting fields; never synthesize them."""
    posting = campaign.get("posting") if isinstance(campaign.get("posting"), Mapping) else {}
    rules = campaign.get("rules") if isinstance(campaign.get("rules"), Mapping) else {}
    merged = {**rules, **posting}
    result: dict[str, Any] = {}
    for field in ("caption", "caption_text", "cta", "cta_text", "hashtags", "handles", "disclosures", "disclosure", "audio_policy", "sound_policy", "subtitle_delivery", "native_tag_requirements", "native_tags", "schedule_intent"):
        value = merged.get(field)
        if isinstance(value, Mapping):
            value = value.get(platform, value.get("global"))
        if value not in (None, "", [], {}):
            result[field] = value
    return result


def _source_items(contract: Mapping[str, Any], field: str, campaign: Mapping[str, Any], platform: str) -> list[dict[str, Any]]:
    items = []
    for item in _posting_items(contract, field):
        scope = _scope(item.get("scope")).get("platforms", [])
        if not scope or platform in scope:
            items.append(item)
    return items


def _issue(kind: str, severity: str, platform: str, field: str, reason: str, provenance: Any = None) -> dict[str, Any]:
    item = {"type": kind, "severity": severity, "platform": platform, "field": field, "reason": reason, "provenance": _provenance(provenance)}
    return {"issue_id": _hash("posting-package-issue-v1:", item), **item}


def posting_package_is_current(package: Mapping[str, Any] | None, production_contract: Mapping[str, Any] | None, clip_strategy: Mapping[str, Any] | None) -> bool:
    if not isinstance(package, Mapping) or not isinstance(production_contract, Mapping) or not isinstance(clip_strategy, Mapping):
        return False
    return all([
        package.get("schema_version") == SCHEMA_VERSION,
        bool(package.get("posting_package_id")),
        package.get("campaign_id") == production_contract.get("campaign_id") == clip_strategy.get("campaign_id"),
        package.get("source_hash") == production_contract.get("source_hash") == clip_strategy.get("source_hash"),
        package.get("brain_id") == production_contract.get("brain_id") == clip_strategy.get("brain_id"),
        package.get("reconciliation_id") == production_contract.get("reconciliation_id") == clip_strategy.get("reconciliation_id"),
        package.get("production_contract_id") == production_contract.get("contract_id"),
        package.get("clip_strategy_id") == clip_strategy.get("clip_strategy_id"),
        isinstance(package.get("platforms"), Mapping),
        isinstance(package.get("issues"), list),
    ])


def compile_posting_package(production_contract: Mapping[str, Any], clip_strategy: Mapping[str, Any], campaign: Mapping[str, Any] | None = None) -> dict[str, Any]:
    contract = production_contract if isinstance(production_contract, Mapping) else {}
    strategy = clip_strategy if isinstance(clip_strategy, Mapping) else {}
    source = campaign if isinstance(campaign, Mapping) else {}
    identity = {
        "campaign_id": str(contract.get("campaign_id") or strategy.get("campaign_id") or source.get("id") or ""),
        "source_hash": str(contract.get("source_hash") or strategy.get("source_hash") or ""),
        "brain_id": str(contract.get("brain_id") or strategy.get("brain_id") or ""),
        "reconciliation_id": str(contract.get("reconciliation_id") or strategy.get("reconciliation_id") or ""),
        "production_contract_id": str(contract.get("contract_id") or ""),
        "clip_strategy_id": str(strategy.get("clip_strategy_id") or ""),
    }
    issues: list[dict[str, Any]] = []
    if not all(identity.values()):
        issues.append(_issue("identity_failure", "critical", "global", "identity", "Posting package identity chain is incomplete."))
    if contract.get("schema_version") != 1 or strategy.get("schema_version") != 1:
        issues.append(_issue("schema_failure", "critical", "global", "identity", "Upstream contract schema is invalid."))

    platforms: dict[str, dict[str, Any]] = {}
    mandatory_total = 0
    mandatory_with_provenance = 0
    for platform in _platforms(contract, strategy, source):
        explicit = _campaign_fields(source, platform)
        package: dict[str, Any] = {"caption": [], "cta": [], "handles": [], "hashtags": [], "disclosures": [], "audio_policy": [], "subtitle_delivery": [], "native_tag_requirements": [], "schedule_intent": [], "manual_actions": [], "issues": []}
        field_map = {"disclosure": "disclosures", "native_tags": "native_tag_requirements", "sound_policy": "audio_policy"}
        for field in ("cta", "hashtags", "handles", "disclosure", "audio_policy", "subtitle_delivery", "native_tag_requirements", "schedule_intent"):
            target = field_map.get(field, field)
            authoritative = _source_items(contract, field, source, platform)
            if authoritative:
                for raw in authoritative:
                    raw_provenance = dict(raw.get("provenance") or {})
                    raw_provenance.setdefault("source_hash", identity["source_hash"])
                    copied = _item(target, raw.get("value"), raw.get("required"), raw_provenance, raw.get("scope"), manual_required=raw_provenance.get("interpretation_type") in {"unsupported", "ambiguous", "conflicting", "manual_required"})
                    package[target].append(copied)
                    if copied["required"] is True:
                        mandatory_total += 1
                        if copied["provenance"]["evidence_ids"] and copied["provenance"]["source_hash"] == identity["source_hash"]:
                            mandatory_with_provenance += 1
                        if copied["value"] in (None, "", [], {}):
                            issues.append(_issue("missing_mandatory_posting", "critical", platform, target, "Mandatory posting value is absent.", copied["provenance"]))
                        if copied.get("manual_required"):
                            issues.append(_issue("mandatory_uncertain", "critical", platform, target, "Mandatory posting requirement is unresolved or unsupported.", copied["provenance"]))
            elif target in explicit:
                package[target].append(_item(target, explicit[target], True, {"source_hash": identity["source_hash"]}, {"platforms": [platform]}))
        caption = explicit.get("caption") or explicit.get("caption_text")
        if caption is not None:
            package["caption"] = [_item("caption", caption, True, {"source_hash": identity["source_hash"]}, {"platforms": [platform]})]
        # Missing mandatory posting families are blocked only when the contract
        # actually declares that family mandatory; no requirement is invented.
        for field in ("cta", "hashtags", "handles", "disclosures"):
            declared = [x for x in _source_items(contract, field, source, platform) if x.get("required") is True]
            if declared and not package[field]:
                for raw in declared:
                    issues.append(_issue("missing_mandatory_posting", "critical", platform, field, "Mandatory posting value is absent.", raw.get("provenance")))
        for field in ("audio_policy", "subtitle_delivery", "native_tag_requirements"):
            if any(x.get("manual_required") for x in package[field]):
                package["manual_actions"].append({"action": "manual_required", "field": field, "reason": "Platform-native or unresolved requirement cannot be executed by this compiler."})
        package["issues"] = sorted({x["issue_id"]: x for x in issues if x["platform"] == platform}.values(), key=lambda x: x["issue_id"])
        platforms[platform] = package

    if mandatory_total and mandatory_with_provenance != mandatory_total:
        issues.append(_issue("provenance_incomplete", "critical", "global", "posting", "Not every mandatory posting field has verified source provenance."))
    provenance_coverage = mandatory_with_provenance / mandatory_total if mandatory_total else 1.0
    for platform, package in platforms.items():
        package["issues"] = sorted({x["issue_id"]: x for x in issues if x["platform"] == platform}.values(), key=lambda x: x["issue_id"])
    issues = sorted({x["issue_id"]: x for x in issues}.values(), key=lambda x: x["issue_id"])
    status = "blocked" if any(x["severity"] == "critical" for x in issues) else "review" if any(package["issues"] or package["manual_actions"] for package in platforms.values()) else "ready"
    result = {"schema_version": SCHEMA_VERSION, "posting_package_id": "", **identity, "status": status, "platforms": platforms, "issues": issues, "summary": {"platform_count": len(platforms), "mandatory_fields": mandatory_total, "provenance_coverage": provenance_coverage, "manual_action_count": sum(len(x["manual_actions"]) for x in platforms.values())}}
    result["posting_package_id"] = _hash("posting-package-v1:", result)
    return result


__all__ = ["SCHEMA_VERSION", "compile_posting_package", "posting_package_is_current"]
