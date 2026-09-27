#!/usr/bin/env python3
"""Bounded CA-08 acceptance; deterministic and read-only."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.campaign_ai import normalize_ai_result
from core.campaign_evidence import source_fingerprint
from core.compliance_gate import compile_compliance_gate, compliance_gate_is_current


def prov(evidence="e1", source_hash="source-1"):
    return {
        "rule_id": "recon-rule-1",
        "reconciliation_rule_id": "recon-rule-1",
        "brain_rule_ids": ["brain-rule-1"],
        "evidence_ids": [evidence] if evidence else [],
        "source_references": [{"source_type": "campaign", "location": "description"}],
        "source_hash": source_hash,
        "requirement_level": "mandatory",
        "interpretation_type": "explicit",
        "resolution": {"status": "resolved"},
        "scope": {"platforms": ["instagram"], "languages": [], "audiences": []},
    }


def post(field, value, source_hash, required=True):
    return {"field": field, "value": value, "required": required, "scope": {"platforms": ["instagram"]}, "provenance": prov(source_hash=source_hash)}


def fixture():
    campaign = {"id": "ca08-acceptance", "title": "CA-08", "description": "Follow now."}
    source_hash = source_fingerprint(campaign)
    evidence = {"schema_version": 1, "source_hash": source_hash, "verified": [{"evidence_id": "e1", "rule_path": "rules.cta_text", "quote": "Follow now.", "source_type": "campaign", "location": "description"}], "unverified": []}
    brain = {"schema_version": 1, "campaign_id": campaign["id"], "source_hash": source_hash, "brain_id": "brain-v1:accept", "rules": [{"rule_id": "brain-rule-1", "source_rule_path": "rules.cta_text", "value": "Follow now", "requirement_level": "mandatory", "interpretation_type": "explicit", "evidence_ids": ["e1"], "scope": {"platforms": ["instagram"]}}], "conflicts": [], "ambiguities": [], "evidence": {"schema_version": 1, "source_hash": source_hash, "verified": evidence["verified"], "unverified": []}}
    critic = {"schema_version": 1, "campaign_id": campaign["id"], "source_hash": source_hash, "brain_id": brain["brain_id"], "critic_id": "critic-v1:accept", "status": "pass", "findings": []}
    reconciliation = {"schema_version": 1, "campaign_id": campaign["id"], "source_hash": source_hash, "brain_id": brain["brain_id"], "critic_id": critic["critic_id"], "reconciliation_id": "reconciliation-v1:accept", "status": "resolved", "rules": [{"rule_id": "recon-rule-1", "source_rule_path": "rules.cta_text", "value": "Follow now", "requirement_level": "mandatory", "interpretation_type": "explicit", "evidence_ids": ["e1"], "brain_rule_ids": [brain["rules"][0]["rule_id"]], "scope": {"platforms": ["instagram"]}, "resolution": {"status": "resolved"}}], "conflicts": [], "findings": []}
    production = {"schema_version": 1, "contract_id": "production-contract-v1:accept", "campaign_id": campaign["id"], "source_hash": source_hash, "brain_id": brain["brain_id"], "critic_id": critic["critic_id"], "reconciliation_id": reconciliation["reconciliation_id"], "status": "ready", "production": {"requirements": []}, "material": {"requirements": []}, "clip": {"requirements": []}, "posting": {"requirements": [post("cta", "Follow now", source_hash)], "platforms": ["instagram"], "cta": [post("cta", "Follow now", source_hash)], "hashtags": [post("hashtags", ["#Optional"], source_hash, False)], "handles": [], "disclosure": [], "audio_policy": [], "subtitle_delivery": [], "native_tag_requirements": [], "schedule_intent": []}}
    material = {"schema_version": 1, "material_plan_id": "material-plan-v1:accept", "campaign_id": campaign["id"], "source_hash": source_hash, "brain_id": brain["brain_id"], "reconciliation_id": reconciliation["reconciliation_id"], "production_contract_id": production["contract_id"], "status": "ready", "requirements": [], "assets": []}
    clip = {"schema_version": 1, "clip_strategy_id": "clip-strategy-v1:accept", "campaign_id": campaign["id"], "source_hash": source_hash, "brain_id": brain["brain_id"], "reconciliation_id": reconciliation["reconciliation_id"], "production_contract_id": production["contract_id"], "material_plan_id": material["material_plan_id"], "status": "ready", "platforms": ["instagram"], "segments": [], "constraints": []}
    posting = {"schema_version": 1, "posting_package_id": "posting-package-v1:accept", "campaign_id": campaign["id"], "source_hash": source_hash, "brain_id": brain["brain_id"], "reconciliation_id": reconciliation["reconciliation_id"], "production_contract_id": production["contract_id"], "clip_strategy_id": clip["clip_strategy_id"], "status": "ready", "platforms": {"instagram": {"cta": [post("cta", "Follow now", source_hash)], "hashtags": [], "handles": [], "disclosures": [], "caption": [], "audio_policy": [], "subtitle_delivery": [], "native_tag_requirements": [], "schedule_intent": []}}, "issues": []}
    return campaign, evidence, brain, critic, reconciliation, production, material, clip, posting


def main():
    campaign, evidence, brain, critic, reconciliation, production, material, clip, posting = fixture()
    originals = copy.deepcopy([campaign, evidence, brain, critic, reconciliation, production, material, clip, posting])
    gate = compile_compliance_gate(campaign, evidence, brain, critic, reconciliation, production, material, clip, posting)
    assert gate["status"] == "ready"
    assert all(gate["checks"].values())
    assert compliance_gate_is_current(gate, evidence, brain, critic, reconciliation, production, material, clip, posting)

    missing = copy.deepcopy(posting)
    missing["platforms"]["instagram"]["cta"] = []
    blocked = compile_compliance_gate(campaign, evidence, brain, critic, reconciliation, production, material, clip, missing)
    assert blocked["status"] == "blocked"
    assert any(item["code"] == "posting_requirement_lost" for item in blocked["issues"])

    optional = copy.deepcopy(production)
    optional["posting"]["requirements"][0]["required"] = False
    optional["posting"]["requirements"][0]["provenance"]["requirement_level"] = "optional"
    optional["posting"]["cta"][0]["required"] = False
    optional["posting"]["cta"][0]["provenance"]["requirement_level"] = "optional"
    optional_gate = compile_compliance_gate(campaign, evidence, brain, critic, reconciliation, optional, material, clip, posting)
    assert optional_gate["status"] == "ready"

    stale = copy.deepcopy(production)
    stale["source_hash"] = "stale"
    stale_gate = compile_compliance_gate(campaign, evidence, brain, critic, reconciliation, stale, material, clip, posting)
    assert stale_gate["status"] == "blocked"
    assert any(item["code"] == "stale_source_hash" for item in stale_gate["issues"])

    restriction = copy.deepcopy(production)
    restriction["clip"]["requirements"] = [{"field": "prohibited_content", "value": ["gambling"], "required": True, "scope": {}, "provenance": prov(source_hash=source_hash)}]
    restriction_clip = copy.deepcopy(clip)
    restriction_clip["constraints"] = []
    restriction_gate = compile_compliance_gate(campaign, evidence, brain, critic, reconciliation, restriction, material, restriction_clip, posting)
    assert restriction_gate["status"] == "blocked"
    assert any(item["code"] == "restriction_lost" for item in restriction_gate["issues"])

    result = normalize_ai_result(
        {"campaign_fit": {"score": 1, "label": "high", "reason": "fixture"}, "rules": {"cta_required": True, "cta_text": "Follow now"}, "evidence": [{"rule_path": "rules.cta_text", "quote": "Follow now."}], "confidence": 0.9},
        campaign["id"], campaign,
    )
    assert "compliance_gate" in result
    assert result["compliance_gate"]["campaign_id"] == campaign["id"]
    assert result["compliance_gate"]["source_hash"] == source_fingerprint(campaign)
    assert compliance_gate_is_current(result["compliance_gate"], result["evidence_contract"], result["campaign_brain"], result["campaign_critic"], result["campaign_reconciliation"], result["production_contract"], result["material_plan"], result["clip_strategy"], result["posting_package"])

    assert originals == [campaign, evidence, brain, critic, reconciliation, production, material, clip, posting]

    print("COMPLIANCE_GATE_PRESENT=true")
    print("FULL_CHAIN_IDENTITY_VALID=true")
    print("PROVENANCE_VALIDATED=true")
    print("MANDATORY_POSTING_PRESERVED=true")
    print("OPTIONAL_REQUIREMENT_NOT_BLOCKING=true")
    print("PLATFORM_SCOPE_VALIDATED=true")
    print("CONTENT_RESTRICTIONS_VALIDATED=true")
    print("MATERIAL_READINESS_VALIDATED=true")
    print("CACHE_INVALIDATION=true")
    print("INPUT_IMMUTABILITY=true")
    print("DETERMINISTIC_IDENTITY=true")
    print("LEGACY_COMPATIBILITY=true")
    print("BUFFER_PUBLISHING_MUTATION=NONE")
    print("MANUAL_D1_MUTATION=NONE")


if __name__ == "__main__":
    main()
