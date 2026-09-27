#!/usr/bin/env python3
"""Deterministic CA-08 final campaign compliance gate.

CA-08 verifies the already-compiled campaign intelligence chain. It does not
invent policy, reinterpret source material, call an LLM, render, publish,
mutate Buffer/D1, or change any upstream artifact.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

SCHEMA_VERSION = 1
_ALLOWED_STATUSES = {"ready", "review", "blocked", "pass"}
_MANDATORY_INTERPRETATIONS = {"unsupported", "ambiguous", "conflicting", "manual_required"}
_RESTRICTION_FIELDS = {"prohibited_content", "forbidden_content", "allowed_content", "safety", "content_requirements"}
_POSTING_FIELDS = {"caption", "cta", "hashtags", "handles", "disclosure", "disclosures", "audio_policy", "sound_policy", "subtitle_delivery", "native_tag_requirements", "native_tags", "schedule_intent"}
_SCHEMA_KEYS = {
    "evidence_contract": 1, "campaign_brain": 1, "campaign_critic": 1, "campaign_reconciliation": 1,
    "production_contract": 1, "material_plan": 1, "clip_strategy": 1, "posting_package": 1,
}

def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return value

def _key(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _hash(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_key(value).encode("utf-8")).hexdigest()

def _scope(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, Mapping) else {}
    return {
        dimension: sorted({
            (" ".join(str(item).split()).lower() if dimension != "audiences" else " ".join(str(item).split()))
            for item in raw.get(dimension, []) or [] if str(item).strip()
        })
        for dimension in ("platforms", "languages", "audiences")
    }

def _norm_status(value: Any) -> str:
    return str(value or "").strip().lower()

def _issue(code: str, severity: str, message: str, *, stage: str = "global", field: str = "", refs: Any = None) -> dict[str, Any]:
    item = {
        "code": code, "severity": severity, "stage": stage, "field": field,
        "message": " ".join(str(message).split()),
        "references": sorted({str(x) for x in (refs or []) if str(x)}),
    }
    return {"issue_id": _hash("compliance-issue-v1:", item), **item}

def _verified_evidence_ids(evidence_contract: Mapping[str, Any], brain: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for collection in (
        evidence_contract.get("verified") if isinstance(evidence_contract, Mapping) else [],
        (brain.get("evidence") or {}).get("verified") if isinstance(brain.get("evidence"), Mapping) else [],
    ):
        for item in collection or []:
            if isinstance(item, Mapping) and item.get("evidence_id"):
                ids.add(str(item["evidence_id"]))
    return ids

def _brain_rule_ids(brain: Mapping[str, Any]) -> set[str]:
    return {str(item.get("rule_id")) for item in brain.get("rules") or [] if isinstance(item, Mapping) and item.get("rule_id")}

def _reconciliation_rule_ids(reconciliation: Mapping[str, Any]) -> set[str]:
    return {str(item.get("rule_id")) for item in reconciliation.get("rules") or [] if isinstance(item, Mapping) and item.get("rule_id")}

def _production_requirement_ids(production: Mapping[str, Any]) -> set[str]:
    contract_id = production.get("contract_id")
    result: set[str] = set()
    material = production.get("material") if isinstance(production.get("material"), Mapping) else {}
    for item in material.get("requirements", []) if isinstance(material.get("requirements"), list) else []:
        if not isinstance(item, Mapping):
            continue
        result.add(_hash("production-requirement-v1:", {
            "production_contract_id": contract_id, "field": item.get("field"),
            "value": item.get("value"), "scope": _scope(item.get("scope")),
        }))
    return result

def _iter_material_requirements(material_plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in material_plan.get("requirements") or [] if isinstance(item, Mapping)]

def _iter_posting_requirements(production: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    posting = production.get("posting") if isinstance(production.get("posting"), Mapping) else {}
    result: list[Mapping[str, Any]] = []
    for field in _POSTING_FIELDS:
        raw = posting.get(field)
        if isinstance(raw, list):
            result.extend(item for item in raw if isinstance(item, Mapping))
        elif isinstance(raw, Mapping):
            for platform_items in raw.values():
                if isinstance(platform_items, list):
                    result.extend(item for item in platform_items if isinstance(item, Mapping))
    result.extend(
        item for item in posting.get("requirements", []) or []
        if isinstance(item, Mapping) and str(item.get("field") or "").lower() in _POSTING_FIELDS
    )
    dedupe: dict[str, Mapping[str, Any]] = {}
    for item in result:
        dedupe[_key(item)] = item
    return list(dedupe.values())

def _iter_posting_package_items(posting_package: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    platforms = posting_package.get("platforms") if isinstance(posting_package.get("platforms"), Mapping) else {}
    for platform in sorted(platforms):
        payload = platforms.get(platform)
        if not isinstance(payload, Mapping):
            continue
        for field in _POSTING_FIELDS:
            values = payload.get(field)
            if isinstance(values, list):
                result.extend(item for item in values if isinstance(item, Mapping))
    return result

def _canonical_posting_field(value: Any) -> str:
    field = str(value or "").lower()
    return {
        "cta_text": "cta", "disclosure": "disclosures", "disclosures": "disclosures",
        "native_tags": "native_tag_requirements", "native_tag_requirements": "native_tag_requirements",
        "sound_policy": "audio_policy",
    }.get(field, field)

def _item_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    if _canonical_posting_field(expected.get("field")) != _canonical_posting_field(actual.get("field")):
        return False
    if _scope(expected.get("scope")) != _scope(actual.get("scope")):
        return False
    if expected.get("required") is True and actual.get("required") is not True:
        return False
    if "value" in expected and _canonical(expected.get("value")) != _canonical(actual.get("value")):
        return False
    ep = expected.get("provenance") if isinstance(expected.get("provenance"), Mapping) else {}
    ap = actual.get("provenance") if isinstance(actual.get("provenance"), Mapping) else {}
    expected_ids = {str(x) for x in ep.get("evidence_ids") or []}
    actual_ids = {str(x) for x in ap.get("evidence_ids") or []}
    if expected_ids and not expected_ids.issubset(actual_ids):
        return False
    expected_rule = str(ep.get("rule_id") or ep.get("reconciliation_rule_id") or "")
    actual_rule = str(ap.get("rule_id") or ap.get("reconciliation_rule_id") or "")
    if expected_rule and expected_rule != actual_rule:
        return False
    return True

def _check_required_provenance(stage: str, items: list[Mapping[str, Any]], valid_evidence: set[str], current_source_hash: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in items:
        required = item.get("required") is True or str(item.get("requirement_level") or "").lower() == "mandatory"
        if not required:
            continue
        prov = item.get("provenance")
        if isinstance(prov, list):
            provenances = [x for x in prov if isinstance(x, Mapping)]
        elif isinstance(prov, Mapping):
            provenances = [prov]
        else:
            provenances = [item] if any(key in item for key in ("evidence_ids", "interpretation_type", "resolution", "source_hash")) else []
        evidence_ids = {str(x) for p in provenances for x in p.get("evidence_ids") or []}
        source_hashes = {str(p.get("source_hash") or "") for p in provenances if str(p.get("source_hash") or "")}
        if not evidence_ids or not evidence_ids.issubset(valid_evidence) or (source_hashes and source_hashes != {current_source_hash}):
            issues.append(_issue(
                "provenance_invalid", "critical",
                f"Mandatory {stage} item lacks complete current verified provenance.",
                stage=stage, field=str(item.get("field") or item.get("material_requirement_id") or ""),
                refs=sorted(evidence_ids),
            ))
        for p in provenances:
            interpretation = _norm_status(p.get("interpretation_type"))
            resolution = p.get("resolution") if isinstance(p.get("resolution"), Mapping) else {}
            if interpretation in _MANDATORY_INTERPRETATIONS and _norm_status(resolution.get("status")) != "resolved":
                issues.append(_issue(
                    "mandatory_uncertain", "critical",
                    f"Mandatory {stage} item remains {interpretation}.",
                    stage=stage, field=str(item.get("field") or item.get("material_requirement_id") or ""),
                    refs=sorted(evidence_ids),
                ))
    return issues

def _check_identity_and_schema(artifacts: Mapping[str, Mapping[str, Any]], campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_campaign = str(campaign.get("id") or "")
    expected_source_hash = str(campaign.get("source_hash") or "")
    for name, expected_schema in _SCHEMA_KEYS.items():
        artifact = artifacts.get(name)
        if not isinstance(artifact, Mapping):
            issues.append(_issue("artifact_missing", "critical", f"{name} artifact is missing.", stage=name))
            continue
        if artifact.get("schema_version") != expected_schema:
            issues.append(_issue("schema_invalid", "critical", f"{name} schema_version is invalid.", stage=name))
    if expected_campaign:
        for name, artifact in artifacts.items():
            if name == "evidence_contract":
                continue
            if isinstance(artifact, Mapping) and str(artifact.get("campaign_id") or "") != expected_campaign:
                issues.append(_issue("identity_mismatch", "critical", f"{name} campaign_id does not match campaign.", stage=name, field="campaign_id"))
    if expected_source_hash:
        for name, artifact in artifacts.items():
            if isinstance(artifact, Mapping) and str(artifact.get("source_hash") or "") != expected_source_hash:
                issues.append(_issue("stale_source_hash", "critical", f"{name} source_hash is stale or mismatched.", stage=name, field="source_hash"))
    if any(name != "evidence_contract" and not str(artifact.get("campaign_id") or "") for name, artifact in artifacts.items() if isinstance(artifact, Mapping)):
        issues.append(_issue("identity_incomplete", "critical", "One or more stage artifacts have no campaign_id.", stage="global", field="campaign_id"))
    if any(not str(artifact.get("source_hash") or "") for artifact in artifacts.values() if isinstance(artifact, Mapping)):
        issues.append(_issue("identity_incomplete", "critical", "One or more artifacts have no source_hash.", stage="global", field="source_hash"))

    brain = artifacts.get("campaign_brain") or {}
    critic = artifacts.get("campaign_critic") or {}
    reconciliation = artifacts.get("campaign_reconciliation") or {}
    production = artifacts.get("production_contract") or {}
    material = artifacts.get("material_plan") or {}
    clip = artifacts.get("clip_strategy") or {}
    posting = artifacts.get("posting_package") or {}
    links = [
        ("critic", critic, "brain_id", brain.get("brain_id")),
        ("reconciliation", reconciliation, "brain_id", brain.get("brain_id")),
        ("reconciliation", reconciliation, "critic_id", critic.get("critic_id")),
        ("production_contract", production, "brain_id", brain.get("brain_id")),
        ("production_contract", production, "critic_id", critic.get("critic_id")),
        ("production_contract", production, "reconciliation_id", reconciliation.get("reconciliation_id")),
        ("material_plan", material, "production_contract_id", production.get("contract_id")),
        ("clip_strategy", clip, "production_contract_id", production.get("contract_id")),
        ("clip_strategy", clip, "material_plan_id", material.get("material_plan_id")),
        ("posting_package", posting, "production_contract_id", production.get("contract_id")),
        ("posting_package", posting, "clip_strategy_id", clip.get("clip_strategy_id")),
        ("posting_package", posting, "reconciliation_id", reconciliation.get("reconciliation_id")),
        ("posting_package", posting, "brain_id", brain.get("brain_id")),
    ]
    for stage, artifact, field, expected in links:
        if isinstance(artifact, Mapping) and str(artifact.get(field) or "") != str(expected or ""):
            issues.append(_issue("identity_mismatch", "critical", f"{stage}.{field} does not match its upstream identity.", stage=stage, field=field))
    return issues

def _check_provenance_chain(evidence_contract: Mapping[str, Any], brain: Mapping[str, Any], critic: Mapping[str, Any], reconciliation: Mapping[str, Any], production: Mapping[str, Any], material: Mapping[str, Any], clip: Mapping[str, Any], posting: Mapping[str, Any]) -> list[dict[str, Any]]:
    del critic
    issues: list[dict[str, Any]] = []
    valid_evidence = _verified_evidence_ids(evidence_contract, brain)
    current_source_hash = str(evidence_contract.get("source_hash") or brain.get("source_hash") or "")
    if evidence_contract.get("source_hash") and brain.get("source_hash") and evidence_contract.get("source_hash") != brain.get("source_hash"):
        issues.append(_issue("stale_source_hash", "critical", "Evidence contract and Brain source hashes differ.", stage="evidence"))
    unverified = evidence_contract.get("unverified") if isinstance(evidence_contract, Mapping) else []
    if unverified:
        issues.append(_issue("unverified_evidence", "critical", "Evidence contract contains unverified source claims.", stage="evidence", refs=[item.get("evidence_id") for item in unverified if isinstance(item, Mapping)]))
    for item in brain.get("rules") or []:
        if not isinstance(item, Mapping):
            continue
        evidence_ids = {str(x) for x in item.get("evidence_ids") or []}
        if evidence_ids and not evidence_ids.issubset(valid_evidence):
            issues.append(_issue("provenance_invalid", "critical", "Brain rule references evidence that is not verified in the current evidence contract.", stage="brain", field=str(item.get("source_rule_path") or ""), refs=sorted(evidence_ids)))
        if item.get("requirement_level") == "mandatory" and (not evidence_ids or (str(item.get("source_hash") or current_source_hash) != current_source_hash)):
            issues.append(_issue("provenance_invalid", "critical", "Mandatory Brain rule lacks complete current provenance.", stage="brain", field=str(item.get("source_rule_path") or ""), refs=sorted(evidence_ids)))
    issues.extend(_check_required_provenance("reconciliation", [item for item in reconciliation.get("rules") or [] if isinstance(item, Mapping)], valid_evidence, current_source_hash))
    production_production = production.get("production") if isinstance(production.get("production"), Mapping) else {}
    issues.extend(_check_required_provenance("production_contract", [item for item in production_production.get("requirements", []) if isinstance(item, Mapping)], valid_evidence, current_source_hash))
    for domain in ("material", "posting", "clip"):
        payload = production.get(domain) if isinstance(production.get(domain), Mapping) else {}
        items: list[Mapping[str, Any]] = []
        for key in ("requirements", "asset_requirements"):
            values = payload.get(key)
            if isinstance(values, list):
                items.extend(item for item in values if isinstance(item, Mapping))
            elif isinstance(values, Mapping):
                for value in values.values():
                    if isinstance(value, list):
                        items.extend(item for item in value if isinstance(item, Mapping))
        issues.extend(_check_required_provenance(f"production_{domain}", items, valid_evidence, current_source_hash))
    issues.extend(_check_required_provenance("material_plan", _iter_material_requirements(material), valid_evidence, current_source_hash))
    issues.extend(_check_required_provenance("clip_strategy", [item for item in clip.get("segments") or [] if isinstance(item, Mapping)], valid_evidence, current_source_hash))
    issues.extend(_check_required_provenance("posting_package", _iter_posting_package_items(posting), valid_evidence, current_source_hash))
    return issues

def _check_statuses(brain: Mapping[str, Any], critic: Mapping[str, Any], reconciliation: Mapping[str, Any], production: Mapping[str, Any], material: Mapping[str, Any], clip: Mapping[str, Any], posting: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for stage, artifact in (
        ("critic", critic), ("reconciliation", reconciliation), ("production_contract", production),
        ("material_plan", material), ("clip_strategy", clip), ("posting_package", posting),
    ):
        status = _norm_status(artifact.get("status"))
        if status == "blocked":
            issues.append(_issue("upstream_blocked", "critical", f"{stage} reports blocked status.", stage=stage))
        elif status in {"review", "unresolved"}:
            issues.append(_issue("upstream_review", "warning", f"{stage} reports review/unresolved status.", stage=stage))
        elif status and status not in _ALLOWED_STATUSES and not (stage == "reconciliation" and status == "resolved"):
            issues.append(_issue("status_invalid", "critical", f"{stage} has an unsupported status: {status}.", stage=stage))
    for source_name, artifact, collection_name in (
        ("campaign_brain", brain, "conflicts"),
        ("campaign_reconciliation", reconciliation, "conflicts"),
        ("campaign_reconciliation", reconciliation, "findings"),
    ):
        for item in artifact.get(collection_name) or []:
            if not isinstance(item, Mapping):
                continue
            severity = str(item.get("severity") or "").upper()
            state = _norm_status(item.get("status"))
            if state == "unresolved" and severity == "CRITICAL":
                issues.append(_issue("critical_unresolved", "critical", f"Unresolved critical {collection_name[:-1]} remains in {source_name}.", stage=source_name))
            elif state in {"unresolved", "open"}:
                issues.append(_issue("unresolved_issue", "warning", f"Unresolved {collection_name[:-1]} remains in {source_name}.", stage=source_name))
    return issues

def _check_requirement_preservation(brain: Mapping[str, Any], reconciliation: Mapping[str, Any], production: Mapping[str, Any], material: Mapping[str, Any], clip: Mapping[str, Any], posting: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    brain_ids = _brain_rule_ids(brain)
    recon_ids = _reconciliation_rule_ids(reconciliation)
    for rule in reconciliation.get("rules") or []:
        if not isinstance(rule, Mapping):
            continue
        refs = {str(x) for x in rule.get("brain_rule_ids") or []}
        if refs and not refs.issubset(brain_ids):
            issues.append(_issue("lineage_gap", "critical", "Reconciliation rule references a Brain rule that is absent.", stage="reconciliation", field=str(rule.get("rule_id") or ""), refs=sorted(refs)))
    production_material_ids = _production_requirement_ids(production)
    for req in _iter_material_requirements(material):
        rid = str(req.get("production_contract_requirement_id") or "")
        if rid and rid not in production_material_ids:
            issues.append(_issue("lineage_gap", "critical", "Material Plan requirement is not bound to a Production Contract material requirement.", stage="material_plan", field=str(req.get("material_requirement_id") or ""))
        provenance = req.get("provenance") if isinstance(req.get("provenance"), Mapping) else {}
        recon_rule = str(provenance.get("rule_id") or "")
        if recon_rule and recon_rule not in recon_ids:
            issues.append(_issue("lineage_gap", "critical", "Material Plan requirement references an absent reconciliation rule.", stage="material_plan", field=str(req.get("material_requirement_id") or ""), refs=[recon_rule]))
    material_ids = {str(item.get("material_requirement_id")) for item in _iter_material_requirements(material) if item.get("material_requirement_id")}
    for segment in clip.get("segments") or []:
        if not isinstance(segment, Mapping):
            continue
        rid = str(segment.get("material_requirement_id") or "")
        if rid and rid not in material_ids:
            issues.append(_issue("lineage_gap", "critical", "Clip segment references an absent Material Plan requirement.", stage="clip_strategy", field=str(segment.get("segment_id") or ""), refs=[rid]))
    expected_posting = [item for item in _iter_posting_requirements(production) if item.get("required") is True]
    actual_posting = _iter_posting_package_items(posting)
    missing = [str(expected.get("field") or "posting") for expected in expected_posting if not any(_item_matches(expected, actual) for actual in actual_posting)]
    if missing:
        issues.append(_issue("posting_requirement_lost", "critical", "One or more mandatory Production Contract posting requirements are absent or altered in the Posting Package.", stage="posting_package", field="posting", refs=sorted(missing)))
    return issues

def _check_platform_and_restrictions(production: Mapping[str, Any], material: Mapping[str, Any], clip: Mapping[str, Any], posting: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_platforms: set[str] = set()
    posting_domain = production.get("posting") if isinstance(production.get("posting"), Mapping) else {}
    for value in (posting_domain.get("platforms"), clip.get("platforms")):
        if isinstance(value, list):
            expected_platforms.update(str(x).strip().lower() for x in value if str(x).strip())
    production_domain = production.get("production") if isinstance(production.get("production"), Mapping) else {}
    for item in production_domain.get("requirements", []) or []:
        if isinstance(item, Mapping):
            expected_platforms.update(_scope(item.get("scope")).get("platforms", []))
    for item in material.get("requirements") or []:
        if isinstance(item, Mapping):
            expected_platforms.update(_scope(item.get("scope")).get("platforms", []))
    actual_platforms = {str(x).strip().lower() for x in (posting.get("platforms") or {}).keys() if str(x).strip()}
    missing_platforms = sorted(expected_platforms - actual_platforms)
    if missing_platforms:
        issues.append(_issue("platform_scope_lost", "critical", "Posting Package does not contain every platform declared upstream.", stage="posting_package", field="platforms", refs=missing_platforms))

    clip_requirements = [
        item for item in (production.get("clip", {}).get("requirements") if isinstance(production.get("clip"), Mapping) else []) or []
        if isinstance(item, Mapping)
    ]
    clip_constraints = [item for item in (clip.get("constraints") or []) if isinstance(item, Mapping)]
    for required in [item for item in clip_requirements if str(item.get("field") or "").lower() in _RESTRICTION_FIELDS]:
        if not any(
            str(check.get("field") or "").lower() == str(required.get("field") or "").lower()
            and _canonical(check.get("scope")) == _canonical(required.get("scope"))
            and _canonical(check.get("value")) == _canonical(required.get("value"))
            and _canonical(check.get("provenance")) == _canonical(required.get("provenance"))
            for check in clip_constraints
        ):
            issues.append(_issue("restriction_lost", "critical", "Declared content restriction was not preserved in Clip Strategy constraints.", stage="clip_strategy", field=str(required.get("field") or "")))
    return issues

def _check_material_readiness(material: Mapping[str, Any], clip: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if _norm_status(material.get("status")) == "blocked":
        issues.append(_issue("material_blocked", "critical", "Material Plan is blocked.", stage="material_plan"))
    assets = {
        str(item.get("asset_id") or item.get("fingerprint") or ""): item
        for item in material.get("assets") or []
        if isinstance(item, Mapping) and str(item.get("asset_id") or item.get("fingerprint") or "")
    }
    ready_states = {"verified", "acquired", "ready"}
    for segment in clip.get("segments") or []:
        if not isinstance(segment, Mapping) or _norm_status(segment.get("status")) != "selected":
            continue
        asset_id = str(segment.get("asset_fingerprint") or "")
        if not asset_id or asset_id not in assets:
            issues.append(_issue("selected_asset_missing", "critical", "Selected clip segment does not reference a known Material Plan asset.", stage="clip_strategy", field=str(segment.get("segment_id") or "")))
            continue
        if _norm_status(assets[asset_id].get("status")) not in ready_states:
            issues.append(_issue("selected_asset_not_ready", "critical", "Selected clip segment references an asset that is not execution-ready.", stage="clip_strategy", field=str(segment.get("segment_id") or "")))
    return issues

def _severity_rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "info": 2}.get(value, 3)

def compile_compliance_gate(
    campaign: Mapping[str, Any],
    evidence_contract: Mapping[str, Any],
    campaign_brain: Mapping[str, Any],
    campaign_critic: Mapping[str, Any],
    campaign_reconciliation: Mapping[str, Any],
    production_contract: Mapping[str, Any],
    material_plan: Mapping[str, Any],
    clip_strategy: Mapping[str, Any],
    posting_package: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a deterministic final compliance result without mutating inputs."""
    source = deepcopy(campaign) if isinstance(campaign, Mapping) else {}
    evidence = deepcopy(evidence_contract) if isinstance(evidence_contract, Mapping) else {}
    brain = deepcopy(campaign_brain) if isinstance(campaign_brain, Mapping) else {}
    critic = deepcopy(campaign_critic) if isinstance(campaign_critic, Mapping) else {}
    reconciliation = deepcopy(campaign_reconciliation) if isinstance(campaign_reconciliation, Mapping) else {}
    production = deepcopy(production_contract) if isinstance(production_contract, Mapping) else {}
    material = deepcopy(material_plan) if isinstance(material_plan, Mapping) else {}
    clip = deepcopy(clip_strategy) if isinstance(clip_strategy, Mapping) else {}
    posting = deepcopy(posting_package) if isinstance(posting_package, Mapping) else {}
    artifacts = {
        "evidence_contract": evidence, "campaign_brain": brain, "campaign_critic": critic,
        "campaign_reconciliation": reconciliation, "production_contract": production,
        "material_plan": material, "clip_strategy": clip, "posting_package": posting,
    }
    source_identity = {"id": str(source.get("id") or ""), "source_hash": str(source.get("source_hash") or "")}
    issues: list[dict[str, Any]] = []
    issues.extend(_check_identity_and_schema(artifacts, source_identity))
    issues.extend(_check_provenance_chain(evidence, brain, critic, reconciliation, production, material, clip, posting))
    issues.extend(_check_statuses(brain, critic, reconciliation, production, material, clip, posting))
    issues.extend(_check_requirement_preservation(brain, reconciliation, production, material, clip, posting))
    issues.extend(_check_platform_and_restrictions(production, material, clip, posting))
    issues.extend(_check_material_readiness(material, clip))
    issues = sorted(
        {str(item["issue_id"]): item for item in issues}.values(),
        key=lambda item: (_severity_rank(str(item.get("severity"))), item.get("code", ""), item.get("stage", ""), item.get("field", ""), item.get("issue_id", "")),
    )
    critical = sum(item.get("severity") == "critical" for item in issues)
    warnings = sum(item.get("severity") == "warning" for item in issues)
    status = "blocked" if critical else "review" if warnings else "ready"
    identity = {
        "campaign_id": str(source.get("id") or brain.get("campaign_id") or ""),
        "source_hash": str(evidence.get("source_hash") or brain.get("source_hash") or ""),
        "brain_id": str(brain.get("brain_id") or ""),
        "critic_id": str(critic.get("critic_id") or ""),
        "reconciliation_id": str(reconciliation.get("reconciliation_id") or ""),
        "production_contract_id": str(production.get("contract_id") or ""),
        "material_plan_id": str(material.get("material_plan_id") or ""),
        "clip_strategy_id": str(clip.get("clip_strategy_id") or ""),
        "posting_package_id": str(posting.get("posting_package_id") or ""),
    }
    checks = {
        "identity": not any(item["code"] in {"artifact_missing", "schema_invalid", "identity_mismatch", "stale_source_hash", "identity_incomplete"} for item in issues),
        "provenance": not any(item["code"] in {"provenance_invalid", "unverified_evidence", "mandatory_uncertain"} for item in issues),
        "requirements": not any(item["code"] in {"lineage_gap", "posting_requirement_lost"} for item in issues),
        "platform_scope": not any(item["code"] == "platform_scope_lost" for item in issues),
        "content_restrictions": not any(item["code"] == "restriction_lost" for item in issues),
        "material": not any(item["code"] in {"material_blocked", "selected_asset_missing", "selected_asset_not_ready"} for item in issues),
        "posting": not any(item["code"] in {"posting_requirement_lost", "platform_scope_lost"} for item in issues),
        "upstream_status": not any(item["code"] in {"upstream_blocked", "critical_unresolved", "status_invalid"} for item in issues),
    }
    result = {
        "schema_version": SCHEMA_VERSION, "compliance_gate_id": "", **identity,
        "status": status, "checks": checks, "issues": issues,
        "summary": {"check_count": len(checks), "critical_count": critical, "warning_count": warnings, "issue_count": len(issues)},
    }
    stable = {key: value for key, value in result.items() if key != "compliance_gate_id"}
    result["compliance_gate_id"] = _hash("compliance-gate-v1:", stable)
    return result

