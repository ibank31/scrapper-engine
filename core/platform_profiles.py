"""Versioned, provider-neutral platform rule profiles."""
from __future__ import annotations

import re
from typing import Any

PROFILE_VERSION = "platform-profile-v1"
PLATFORMS = ("instagram", "tiktok", "youtube")
DEFAULTS = {
    "instagram": {"caption_limit": 2200, "subtitle_delivery": "burned_in", "sound_policy": "manual_required", "schedule_capability": "channel_queue"},
    "tiktok": {"caption_limit": 2200, "subtitle_delivery": "burned_in", "sound_policy": "manual_required", "schedule_capability": "channel_queue"},
    "youtube": {"caption_limit": 5000, "subtitle_delivery": "burned_in", "sound_policy": "manual_required", "schedule_capability": "channel_queue"},
}


def _values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item.get("text") if isinstance(item, dict) else item).strip() for item in value if str(item.get("text") if isinstance(item, dict) else item).strip()]
    return [str(value).strip()] if value and str(value).strip() else []


def _platforms(detail: dict[str, Any]) -> list[str]:
    campaign = detail.get("campaign") or detail
    raw = campaign.get("socialPlatforms") or campaign.get("platforms") or []
    normalized = []
    for value in raw if isinstance(raw, list) else [raw]:
        key = re.sub(r"[^a-z]", "", str(value).lower())
        if key in {"instagram", "ig"}: key = "instagram"
        elif key in {"tiktok", "tik tok"}: key = "tiktok"
        elif key in {"youtube", "yt"}: key = "youtube"
        if key in PLATFORMS and key not in normalized: normalized.append(key)
    return normalized or list(PLATFORMS)


def build_platform_profiles(detail: dict[str, Any], production: dict[str, Any], source_of_truth: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize platform applicability without making provider calls."""
    platform_rules = production.get("platform_rules") if isinstance(production.get("platform_rules"), dict) else {}
    global_required_handles = _values(production.get("required_handles"))
    global_hashtags = _values(production.get("hashtags"))
    global_disclosures = _values(production.get("disclosures"))
    global_cta = _values(production.get("cta_urls")) + _values(production.get("cta_text"))
    global_prohibited = _values(production.get("prohibited"))
    required_phrases = []
    for item in source_of_truth.get("normalized_requirements") or []:
        if not isinstance(item, dict):
            continue
        if item.get("mandatory") and item.get("platform", "all") in ("all", None):
            required_phrases.append(str(item.get("text") or "").strip())
    result = {}
    for platform in _platforms(detail):
        override = platform_rules.get(platform) if isinstance(platform_rules.get(platform), dict) else {}
        default = DEFAULTS[platform]
        result[platform] = {
            "version": PROFILE_VERSION,
            "platform": platform,
            "required_handles": _values(override.get("required_handles", global_required_handles)),
            "suggested_handles": _values(override.get("suggested_handles")),
            "required_hashtags": _values(override.get("required_hashtags", global_hashtags)),
            "suggested_hashtags": _values(override.get("suggested_hashtags")),
            "required_disclosures": _values(override.get("required_disclosures", global_disclosures)),
            "cta": _values(override.get("cta", global_cta)),
            "required_phrases": _values(override.get("required_phrases", required_phrases)),
            "prohibited_terms": _values(override.get("prohibited_terms", global_prohibited)),
            "caption_limit": int(override.get("caption_limit", default["caption_limit"])),
            "subtitle_delivery": str(override.get("subtitle_delivery", default["subtitle_delivery"])),
            "sound_policy": str(override.get("sound_policy", default["sound_policy"])),
            "schedule_capability": str(override.get("schedule_capability", default["schedule_capability"])),
            "rule_evidence": list(source_of_truth.get("rule_evidence") or []),
        }
    return result


__all__ = ["PROFILE_VERSION", "PLATFORMS", "build_platform_profiles"]
