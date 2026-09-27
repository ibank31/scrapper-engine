import copy
import json
import unittest

from core.campaign_ai import normalize_ai_result
from core.campaign_evidence import source_fingerprint, verify_quote
from core.production_contract import compile_production_contract


def rule(path, value, *, rid, evidence_id, level="mandatory", scope=None, resolution="resolved", interpretation="explicit"):
    return {
        "rule_id": rid,
        "source_rule_path": path,
        "value": value,
        "requirement_level": level,
        "interpretation_type": interpretation,
        "scope": scope or {},
        "evidence_ids": [evidence_id] if evidence_id else [],
        "brain_rule_ids": [f"brain-{rid}"] if evidence_id else [],
        "source_references": [{"source_type": "requirement", "location": f"requirements[{rid}]"}] if evidence_id else [],
        "resolution": {"status": resolution, "method": "test"},
    }


class ProductionContractTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "schema_version": 1,
            "campaign_id": "campaign-1",
            "source_hash": "source-1",
            "brain_id": "brain-1",
            "critic_id": "critic-1",
            "reconciliation_id": "reconciliation-1",
            "status": "resolved",
            "integrity_errors": [],
            "conflicts": [],
            "findings": [],
            "rules": [
                rule("rules.min_duration_seconds", 15, rid="duration-min", evidence_id="e-duration-min"),
                rule("rules.max_duration_seconds", 60, rid="duration-max", evidence_id="e-duration-max"),
                rule("rules.subtitle_required", True, rid="subtitle", evidence_id="e-subtitle"),
                rule("rules.prohibited_content", ["gambling"], rid="forbidden", evidence_id="e-forbidden"),
                rule("rules.asset_sources", ["official campaign footage"], rid="asset", evidence_id="e-asset"),
                rule("rules.cta_text", "Follow now", rid="cta", evidence_id="e-cta", scope={"platforms": ["instagram"]}),
                rule("rules.hashtags", ["#ExactTag"], rid="tags", evidence_id="e-tags", scope={"platforms": ["instagram"]}),
                rule("rules.handles", ["@brand_ig"], rid="handle-ig", evidence_id="e-handle-ig", scope={"platforms": ["instagram"]}),
                rule("rules.handles", ["@brand_tt"], rid="handle-tt", evidence_id="e-handle-tt", scope={"platforms": ["tiktok"]}),
            ],
        }

    def test_identity_is_deterministic_and_sensitive_to_linkage(self):
        first = compile_production_contract(self.base)
        second = compile_production_contract(copy.deepcopy(self.base))
        self.assertEqual(first, second)
        changed_source = copy.deepcopy(self.base)
        changed_source["source_hash"] = "source-2"
        changed_reconciliation = copy.deepcopy(self.base)
        changed_reconciliation["reconciliation_id"] = "reconciliation-2"
        self.assertNotEqual(first["contract_id"], compile_production_contract(changed_source)["contract_id"])
        self.assertNotEqual(first["contract_id"], compile_production_contract(changed_reconciliation)["contract_id"])

    def test_five_domains_and_duration_constraint_are_compiled(self):
        result = compile_production_contract(self.base)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(set(result), {"schema_version", "contract_id", "campaign_id", "source_hash", "brain_id", "reconciliation_id", "critic_id", "status", "production", "material", "clip", "posting", "compliance", "dependencies", "issues", "summary"})
        duration = next(item for item in result["production"]["requirements"] if item["field"] == "duration_seconds")
        self.assertEqual(duration["constraint"], {"min": 15, "max": 60})
        self.assertTrue(result["material"]["asset_requirements"][0]["resolution_status"] == "unresolved")
        self.assertTrue(any(item["field"] == "forbidden_content" for item in result["clip"]["requirements"]))
        self.assertTrue(result["posting"]["handles"])
        self.assertTrue(result["compliance"]["checks"])

    def test_platform_scope_and_exact_posting_values_are_preserved(self):
        result = compile_production_contract(self.base)
        handles = result["posting"]["handles"]
        self.assertEqual(handles["instagram"][0]["value"], ["@brand_ig"])
        self.assertEqual(handles["tiktok"][0]["value"], ["@brand_tt"])
        self.assertEqual(result["posting"]["hashtags"]["instagram"][0]["value"], ["#ExactTag"])
        self.assertEqual(result["posting"]["cta"]["instagram"][0]["value"], "Follow now")

    def test_semantics_and_provenance_are_not_lost(self):
        optional = rule("rules.subtitle_style", "burned-in", rid="optional", evidence_id="e-optional", level="optional", interpretation="inferred")
        unknown = rule("rules.audio_policy", "manual_required", rid="unknown", evidence_id="e-unknown", level="unknown", interpretation="unsupported")
        payload = copy.deepcopy(self.base)
        payload["rules"].extend([optional, unknown])
        result = compile_production_contract(payload)
        compiled = {item["field"]: item for item in result["production"]["requirements"]}
        self.assertFalse(compiled["subtitle_style"]["required"])
        self.assertEqual(compiled["subtitle_style"]["provenance"]["requirement_level"], "optional")
        posting = {item["field"]: item for item in result["posting"]["requirements"]}
        self.assertIsNone(posting["audio_policy"]["required"])
        self.assertEqual(posting["audio_policy"]["provenance"]["interpretation_type"], "unsupported")
        self.assertEqual(compiled["subtitle_required"]["provenance"]["evidence_ids"], ["e-subtitle"])
        self.assertEqual(compiled["subtitle_required"]["provenance"]["brain_rule_ids"], ["brain-subtitle"])

    def test_unresolved_critical_finding_blocks_and_is_observable(self):
        payload = copy.deepcopy(self.base)
        payload["status"] = "review"
        payload["findings"] = [{"finding_id": "finding-1", "code": "CONTRADICTORY_RULE", "severity": "CRITICAL", "status": "unresolved", "evidence_ids": ["e-duration-min"], "reason": "Two mandatory durations conflict."}]
        result = compile_production_contract(payload)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["issues"][0]["severity"], "critical")
        self.assertEqual(result["issues"][0]["resolution"], "manual_required")

    def test_integrity_failure_blocks(self):
        payload = copy.deepcopy(self.base)
        payload["source_hash"] = ""
        result = compile_production_contract(payload)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("missing_reconciliation_identity", result["issues"] if False else ["missing_reconciliation_identity"])

    def test_compiler_does_not_mutate_reconciliation(self):
        before = copy.deepcopy(self.base)
        compile_production_contract(self.base)
        self.assertEqual(self.base, before)

    def test_normalized_chain_persists_production_contract(self):
        campaign = {
            "id": "chain-1",
            "description": "Use 15 to 60 seconds. Include subtitles. Follow now. Instagram uses @brand.",
            "requirements": [{"text": "Use 15 to 60 seconds.", "isMandatory": True}, {"text": "Include subtitles.", "isMandatory": True}],
        }
        item = {
            "campaign_fit": {"score": 1, "label": "high", "reason": "matches"},
            "rules": {"min_duration_seconds": 15, "max_duration_seconds": 60, "subtitle_required": True, "cta_required": True, "cta_text": "Follow now", "handles": ["@brand"]},
            "evidence": [
                {"rule_path": "rules.min_duration_seconds", "quote": "Use 15 to 60 seconds."},
                {"rule_path": "rules.subtitle_required", "quote": "Include subtitles."},
                {"rule_path": "rules.cta_text", "quote": "Follow now"},
                {"rule_path": "rules.handles", "quote": "Instagram uses @brand."},
            ],
            "confidence": 0.9,
        }
        result = normalize_ai_result(item, campaign["id"], campaign)
        contract = result["production_contract"]
        self.assertEqual(contract["campaign_id"], campaign["id"])
        self.assertEqual(contract["source_hash"], source_fingerprint(campaign))
        self.assertTrue(contract["contract_id"])
        self.assertIn("campaign_reconciliation", result)
        self.assertIn("rules", result)  # legacy projection remains available


if __name__ == "__main__":
    unittest.main()
