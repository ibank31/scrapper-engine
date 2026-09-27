import copy
import unittest

from core.posting_package import compile_posting_package, posting_package_is_current


def prov(evidence, source="source-1", rule="rule-1"):
    return {"rule_id": rule, "reconciliation_rule_id": "recon-1", "brain_rule_ids": ["brain-rule-1"], "evidence_ids": [evidence], "source_references": [{"source_type": "brief", "location": evidence}], "source_hash": source, "interpretation_type": "explicit", "requirement_level": "mandatory", "resolution": {"status": "resolved"}}


def req(field, value, evidence, scope=None, required=True):
    return {"field": field, "value": value, "required": required, "scope": scope or {}, "provenance": prov(evidence)}


class PostingPackageTests(unittest.TestCase):
    def setUp(self):
        self.contract = {
            "schema_version": 1, "contract_id": "production-contract-v1:1", "campaign_id": "campaign-1", "source_hash": "source-1", "brain_id": "brain-v1:1", "reconciliation_id": "reconciliation-v1:1",
            "posting": {
                "requirements": [],
                "cta": [req("cta", "Follow now", "e-cta", {"platforms": ["instagram"]})],
                "hashtags": [req("hashtags", ["#ExactTag"], "e-tags", {"platforms": ["instagram"]}), req("hashtags", ["#TikTokTag"], "e-tags-tt", {"platforms": ["tiktok"]})],
                "handles": [req("handles", ["@brand_ig"], "e-handle-ig", {"platforms": ["instagram"]}), req("handles", ["@brand_tt"], "e-handle-tt", {"platforms": ["tiktok"]})],
                "disclosure": [req("disclosure", ["#ad"], "e-disclosure", {"platforms": ["instagram"]})],
                "audio_policy": [req("audio_policy", "campaign audio only", "e-audio", {"platforms": ["instagram"]})],
            },
        }
        self.strategy = {"schema_version": 1, "clip_strategy_id": "clip-strategy-v1:1", "campaign_id": "campaign-1", "source_hash": "source-1", "brain_id": "brain-v1:1", "reconciliation_id": "reconciliation-v1:1", "platforms": ["instagram", "tiktok"]}

    def test_exact_values_and_platform_scope_are_preserved(self):
        package = compile_posting_package(self.contract, self.strategy)
        self.assertEqual(package["status"], "ready")
        self.assertEqual(package["platforms"]["instagram"]["cta"][0]["value"], "Follow now")
        self.assertEqual(package["platforms"]["instagram"]["hashtags"][0]["value"], ["#ExactTag"])
        self.assertEqual(package["platforms"]["tiktok"]["hashtags"][0]["value"], ["#TikTokTag"])
        self.assertEqual(package["platforms"]["instagram"]["handles"][0]["value"], ["@brand_ig"])
        self.assertEqual(package["platforms"]["tiktok"]["handles"][0]["value"], ["@brand_tt"])

    def test_missing_mandatory_value_blocks_without_invention(self):
        contract = copy.deepcopy(self.contract)
        contract["posting"]["cta"][0]["value"] = None
        package = compile_posting_package(contract, self.strategy)
        self.assertEqual(package["status"], "blocked")
        self.assertFalse(any(item["value"] for item in package["platforms"]["instagram"]["cta"]))
        self.assertTrue(any(item["type"] == "missing_mandatory_posting" for item in package["issues"]))

    def test_unverified_provenance_blocks(self):
        contract = copy.deepcopy(self.contract)
        contract["posting"]["cta"][0]["provenance"]["evidence_ids"] = []
        package = compile_posting_package(contract, self.strategy)
        self.assertEqual(package["status"], "blocked")
        self.assertEqual(package["summary"]["provenance_coverage"], 6 / 7)

    def test_determinism_cache_and_immutability(self):
        before_contract, before_strategy = copy.deepcopy(self.contract), copy.deepcopy(self.strategy)
        first = compile_posting_package(self.contract, self.strategy)
        second = compile_posting_package(copy.deepcopy(self.contract), copy.deepcopy(self.strategy))
        self.assertEqual(first, second)
        self.assertEqual(self.contract, before_contract)
        self.assertEqual(self.strategy, before_strategy)
        self.assertTrue(posting_package_is_current(first, self.contract, self.strategy))
        changed = copy.deepcopy(self.strategy)
        changed["clip_strategy_id"] = "clip-strategy-v1:changed"
        self.assertFalse(posting_package_is_current(first, self.contract, changed))

    def test_campaign_fallback_requires_provenance(self):
        campaign = {
            "id": "campaign-1",
            "platforms": ["instagram"],
            "posting": {"cta": {"instagram": "Campaign CTA"}},
            "posting_provenance": prov("e-campaign-cta"),
        }
        package = compile_posting_package(self.contract, self.strategy, campaign)
        self.assertEqual(package["status"], "ready")
        self.assertEqual(package["summary"]["provenance_coverage"], 1.0)

        campaign["posting_provenance"]["evidence_ids"] = []
        blocked = compile_posting_package(self.contract, self.strategy, campaign)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["summary"]["provenance_coverage"], 7 / 8)
        self.assertTrue(any(i["type"] == "provenance_invalid" and i["field"] == "cta" for i in blocked["issues"]))

    def test_manual_native_requirement_is_explicit_and_blocks_mandatory(self):
        contract = copy.deepcopy(self.contract)
        manual = req("native_tag_requirements", {"tag": "native"}, "e-native", {"platforms": ["instagram"]})
        manual["provenance"]["interpretation_type"] = "manual_required"
        contract["posting"]["native_tag_requirements"] = [manual]
        package = compile_posting_package(contract, self.strategy)
        self.assertEqual(package["status"], "blocked")
        self.assertTrue(package["platforms"]["instagram"]["manual_actions"])
        self.assertTrue(any(i["type"] == "mandatory_uncertain" for i in package["issues"]))

    def test_caption_and_schedule_are_only_copied_when_explicit(self):
        campaign = {"id": "campaign-1", "platforms": ["instagram"], "posting": {"caption": {"instagram": "Exact campaign caption"}, "schedule_intent": {"instagram": "next approved slot"}}}
        package = compile_posting_package(self.contract, self.strategy, campaign)
        self.assertEqual(package["platforms"]["instagram"]["caption"][0]["value"], "Exact campaign caption")
        self.assertEqual(package["platforms"]["instagram"]["schedule_intent"][0]["value"], "next approved slot")


if __name__ == "__main__":
    unittest.main()
