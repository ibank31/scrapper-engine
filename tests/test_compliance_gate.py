import copy
import unittest

from core.campaign_ai import normalize_ai_result
from core.campaign_evidence import source_fingerprint
from core.compliance_gate import compile_compliance_gate, compliance_gate_is_current


def prov(evidence="e1", source_hash=""):
    return {
        "rule_id": "recon-rule-1",
        "reconciliation_rule_id": "recon-rule-1",
        "brain_rule_ids": ["brain-rule-1"],
        "evidence_ids": [evidence] if evidence else [],
        "source_references": [{"source_type": "campaign", "location": "requirements[0]"}],
        "source_hash": source_hash,
        "requirement_level": "mandatory",
        "interpretation_type": "explicit",
        "resolution": {"status": "resolved"},
        "scope": {"platforms": ["instagram"], "languages": [], "audiences": []},
    }


def posting_item(field="cta", value="Follow now", required=True, scope=None, evidence="e1", source_hash=""):
    return {
        "field": field,
        "value": value,
        "required": required,
        "scope": scope or {"platforms": ["instagram"], "languages": [], "audiences": []},
        "provenance": prov(evidence, source_hash),
    }


class ComplianceGateTests(unittest.TestCase):
    def setUp(self):
        self.campaign = {
            "id": "campaign-1",
            "title": "Compliance fixture",
            "description": "Follow now.",
        }
        self.source_hash = source_fingerprint(self.campaign)
        self.evidence = {
            "schema_version": 1,
            "source_hash": self.source_hash,
            "verified": [{
                "evidence_id": "e1",
                "rule_path": "rules.cta_text",
                "quote": "Follow now.",
                "source_type": "campaign",
                "location": "description",
            }],
            "unverified": [],
        }
        self.brain = {
            "schema_version": 1,
            "campaign_id": "campaign-1",
            "source_hash": self.source_hash,
            "brain_id": "brain-v1:test",
            "rules": [{
                "rule_id": "brain-rule-1",
                "source_rule_path": "rules.cta_text",
                "value": "Follow now",
                "requirement_level": "mandatory",
                "interpretation_type": "explicit",
                "evidence_ids": ["e1"],
                "source_references": [{"source_type": "campaign", "location": "description"}],
                "scope": {"platforms": ["instagram"], "languages": [], "audiences": []},
            }],
            "conflicts": [],
            "ambiguities": [],
            "evidence": {"schema_version": 1, "source_hash": self.source_hash, "verified": self.evidence["verified"], "unverified": []},
        }
        self.critic = {
            "schema_version": 1,
            "campaign_id": "campaign-1",
            "source_hash": self.source_hash,
            "brain_id": "brain-v1:test",
            "critic_id": "critic-v1:test",
            "status": "pass",
            "findings": [],
        }
        self.reconciliation = {
            "schema_version": 1,
            "campaign_id": "campaign-1",
            "source_hash": self.source_hash,
            "brain_id": "brain-v1:test",
            "critic_id": "critic-v1:test",
            "reconciliation_id": "reconciliation-v1:test",
            "status": "resolved",
            "rules": [{
                "rule_id": "recon-rule-1",
                "source_rule_path": "rules.cta_text",
                "value": "Follow now",
                "requirement_level": "mandatory",
                "interpretation_type": "explicit",
                "evidence_ids": ["e1"],
                "brain_rule_ids": ["brain-rule-1"],
                "source_references": [{"source_type": "campaign", "location": "description"}],
                "scope": {"platforms": ["instagram"], "languages": [], "audiences": []},
                "resolution": {"status": "resolved"},
            }],
            "conflicts": [],
            "findings": [],
        }
        self.production = {
            "schema_version": 1,
            "contract_id": "production-contract-v1:test",
            "campaign_id": "campaign-1",
            "source_hash": self.source_hash,
            "brain_id": "brain-v1:test",
            "critic_id": "critic-v1:test",
            "reconciliation_id": "reconciliation-v1:test",
            "status": "ready",
            "production": {"requirements": []},
            "material": {"requirements": []},
            "clip": {"requirements": []},
            "posting": {
                "requirements": [posting_item()],
                "platforms": ["instagram"],
                "cta": [posting_item()],
                "hashtags": [posting_item("hashtags", ["#Optional"], False)],
                "handles": [],
                "disclosure": [],
                "audio_policy": [],
                "subtitle_delivery": [],
                "native_tag_requirements": [],
                "schedule_intent": [],
            },
        }
        self.material = {
            "schema_version": 1,
            "material_plan_id": "material-plan-v1:test",
            "campaign_id": "campaign-1",
            "source_hash": self.source_hash,
            "brain_id": "brain-v1:test",
            "reconciliation_id": "reconciliation-v1:test",
            "production_contract_id": "production-contract-v1:test",
            "status": "ready",
            "requirements": [],
            "assets": [],
        }
        self.clip = {
            "schema_version": 1,
            "clip_strategy_id": "clip-strategy-v1:test",
            "campaign_id": "campaign-1",
            "source_hash": self.source_hash,
            "brain_id": "brain-v1:test",
            "reconciliation_id": "reconciliation-v1:test",
            "production_contract_id": "production-contract-v1:test",
            "material_plan_id": "material-plan-v1:test",
            "status": "ready",
            "platforms": ["instagram"],
            "segments": [],
            "constraints": [],
        }
        self.posting = {
            "schema_version": 1,
            "posting_package_id": "posting-package-v1:test",
            "campaign_id": "campaign-1",
            "source_hash": self.source_hash,
            "brain_id": "brain-v1:test",
            "reconciliation_id": "reconciliation-v1:test",
            "production_contract_id": "production-contract-v1:test",
            "clip_strategy_id": "clip-strategy-v1:test",
            "status": "ready",
            "platforms": {
                "instagram": {
                    "cta": [posting_item()],
                    "hashtags": [],
                    "handles": [],
                    "disclosures": [],
                    "caption": [],
                    "audio_policy": [],
                    "subtitle_delivery": [],
                    "native_tag_requirements": [],
                    "schedule_intent": [],
                }
            },
            "issues": [],
        }

    def gate(self):
        return compile_compliance_gate(
            self.campaign, self.evidence, self.brain, self.critic,
            self.reconciliation, self.production, self.material, self.clip, self.posting,
        )

    def test_valid_chain_is_ready_and_current(self):
        gate = self.gate()
        self.assertEqual(gate["status"], "ready", gate["issues"])
        self.assertTrue(all(gate["checks"].values()), gate["issues"])
        self.assertTrue(gate["compliance_gate_id"].startswith("compliance-gate-v1:"))
        self.assertTrue(compliance_gate_is_current(
            gate, self.evidence, self.brain, self.critic, self.reconciliation,
            self.production, self.material, self.clip, self.posting,
        ))

    def test_identity_mismatch_blocks(self):
        posting = copy.deepcopy(self.posting)
        posting["clip_strategy_id"] = "clip-strategy-v1:stale"
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, self.production, self.material, self.clip, posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "identity_mismatch" for i in gate["issues"]))

    def test_source_hash_mismatch_blocks(self):
        brain = copy.deepcopy(self.brain)
        brain["source_hash"] = "stale-source"
        gate = compile_compliance_gate(self.campaign, self.evidence, brain, self.critic, self.reconciliation, self.production, self.material, self.clip, self.posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "stale_source_hash" for i in gate["issues"]))

    def test_missing_mandatory_posting_blocks_without_invention(self):
        posting = copy.deepcopy(self.posting)
        posting["platforms"]["instagram"]["cta"] = []
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, self.production, self.material, self.clip, posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "posting_requirement_lost" for i in gate["issues"]))

    def test_optional_posting_requirement_may_be_absent(self):
        gate = self.gate()
        self.assertEqual(gate["status"], "ready", gate["issues"])
        self.assertFalse(any(i["code"] == "posting_requirement_lost" for i in gate["issues"]))

    def test_invalid_mandatory_provenance_blocks(self):
        production = copy.deepcopy(self.production)
        production["posting"]["cta"][0]["provenance"]["evidence_ids"] = []
        production["posting"]["requirements"][0]["provenance"]["evidence_ids"] = []
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, production, self.material, self.clip, self.posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "provenance_invalid" for i in gate["issues"]))

    def test_ambiguous_mandatory_blocks(self):
        production = copy.deepcopy(self.production)
        production["posting"]["cta"][0]["provenance"]["interpretation_type"] = "ambiguous"
        production["posting"]["requirements"][0]["provenance"]["interpretation_type"] = "ambiguous"
        production["posting"]["cta"][0]["provenance"]["resolution"]["status"] = "unresolved"
        production["posting"]["requirements"][0]["provenance"]["resolution"]["status"] = "unresolved"
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, production, self.material, self.clip, self.posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "mandatory_uncertain" for i in gate["issues"]))

    def test_platform_scope_loss_blocks(self):
        posting = copy.deepcopy(self.posting)
        posting["platforms"] = {"tiktok": posting["platforms"].pop("instagram")}
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, self.production, self.material, self.clip, posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "platform_scope_lost" for i in gate["issues"]))

    def test_restriction_loss_blocks(self):
        production = copy.deepcopy(self.production)
        production["clip"]["requirements"] = [{
            "field": "prohibited_content",
            "value": ["gambling"],
            "required": True,
            "scope": {},
            "provenance": prov("e1", self.source_hash),
        }]
        clip = copy.deepcopy(self.clip)
        clip["constraints"] = []
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, production, self.material, clip, self.posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "restriction_lost" for i in gate["issues"]))

    def test_material_and_selected_asset_readiness_are_checked(self):
        material = copy.deepcopy(self.material)
        clip = copy.deepcopy(self.clip)
        material["status"] = "blocked"
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, self.production, material, clip, self.posting)
        self.assertEqual(gate["status"], "blocked")
        asset = {"fingerprint": "asset-1", "status": "candidate"}
        material["status"] = "ready"
        material["assets"] = [asset]
        clip["segments"] = [{
            "segment_id": "seg-1", "status": "selected", "asset_fingerprint": "asset-1",
            "required": True, "material_requirement_id": "",
        }]
        gate = compile_compliance_gate(self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, self.production, material, clip, self.posting)
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(any(i["code"] == "selected_asset_not_ready" for i in gate["issues"]))

    def test_determinism_and_input_immutability(self):
        inputs = [self.campaign, self.evidence, self.brain, self.critic, self.reconciliation, self.production, self.material, self.clip, self.posting]
        before = copy.deepcopy(inputs)
        first = self.gate()
        second = self.gate()
        self.assertEqual(first, second)
        self.assertEqual(inputs, before)

    def test_cache_invalidates_each_downstream_identity(self):
        gate = self.gate()
        for obj, key, replacement in [
            (self.brain, "brain_id", "brain-v1:changed"),
            (self.critic, "critic_id", "critic-v1:changed"),
            (self.reconciliation, "reconciliation_id", "reconciliation-v1:changed"),
            (self.production, "contract_id", "production-contract-v1:changed"),
            (self.material, "material_plan_id", "material-plan-v1:changed"),
            (self.clip, "clip_strategy_id", "clip-strategy-v1:changed"),
            (self.posting, "posting_package_id", "posting-package-v1:changed"),
        ]:
            changed = copy.deepcopy(obj)
            changed[key] = replacement
            artifacts = {
                "brain": copy.deepcopy(self.brain), "critic": copy.deepcopy(self.critic),
                "reconciliation": copy.deepcopy(self.reconciliation), "production": copy.deepcopy(self.production),
                "material": copy.deepcopy(self.material), "clip": copy.deepcopy(self.clip),
                "posting": copy.deepcopy(self.posting),
            }
            artifacts[next(name for name, original in [
                ("brain", self.brain), ("critic", self.critic), ("reconciliation", self.reconciliation),
                ("production", self.production), ("material", self.material), ("clip", self.clip), ("posting", self.posting)
            ] if original is obj)] = changed
            current = compile_compliance_gate(
                self.campaign, self.evidence, artifacts["brain"], artifacts["critic"], artifacts["reconciliation"],
                artifacts["production"], artifacts["material"], artifacts["clip"], artifacts["posting"],
            )
            self.assertNotEqual(gate["compliance_gate_id"], current["compliance_gate_id"])

    def test_normalized_chain_persists_final_gate(self):
        campaign = {
            "id": "chain-ca08",
            "description": "Use official campaign footage. Follow now.",
            "requirements": [{"text": "Use official campaign footage.", "isMandatory": True}],
        }
        item = {
            "campaign_fit": {"score": 1, "label": "high", "reason": "matches"},
            "rules": {"asset_sources": ["official campaign footage"], "cta_required": True, "cta_text": "Follow now"},
            "evidence": [
                {"rule_path": "rules.asset_sources", "quote": "Use official campaign footage."},
                {"rule_path": "rules.cta_text", "quote": "Follow now."},
            ],
            "confidence": 0.9,
        }
        result = normalize_ai_result(item, campaign["id"], campaign)
        self.assertIn("compliance_gate", result)
        gate = result["compliance_gate"]
        self.assertEqual(gate["campaign_id"], campaign["id"])
        self.assertEqual(gate["source_hash"], source_fingerprint(campaign))
        self.assertTrue(gate["compliance_gate_id"])
        self.assertTrue(compliance_gate_is_current(
            gate, result["evidence_contract"], result["campaign_brain"], result["campaign_critic"],
            result["campaign_reconciliation"], result["production_contract"], result["material_plan"],
            result["clip_strategy"], result["posting_package"],
        ))


if __name__ == "__main__":
    unittest.main()
