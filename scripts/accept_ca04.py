#!/usr/bin/env python3
"""Bounded CA-04 acceptance; no provider, Buffer, or D1 mutation."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.campaign_ai import normalize_ai_result
from core.campaign_evidence import source_fingerprint


def main() -> None:
    campaign = {
        "id": "ca04-acceptance-fixture",
        "description": "Use 15 to 60 seconds. Include subtitles. Instagram uses @brand_ig and #ExactTag. TikTok uses @brand_tt. CTA: Follow now.",
        "requirements": [
            {"text": "Use 15 to 60 seconds.", "isMandatory": True},
            {"text": "Include subtitles.", "isMandatory": True},
        ],
    }
    item = {
        "campaign_fit": {"score": 1, "label": "high", "reason": "bounded CA-04 fixture"},
        "rules": {
            "min_duration_seconds": 15, "max_duration_seconds": 60,
            "subtitle_required": True, "cta_required": True, "cta_text": "Follow now",
            "handles": ["@brand_ig", "@brand_tt"], "hashtags": ["#ExactTag"],
            "platform_rules": {"instagram": {"handle": "@brand_ig"}, "tiktok": {"handle": "@brand_tt"}},
        },
        "rule_annotations": [
            {"rule_path": "rules.handles", "value": ["@brand_ig"], "requirement_level": "mandatory", "interpretation_type": "explicit", "scope": {"platforms": ["instagram"]}},
            {"rule_path": "rules.handles", "value": ["@brand_tt"], "requirement_level": "mandatory", "interpretation_type": "explicit", "scope": {"platforms": ["tiktok"]}},
        ],
        "evidence": [
            {"rule_path": "rules.min_duration_seconds", "quote": "Use 15 to 60 seconds."},
            {"rule_path": "rules.subtitle_required", "quote": "Include subtitles."},
            {"rule_path": "rules.handles", "quote": "Instagram uses @brand_ig"},
            {"rule_path": "rules.handles", "quote": "TikTok uses @brand_tt"},
            {"rule_path": "rules.hashtags", "quote": "#ExactTag"},
            {"rule_path": "rules.cta_text", "quote": "CTA: Follow now."},
        ],
        "confidence": 0.95,
    }
    before = copy.deepcopy((campaign, item))
    normalized = normalize_ai_result(item, campaign["id"], campaign)
    contract = normalized["production_contract"]
    persisted = json.loads(json.dumps(normalized, ensure_ascii=False, sort_keys=True))
    assert persisted["production_contract"]["contract_id"] == contract["contract_id"]
    assert contract["campaign_id"] == campaign["id"]
    assert contract["source_hash"] == source_fingerprint(campaign)
    assert contract["brain_id"] == normalized["campaign_brain"]["brain_id"]
    assert contract["critic_id"] == normalized["campaign_critic"]["critic_id"]
    assert contract["reconciliation_id"] == normalized["campaign_reconciliation"]["reconciliation_id"]
    assert contract["status"] in {"ready", "review"}
    assert contract["production"]["requirements"]
    assert "material" in contract and "clip" in contract and "posting" in contract and "compliance" in contract
    def has_evidence(item):
        provenance = item.get("provenance")
        values = provenance if isinstance(provenance, list) else [provenance]
        return any(isinstance(entry, dict) and entry.get("evidence_ids") for entry in values)
    assert all(has_evidence(item) for item in contract["production"]["requirements"] if item.get("required") is True)
    assert "rules" in persisted  # legacy projection remains available
    assert (campaign, item) == before

    print("CONTRACT_PRESENT=true")
    for key in ("contract_id", "campaign_id", "source_hash", "brain_id", "critic_id", "reconciliation_id"):
        print(f"{key.upper()}={contract[key]}")
    print(f"CONTRACT_STATUS={contract['status']}")
    for key in ("production", "material", "clip", "posting", "compliance"):
        print(f"{key.upper()}_CONTRACT=" + json.dumps(contract[key], ensure_ascii=False, sort_keys=True))
    print(f"MANDATORY_REQUIREMENTS={contract['summary']['mandatory_requirements']}")
    print(f"UNRESOLVED_REQUIREMENTS={contract['summary']['unresolved_requirements']}")
    print("ISSUES=" + json.dumps(contract["issues"], ensure_ascii=False, sort_keys=True))
    print("EVIDENCE_COVERAGE=" + str(normalized["evidence_contract"]["coverage"]))
    print("UNVERIFIED_EVIDENCE=" + str(len(normalized["evidence_contract"]["unverified"])))
    print("LEGACY_RULES_COMPATIBILITY=true")
    print("BUFFER_PUBLISHING_MUTATION=NONE")
    print("MANUAL_D1_MUTATION=NONE")


if __name__ == "__main__":
    main()