def compliance_gate_is_current(
    gate: Mapping[str, Any] | None,
    evidence_contract: Mapping[str, Any] | None,
    campaign_brain: Mapping[str, Any] | None,
    campaign_critic: Mapping[str, Any] | None,
    campaign_reconciliation: Mapping[str, Any] | None,
    production_contract: Mapping[str, Any] | None,
    material_plan: Mapping[str, Any] | None,
    clip_strategy: Mapping[str, Any] | None,
    posting_package: Mapping[str, Any] | None,
) -> bool:
    values = {
        "gate": gate, "evidence": evidence_contract, "brain": campaign_brain, "critic": campaign_critic,
        "reconciliation": campaign_reconciliation, "production": production_contract,
        "material": material_plan, "clip": clip_strategy, "posting": posting_package,
    }
    if not all(isinstance(item, Mapping) for item in values.values()):
        return False
    if gate.get("schema_version") != SCHEMA_VERSION or not gate.get("compliance_gate_id"):
        return False
    expected = compile_compliance_gate(
        {"id": gate.get("campaign_id"), "source_hash": gate.get("source_hash")},
        evidence_contract or {}, campaign_brain or {}, campaign_critic or {},
        campaign_reconciliation or {}, production_contract or {}, material_plan or {},
        clip_strategy or {}, posting_package or {},
    )
    return gate == expected

__all__ = ["SCHEMA_VERSION", "compile_compliance_gate", "compliance_gate_is_current"]
