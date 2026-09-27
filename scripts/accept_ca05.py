#!/usr/bin/env python3
"""Bounded CA-05 acceptance; no provider, Buffer, or D1 mutation."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.campaign_ai import normalize_ai_result
from core.campaign_evidence import source_fingerprint
from core.material_intelligence import compile_material_plan, material_plan_is_current


def main() -> None:
    campaign = {
        "id": "ca05-acceptance-fixture",
        "description": "Use official campaign footage and an approved logo. Instagram requires the campaign footage.",
        "requirements": [{"text": "Use official campaign footage.", "isMandatory": True}],
        "platforms": ["Instagram"],
    }
    ai_item = {
        "campaign_fit": {"score": 1, "label": "high", "reason": "matches"},
        "rules": {
            "asset_sources": ["official campaign footage"],
            "subtitle_required": True,
            "platforms": ["Instagram"],
        },
        "rule_annotations": [{
            "rule_path": "rules.asset_sources", "value": "official campaign footage",
            "requirement_level": "mandatory", "interpretation_type": "explicit",
            "scope": {"platforms": ["Instagram"], "languages": [], "audiences": []},
        }],
        "evidence": [{"rule_path": "rules.asset_sources", "quote": "Use official campaign footage."}],
        "confidence": 0.95,
    }
    normalized = normalize_ai_result(ai_item, campaign["id"], campaign)
    envelope = json.loads(json.dumps(normalized, ensure_ascii=False, sort_keys=True))
    contract = envelope["production_contract"]
    initial_plan = envelope["material_plan"]
    assert initial_plan["material_plan_id"]
    assert material_plan_is_current(initial_plan, contract)
    assert initial_plan["status"] == "blocked"
    mandatory = [item for item in initial_plan["requirements"] if item["required"] is True]
    assert mandatory and all(item["provenance"]["evidence_ids"] for item in mandatory)
    requirement_id = mandatory[0]["material_requirement_id"]
    candidate = {
        "material_requirement_id": requirement_id,
        "source_url": "https://campaign.example/official-footage.mp4",
        "source_type": "provided_asset",
        "status": "verified",
        "content_hash": "sha256:ca05-fixture",
        "scope": {"platforms": ["Instagram"], "languages": [], "audiences": []},
    }
    ready_plan = compile_material_plan(contract, [candidate])
    assert ready_plan["status"] == "ready"
    assert ready_plan["assets"][0]["status"] == "verified"
    assert ready_plan["assets"][0]["source_url"].startswith("https://")
    assert ready_plan["requirements"][0]["provenance"]["evidence_ids"]
    assert json.loads(json.dumps(ready_plan, sort_keys=True)) == ready_plan

    fallback_plan = compile_material_plan({**contract, "material": {**contract["material"], "fallback_assets": ["approved alternate footage"]}})
    assert fallback_plan["fallbacks"] and fallback_plan["fallbacks"][0]["authorized"] is True
    assert fallback_plan["status"] == "blocked"

    changed_contract = copy.deepcopy(contract)
    changed_contract["source_hash"] = "changed-source-hash"
    assert not material_plan_is_current(initial_plan, changed_contract)
    assert not material_plan_is_current(initial_plan, {**contract, "contract_id": "production-contract-v1:changed"})
    assert envelope["rules"]
    assert envelope["campaign_id"] == campaign["id"]
    assert envelope["source_hash"] == source_fingerprint(campaign)

    print("MATERIAL_PLAN_PRESENT=true")
    print(f"MATERIAL_PLAN_ID={initial_plan['material_plan_id']}")
    print(f"CAMPAIGN_ID={initial_plan['campaign_id']}")
    print(f"SOURCE_HASH={initial_plan['source_hash']}")
    print(f"BRAIN_ID={initial_plan['brain_id']}")
    print(f"RECONCILIATION_ID={initial_plan['reconciliation_id']}")
    print(f"PRODUCTION_CONTRACT_ID={initial_plan['production_contract_id']}")
    print(f"INITIAL_STATUS={initial_plan['status']}")
    print(f"READY_STATUS={ready_plan['status']}")
    print(f"MANDATORY_REQUIREMENTS={len(mandatory)}")
    print(f"ASSETS_AFTER_VERIFIED_CANDIDATE={len(ready_plan['assets'])}")
    print(f"PROVENANCE_COVERAGE={sum(bool(item['provenance']['evidence_ids']) for item in initial_plan['requirements']) / max(1, len(initial_plan['requirements'])):.1f}")
    print("LEGACY_RULES_COMPATIBILITY=true")
    print("BUFFER_PUBLISHING_MUTATION=NONE")
    print("MANUAL_D1_MUTATION=NONE")


if __name__ == "__main__":
    main()
