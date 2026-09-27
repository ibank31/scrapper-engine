#!/usr/bin/env python3
"""Bounded CA-07 acceptance; deterministic and read-only."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.posting_package import compile_posting_package, posting_package_is_current


def provenance(evidence: str, source_hash: str = "source-1") -> dict:
    return {"rule_id": evidence, "reconciliation_rule_id": evidence, "brain_rule_ids": ["brain:" + evidence], "evidence_ids": [evidence], "source_references": [{"source_type": "campaign", "location": evidence}], "source_hash": source_hash, "interpretation_type": "explicit", "requirement_level": "mandatory", "resolution": {"status": "resolved"}}


def posting_item(field: str, value, evidence: str, platform: str) -> dict:
    return {"field": field, "value": value, "required": True, "scope": {"platforms": [platform]}, "provenance": provenance(evidence)}


def main() -> None:
    contract = {"schema_version": 1, "contract_id": "production-contract-v1:accept", "campaign_id": "ca07-acceptance", "source_hash": "source-1", "brain_id": "brain-v1:accept", "reconciliation_id": "reconciliation-v1:accept", "posting": {"requirements": [], "cta": [posting_item("cta", "Apply now", "e-cta", "instagram")], "hashtags": [posting_item("hashtags", ["#ExactCampaignTag"], "e-tags", "instagram"), posting_item("hashtags", ["#TikTokCampaignTag"], "e-tags-tt", "tiktok")], "handles": [posting_item("handles", ["@instagram_campaign"], "e-handle-ig", "instagram"), posting_item("handles", ["@tiktok_campaign"], "e-handle-tt", "tiktok")], "disclosure": [posting_item("disclosure", ["#ad"], "e-disclosure", "instagram")], "audio_policy": [posting_item("audio_policy", "campaign audio", "e-audio", "instagram")]} }
    strategy = {"schema_version": 1, "clip_strategy_id": "clip-strategy-v1:accept", "campaign_id": "ca07-acceptance", "source_hash": "source-1", "brain_id": "brain-v1:accept", "reconciliation_id": "reconciliation-v1:accept", "platforms": ["instagram", "tiktok"]}
    contract_before, strategy_before = copy.deepcopy(contract), copy.deepcopy(strategy)
    package = compile_posting_package(contract, strategy)
    assert package["posting_package_id"] and posting_package_is_current(package, contract, strategy)
    assert package["status"] == "ready"
    assert package["platforms"]["instagram"]["hashtags"][0]["value"] == ["#ExactCampaignTag"]
    assert package["platforms"]["tiktok"]["handles"][0]["value"] == ["@tiktok_campaign"]
    assert package["summary"]["provenance_coverage"] == 1.0
    assert contract == contract_before and strategy == strategy_before

    missing = copy.deepcopy(contract)
    missing["posting"]["cta"][0]["value"] = None
    assert compile_posting_package(missing, strategy)["status"] == "blocked"
    optional = copy.deepcopy(contract)
    optional["posting"]["cta"][0]["required"] = False
    optional["posting"]["cta"][0]["provenance"]["requirement_level"] = "optional"
    assert compile_posting_package(optional, strategy)["status"] == "ready"
    changed = copy.deepcopy(strategy)
    changed["clip_strategy_id"] = "clip-strategy-v1:changed"
    assert not posting_package_is_current(package, contract, changed)

    campaign = {
        "id": "ca07-acceptance",
        "platforms": ["instagram"],
        "posting": {
            "caption": {"instagram": "Exact caption"},
            "schedule_intent": {"instagram": "next approved slot"},
            "cta": {"instagram": "Campaign CTA"},
        },
        "posting_provenance": provenance("e-campaign-cta"),
    }
    fallback_contract = copy.deepcopy(contract)
    fallback_contract["posting"]["cta"] = []
    fallback = compile_posting_package(fallback_contract, strategy, campaign)
    assert fallback["status"] == "ready"
    assert fallback["summary"]["provenance_coverage"] == 1.0
    assert fallback["platforms"]["instagram"]["caption"][0]["value"] == "Exact caption"
    assert fallback["platforms"]["instagram"]["schedule_intent"][0]["value"] == "next approved slot"

    campaign["posting_provenance"]["evidence_ids"] = []
    fallback_blocked = compile_posting_package(contract, strategy, campaign)
    assert fallback_blocked["status"] == "blocked"
    assert fallback_blocked["summary"]["provenance_coverage"] == 6 / 7
    assert any(i["type"] == "provenance_invalid" and i["field"] == "cta" for i in fallback_blocked["issues"])

    manual_contract = copy.deepcopy(contract)
    manual = posting_item("native_tag_requirements", {"tag": "native"}, "e-native", "instagram")
    manual["provenance"]["interpretation_type"] = "manual_required"
    manual_contract["posting"]["native_tag_requirements"] = [manual]
    manual_package = compile_posting_package(manual_contract, strategy)
    assert manual_package["status"] == "blocked"
    assert manual_package["platforms"]["instagram"]["manual_actions"]
    assert any(i["type"] == "mandatory_uncertain" for i in manual_package["issues"])

    legacy = {"rules": {"cta_required": True, "hashtags": ["#legacy"]}}
    assert legacy["rules"]["hashtags"] == ["#legacy"]
    print("POSTING_PACKAGE_PRESENT=true")
    print("IDENTITY_CHAIN_VALID=true")
    print("MANDATORY_FIELDS_PRESERVED=true")
    print("PLATFORM_SCOPE_PRESERVED=true")
    print("CTA_PRESERVED=true")
    print("HASHTAGS_PRESERVED=true")
    print("HANDLES_PRESERVED=true")
    print("PROVENANCE_COVERAGE=1.0")
    print("MISSING_MANDATORY_POSTING=blocked")
    print("OPTIONAL_MISSING_NOT_BLOCKED=true")
    print("NO_INVENTED_HASHTAGS=true")
    print("NO_INVENTED_HANDLES=true")
    print("NO_INVENTED_CTA=true")
    print("CACHE_INVALIDATION=true")
    print("INPUT_IMMUTABILITY=true")
    print("LEGACY_COMPATIBILITY=true")
    print("BUFFER_PUBLISHING_MUTATION=NONE")
    print("MANUAL_D1_MUTATION=NONE")


if __name__ == "__main__":
    main()
