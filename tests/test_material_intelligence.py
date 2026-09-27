import copy
import unittest

from core.campaign_ai import normalize_ai_result
from core.campaign_evidence import source_fingerprint
from core.material_intelligence import compile_material_plan, material_plan_is_current


def material(value, *, required=None, evidence="e1", scope=None, interpretation="explicit", field="asset_sources"):
    item = {
        "field": field,
        "value": value,
        "required": required,
        "scope": scope or {},
        "provenance": {
            "rule_id": f"rule-{evidence}",
            "reconciliation_rule_id": f"reconciliation-{evidence}",
            "brain_rule_ids": [f"brain-{evidence}"],
            "evidence_ids": [evidence],
            "source_references": [{"source_type": "description", "location": field}],
            "interpretation_type": interpretation,
        },
    }
    return item


def contract(requirements=None, *, fallbacks=None):
    return {
        "schema_version": 1,
        "contract_id": "production-contract-v1:contract-1",
        "campaign_id": "campaign-1",
        "source_hash": "source-hash-1",
        "brain_id": "brain-v1:1",
        "reconciliation_id": "reconciliation-v1:1",
        "material": {"requirements": requirements or [], "fallback_assets": fallbacks or []},
    }


class MaterialIntelligenceTests(unittest.TestCase):
    def test_schema_identity_and_provenance(self):
        result = compile_material_plan(contract([material("official campaign footage", required=True)]))
        self.assertEqual(result["schema_version"], 1)
        self.assertTrue(result["material_plan_id"].startswith("material-plan-v1:"))
        self.assertEqual(result["campaign_id"], "campaign-1")
        self.assertEqual(result["production_contract_id"], "production-contract-v1:contract-1")
        requirement = result["requirements"][0]
        self.assertEqual(requirement["provenance"]["evidence_ids"], ["e1"])
        self.assertEqual(requirement["provenance"]["source_hash"], "source-hash-1")
        self.assertTrue(requirement["production_contract_requirement_id"].startswith("production-requirement-v1:"))

    def test_missing_mandatory_material_blocks(self):
        result = compile_material_plan(contract([material("official campaign footage", required=True)]))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["requirements"][0]["resolution_status"], "missing")
        self.assertEqual(result["issues"][0]["severity"], "critical")
        self.assertEqual(result["issues"][0]["type"], "missing_mandatory_material")

    def test_verified_candidate_resolves_requirement_without_faking_acquisition(self):
        base = compile_material_plan(contract([material("official campaign footage", required=True)]))
        requirement_id = base["requirements"][0]["material_requirement_id"]
        candidate = {"material_requirement_id": requirement_id, "source_url": "https://campaign.example/video.mp4", "source_type": "provided_asset", "status": "verified", "content_hash": "sha-1"}
        result = compile_material_plan(contract([material("official campaign footage", required=True)]), [candidate])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["requirements"][0]["resolution_status"], "resolved")
        self.assertEqual(result["assets"][0]["status"], "verified")
        self.assertNotEqual(result["assets"][0]["status"], "acquired")
        self.assertEqual(result["acquisition_plan"][0]["strategy"], "campaign_source")

    def test_optional_and_unknown_never_become_mandatory(self):
        result = compile_material_plan(contract([
            material("optional logo", required=False, evidence="optional"),
            material("unclear material", required=None, evidence="unknown", interpretation="ambiguous"),
        ]))
        by_value = {item["value"]: item for item in result["requirements"]}
        self.assertFalse(by_value["optional logo"]["required"])
        self.assertIsNone(by_value["unclear material"]["required"])
        self.assertNotEqual(by_value["unclear material"]["resolution_status"], "missing")
        self.assertEqual(result["status"], "review")
        self.assertFalse(any(issue["type"] == "missing_mandatory_material" for issue in result["issues"]))

    def test_platform_scope_remains_separate(self):
        result = compile_material_plan(contract([
            material("Instagram campaign footage", required=True, evidence="ig", scope={"platforms": ["Instagram"]}),
            material("TikTok campaign footage", required=True, evidence="tt", scope={"platforms": ["TikTok"]}),
        ]))
        scopes = {tuple(item["scope"]["platforms"]): item for item in result["requirements"]}
        self.assertIn(("instagram",), scopes)
        self.assertIn(("tiktok",), scopes)
        self.assertNotEqual(scopes[("instagram",)]["material_requirement_id"], scopes[("tiktok",)]["material_requirement_id"])

    def test_fallbacks_are_explicit_and_not_activated_as_assets(self):
        result = compile_material_plan(contract([material("official footage", required=True)], fallbacks=["approved alternate footage"]))
        self.assertEqual(len(result["fallbacks"]), 1)
        self.assertTrue(result["fallbacks"][0]["authorized"])
        self.assertEqual(result["requirements"][0]["resolution_status"], "missing")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["summary"]["asset_count"], 0)

    def test_duplicate_candidates_share_one_logical_asset(self):
        base = compile_material_plan(contract([material("source footage", required=True)]))
        requirement_id = base["requirements"][0]["material_requirement_id"]
        candidates = [
            {"material_requirement_id": requirement_id, "source_url": "https://example.test/a.mp4", "status": "candidate", "fingerprint": "same"},
            {"material_requirement_id": requirement_id, "source_url": "https://mirror.test/a.mp4", "status": "verified", "fingerprint": "same"},
        ]
        result = compile_material_plan(contract([material("source footage", required=True)]), candidates)
        self.assertEqual(len(result["assets"]), 1)
        self.assertEqual(result["summary"]["duplicate_assets"], 1)
        self.assertEqual(result["assets"][0]["status"], "candidate")

    def test_determinism_and_input_immutability(self):
        source = contract([material("source footage", required=True)])
        before = copy.deepcopy(source)
        first = compile_material_plan(source)
        second = compile_material_plan(copy.deepcopy(source))
        self.assertEqual(first, second)
        self.assertEqual(source, before)

    def test_cache_identity_rejects_changed_dependency(self):
        production = contract([])
        plan = compile_material_plan(production)
        self.assertTrue(material_plan_is_current(plan, production))
        changed = copy.deepcopy(production)
        changed["source_hash"] = "source-hash-2"
        self.assertFalse(material_plan_is_current(plan, changed))
        changed_contract = copy.deepcopy(production)
        changed_contract["contract_id"] = "production-contract-v1:contract-2"
        self.assertFalse(material_plan_is_current(plan, changed_contract))

    def test_normalized_chain_persists_material_plan(self):
        campaign = {
            "id": "chain-material-1",
            "description": "Use official campaign footage. Include subtitles.",
            "requirements": [{"text": "Use official campaign footage.", "isMandatory": True}],
        }
        item = {
            "campaign_fit": {"score": 1, "label": "high", "reason": "matches"},
            "rules": {"asset_sources": ["official campaign footage"], "subtitle_required": True},
            "evidence": [{"rule_path": "rules.asset_sources", "quote": "Use official campaign footage."}, {"rule_path": "rules.subtitle_required", "quote": "Include subtitles."}],
            "confidence": 0.9,
        }
        result = normalize_ai_result(item, campaign["id"], campaign)
        plan = result["material_plan"]
        self.assertEqual(plan["campaign_id"], campaign["id"])
        self.assertEqual(plan["source_hash"], source_fingerprint(campaign))
        self.assertIn("production_contract_id", plan)
        self.assertTrue(plan["requirements"])


if __name__ == "__main__":
    unittest.main()
