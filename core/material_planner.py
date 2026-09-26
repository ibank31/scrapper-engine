"""Deterministic execution planning for campaign material policies.

AI decides what a campaign requires. This module decides whether a discovered
source is permitted for a particular required asset and which provider should
be tried first. It never invents sources.
"""
from __future__ import annotations

from typing import Any, Mapping

from core.material_acquisition import normalize_material_policy

SOURCE_TYPE_ALIASES = {
    "youtube": {"youtube", "youtube_official", "public_url"},
    "google_drive": {"google_drive", "google_drive_asset", "drive_file", "drive_folder"},
    "google_drive_folder": {"google_drive_folder", "drive_folder"},
    "vimeo": {"vimeo", "public_url"},
    "direct_media": {"direct_media", "public_url"},
    "official_site": {"official_site"},
    "tracker": {"tracker"},
}

DISCOVERY_PROVIDER = {
    "explicit_url": "explicit",
    "resource_resolution": "campaign_resource",
    "drive_inventory": "google_drive",
    "named_search": "named_media",
    "official_site_search": "official_site",
    "tracker_resolution": "tracker",
    "manual": "manual",
}


def _matches_type(source_type: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    lowered = str(source_type or "").lower()
    for item in allowed:
        item_l = str(item).lower()
        if lowered == item_l:
            return True
        if lowered in SOURCE_TYPE_ALIASES.get(item_l, set()):
            return True
        if item_l in SOURCE_TYPE_ALIASES.get(lowered, set()):
            return True
    return False


def asset_policy(policy: Mapping[str, Any], asset_id: str) -> dict[str, Any] | None:
    p = normalize_material_policy(policy)
    for asset in p["required_assets"]:
        if asset["asset_id"] == str(asset_id):
            return asset
    return None


def permitted_source(policy: Mapping[str, Any], asset_id: str, source_type: str) -> tuple[bool, str]:
    asset = asset_policy(policy, asset_id)
    if not asset:
        return False, "unknown_material_asset_id"
    source = str(source_type or "").lower()
    forbidden = {str(x).lower() for x in asset["forbidden_source_types"]}
    if source in forbidden:
        return False, "source_type_forbidden"
    if not _matches_type(source, asset["allowed_source_types"]):
        return False, "source_type_not_allowed"
    return True, "allowed"


def provider_order(policy: Mapping[str, Any], asset_id: str) -> list[str]:
    asset = asset_policy(policy, asset_id)
    if not asset:
        return []
    methods = asset["discovery_methods"] or normalize_material_policy(policy)["discovery_methods"]
    preferred = [DISCOVERY_PROVIDER[m] for m in methods if m in DISCOVERY_PROVIDER]
    fallback = []
    for value in asset["fallback_sources"]:
        fallback.append(str(value))
    return list(dict.fromkeys(preferred + fallback))


def match_candidate(policy: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[str | None, str]:
    """Bind a candidate to one policy asset without guessing across identities."""
    source_type = str(candidate.get("source_type") or "")
    for asset in normalize_material_policy(policy)["required_assets"]:
        asset_id = asset["asset_id"]
        ok, reason = permitted_source(policy, asset_id, source_type)
        if not ok:
            continue
        preferred = asset["preferred_sources"]
        if preferred:
            haystack = " ".join(
                str(candidate.get(key) or "").lower()
                for key in ("source_type", "provider", "source_url", "reference_role")
            )
            if not any(str(value).lower() in haystack for value in preferred):
                continue
        return asset_id, "policy_match"
    return None, "no_policy_match"


def required_asset_minimums(policy: Mapping[str, Any]) -> dict[str, int]:
    return {
        asset["asset_id"]: int(asset["quantity"]["min"])
        for asset in normalize_material_policy(policy)["required_assets"]
        if asset.get("required", True)
    }


__all__ = [
    "DISCOVERY_PROVIDER",
    "asset_policy",
    "permitted_source",
    "provider_order",
    "match_candidate",
    "required_asset_minimums",
]
