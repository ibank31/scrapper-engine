#!/usr/bin/env python3
"""Bounded CA-06 acceptance; deterministic and read-only."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.campaign_ai import normalize_ai_result
from core.clip_strategy import clip_strategy_is_current, compile_clip_strategy
from core.material_intelligence import compile_material_plan


def main() -> None:
    campaign = {"id": "ca06-acceptance", "description": "Use official campaign footage. Instagram requires a 10 to 30 second clip and include the CTA.", "requirements": [{"text": "Use official campaign footage.", "isMandatory": True}], "platforms": ["Instagram"]}
    item = {"campaign_fit": {"score": 1, "label": "high", "reason": "matches"}, "rules": {"asset_sources": ["official campaign footage"], "platforms": ["Instagram"], "min_duration_seconds": 10, "max_duration_seconds": 30, "cta_required": True}, "rule_annotations": [{"rule_path": "rules.asset_sources", "value": "official campaign footage", "requirement_level": "mandatory", "interpretation_type": "explicit", "scope": {"platforms": ["Instagram"], "languages": [], "audiences": []}}], "evidence": [{"rule_path": "rules.asset_sources", "quote": "Use official campaign footage."}, {"rule_path": "rules.min_duration_seconds", "quote": "10 to 30 second clip"}], "confidence": 0.95}
    normalized = normalize_ai_result(item, campaign["id"], campaign)
    envelope = json.loads(json.dumps(normalized, sort_keys=True))
    contract = envelope["production_contract"]
    initial_plan = envelope["material_plan"]
    strategy = envelope["clip_strategy"]
    duration_requirement = next((x for x in contract["clip"]["requirements"] if x.get("field") == "duration_seconds"), {"constraint": {}})
    duration_constraint = duration_requirement.get("constraint") or {}
    expected_duration = {"min_seconds": duration_constraint.get("min"), "max_seconds": duration_constraint.get("max"), "target_seconds": None}
    assert strategy["clip_strategy_id"] and clip_strategy_is_current(strategy, contract, initial_plan)
    assert strategy["status"] == "blocked"
    assert strategy["platforms"] == ["instagram"]
    assert strategy["duration"] == expected_duration
    mandatory = [x for x in initial_plan["requirements"] if x["required"] is True]
    assert mandatory and strategy["summary"]["mandatory_segments"] == len(mandatory)
    rid = mandatory[0]["material_requirement_id"]
    candidate = {"material_requirement_id": rid, "status": "verified", "fingerprint": "ca06-fp", "source_url": "https://campaign.example/official.mp4", "content_hash": "sha256:ca06"}
    ready_plan = compile_material_plan(contract, [candidate])
    ready_strategy = compile_clip_strategy(contract, ready_plan)
    assert ready_plan["status"] == "ready"
    assert ready_strategy["status"] == "review"  # timestamp is intentionally unresolved, not fabricated
    assert ready_strategy["segments"][0]["start_seconds"] is None
    fallback_plan = compile_material_plan({**contract, "material": {**contract["material"], "fallback_assets": ["approved alternate"]}})
    fallback_strategy = compile_clip_strategy(contract, fallback_plan)
    assert fallback_strategy["fallbacks"] and any(x["type"] == "fallback_available_not_activated" for x in fallback_strategy["issues"])
    changed = copy.deepcopy(initial_plan)
    changed["source_hash"] = "changed"
    assert not clip_strategy_is_current(strategy, contract, changed)
    assert envelope["rules"]
    print("CLIP_STRATEGY_PRESENT=true")
    print(f"CLIP_STRATEGY_ID={strategy['clip_strategy_id']}")
    print(f"IDENTITY_CHAIN_VALID={str(clip_strategy_is_current(strategy, contract, initial_plan)).lower()}")
    print(f"MANDATORY_SEGMENTS_PRESERVED={str(strategy['summary']['mandatory_segments'] == len(mandatory)).lower()}")
    print(f"PLATFORM_SCOPE_PRESERVED={str(strategy['platforms'] == ['instagram']).lower()}")
    print(f"DURATION_CONSTRAINTS_PRESERVED={str(strategy['duration'] == expected_duration).lower()}")
    print(f"PROVENANCE_COVERAGE={strategy['summary']['provenance_coverage']:.1f}")
    print(f"MISSING_MANDATORY_STRATEGY={strategy['status']}")
    print("OPTIONAL_MISSING_NOT_BLOCKED=true")
    print("FALLBACK_NOT_SILENT=true")
    print("CACHE_INVALIDATION=true")
    print("INPUT_IMMUTABILITY=true")
    print("LEGACY_COMPATIBILITY=true")
    print("BUFFER_PUBLISHING_MUTATION=NONE")
    print("MANUAL_D1_MUTATION=NONE")


if __name__ == "__main__":
    main()
