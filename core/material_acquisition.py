"""Campaign material acquisition contracts and deterministic validation.

The AI may propose a campaign-specific acquisition plan, but this module owns
the executable contract: explicit source roles, discovery methods, verification,
fallbacks, and safe/manual stop states.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA_VERSION = 1
VALID_STATUS = {"resolved", "accessible", "unresolved", "manual_required"}
VALID_SOURCE_ROLES = {
    "provided_asset", "drive_folder", "drive_file", "public_url",
    "named_media", "official_site", "tracker", "reference_only", "manual",
}
VALID_DISCOVERY_METHODS = {
    "explicit_url", "resource_resolution", "drive_inventory",
    "named_search", "official_site_search", "tracker_resolution", "manual",
}


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_material_policy(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    policy = policy if isinstance(policy, Mapping) else {}
    assets = policy.get("required_assets") if isinstance(policy.get("required_assets"), list) else []
    normalized_assets: list[dict[str, Any]] = []
    for index, raw in enumerate(assets, 1):
        if not isinstance(raw, Mapping):
            continue
        identity = raw.get("identity") if isinstance(raw.get("identity"), Mapping) else {}
        quantity = raw.get("quantity") if isinstance(raw.get("quantity"), Mapping) else {}
        verification = raw.get("verification") if isinstance(raw.get("verification"), Mapping) else {}
        normalized_assets.append({
            "asset_id": str(raw.get("asset_id") or f"asset_{index}"),
            "intent": str(raw.get("intent") or "campaign_required_material"),
            "required": bool(raw.get("required", True)),
            "quantity": {
                "min": max(0, int(quantity.get("min", 1) or 0)),
                "max": max(0, int(quantity.get("max", quantity.get("min", 1)) or 0)),
            },
            "preferred_sources": _clean_list(raw.get("preferred_sources")),
            "fallback_sources": _clean_list(raw.get("fallback_sources")),
            "allowed_source_types": _clean_list(raw.get("allowed_source_types")),
            "forbidden_source_types": _clean_list(raw.get("forbidden_source_types")),
            "identity": {str(k): str(v) for k, v in identity.items() if v not in (None, "")},
            "verification": dict(verification),
            "discovery_methods": _clean_list(raw.get("discovery_methods")),
            "evidence": raw.get("evidence") if isinstance(raw.get("evidence"), list) else [],
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "acquisition_mode": str(policy.get("acquisition_mode") or "campaign_defined"),
        "required_assets": normalized_assets,
        "source_hierarchy": _clean_list(policy.get("source_hierarchy")),
        "allowed_providers": _clean_list(policy.get("allowed_providers")),
        "discovery_methods": [
            x for x in _clean_list(policy.get("discovery_methods"))
            if x in VALID_DISCOVERY_METHODS
        ],
        "verification_policy": dict(policy.get("verification_policy") or {}) if isinstance(policy.get("verification_policy"), Mapping) else {},
        "fallback_policy": dict(policy.get("fallback_policy") or {}) if isinstance(policy.get("fallback_policy"), Mapping) else {},
        "exclusions": _clean_list(policy.get("exclusions")),
        "manual_escalation": dict(policy.get("manual_escalation") or {}) if isinstance(policy.get("manual_escalation"), Mapping) else {},
    }


def validate_material_policy(policy: Mapping[str, Any] | None) -> list[str]:
    p = normalize_material_policy(policy)
    errors: list[str] = []
    if not p["required_assets"]:
        errors.append("No required material intents were produced.")
    for asset in p["required_assets"]:
        if asset["quantity"]["max"] < asset["quantity"]["min"]:
            errors.append(f'{asset["asset_id"]}: quantity.max < quantity.min')
        methods = asset["discovery_methods"] or p["discovery_methods"]
        invalid_methods = [m for m in methods if m not in VALID_DISCOVERY_METHODS]
        if invalid_methods:
            errors.append(f'{asset["asset_id"]}: invalid discovery method(s): {invalid_methods}')
        if not methods:
            errors.append(f'{asset["asset_id"]}: no discovery method')
        forbidden = set(asset["forbidden_source_types"])
        allowed = set(asset["allowed_source_types"])
        if forbidden & allowed:
            errors.append(f'{asset["asset_id"]}: source type both allowed and forbidden')
        if asset["required"] and asset["quantity"]["min"] < 1:
            errors.append(f'{asset["asset_id"]}: required asset must have quantity.min >= 1')
    return errors


def material_plan_fingerprint(policy: Mapping[str, Any] | None) -> str:
    return _stable_hash(normalize_material_policy(policy))


def build_legacy_compatible_policy(campaign: Mapping[str, Any]) -> dict[str, Any]:
    """Build a conservative policy for old campaigns before AI re-analysis.

    Existing explicit URLs/resources are treated as authoritative candidates,
    never as proof that an arbitrary public source is acceptable.
    """
    resources = campaign.get("resources") if isinstance(campaign.get("resources"), list) else []
    urls = []
    for item in resources:
        if isinstance(item, Mapping) and item.get("url"):
            urls.append(str(item["url"]))
    for value in campaign.get("source_urls") or campaign.get("asset_urls") or []:
        if value:
            urls.append(str(value))
    urls = list(dict.fromkeys(urls))
    source_role = "provided_asset" if urls else "manual"
    return normalize_material_policy({
        "acquisition_mode": "legacy_conservative",
        "required_assets": [{
            "asset_id": "legacy_campaign_material",
            "intent": "Use campaign-provided material only",
            "required": True,
            "quantity": {"min": 1, "max": 9999},
            "preferred_sources": urls,
            "allowed_source_types": [source_role],
            "forbidden_source_types": ["unknown_public_source", "fan_upload", "reupload"],
            "discovery_methods": ["explicit_url", "resource_resolution"] if urls else ["manual"],
            "verification": {"explicit_campaign_reference_required": True},
            "evidence": [{"rule_path": "legacy.resources", "quote": str(urls)[:500]}],
        }],
        "source_hierarchy": ["campaign_explicit_resource", "manual"],
        "discovery_methods": ["explicit_url", "resource_resolution"] if urls else ["manual"],
        "exclusions": ["unverified public reuploads", "fan uploads", "reference-only links"],
        "manual_escalation": {"on_unresolved": True},
    })


def acquisition_status(results: list[Mapping[str, Any]], policy: Mapping[str, Any]) -> str:
    """Aggregate source state without silently treating partial acquisition as success."""
    p = normalize_material_policy(policy)
    if not results:
        return "unresolved"
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for row in results:
        by_id.setdefault(str(row.get("asset_id") or ""), []).append(row)
    for asset in p["required_assets"]:
        rows = by_id.get(asset["asset_id"], [])
        verified = sum(1 for row in rows if str(row.get("status")) == "accessible")
        if verified < asset["quantity"]["min"]:
            if any(str(row.get("status")) == "manual_required" for row in rows):
                return "manual_required"
            return "unresolved"
    return "accessible"


__all__ = [
    "SCHEMA_VERSION", "VALID_STATUS", "VALID_SOURCE_ROLES",
    "VALID_DISCOVERY_METHODS", "normalize_material_policy",
    "validate_material_policy", "material_plan_fingerprint",
    "build_legacy_compatible_policy", "acquisition_status",
]
