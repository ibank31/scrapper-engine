import copy
import json
import unittest
from pathlib import Path

from core.campaign_ai import normalize_ai_result
from core.campaign_critic import critique_campaign
from core.campaign_evidence import source_fingerprint, verify_quote

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "campaigns"


def load_fixture(campaign_id):
    for path in FIXTURE_DIR.glob("*.json"):
        campaign = json.loads(path.read_text(encoding="utf-8"))
        if campaign["id"] == campaign_id:
            return campaign
    raise AssertionError(f"fixture not found: {campaign_id}")


def fixture_ai_item(campaign):
    annotations = []
    for expected in campaign.get("expected_evidence") or []:
        path = str(expected["rule_path"])
        quote = str(expected["quote"])
        low = quote.lower()
        languages = ["en"] if "english" in low else ["id"] if any(token in low for token in ("gunak", "durasi", "detik", "wajib")) else []
        platforms = [
            platform for platform in ("instagram", "tiktok", "youtube", "facebook", "x", "twitter", "linkedin", "threads")
            if platform in path.lower()
        ]
        annotations.append({
            "rule_path": path,
            "value": quote,
            "requirement_level": "mandatory" if expected.get("mandatory") else "optional",
            "interpretation_type": "explicit",
            "scope": {"platforms": platforms, "languages": languages, "audiences": []},
        })
    return {
        "campaign_fit": {"score": 0.9, "label": "high", "reason": "fixture"},
        "rules": {},
        "rule_annotations": annotations,
        "ambiguities": [],
        "evidence": list(campaign.get("expected_evidence") or []),
        "confidence": 0.95,
    }


def brain_for(campaign):
    return normalize_ai_result(fixture_ai_item(campaign), campaign["id"], campaign)["campaign_brain"]


def rule_for(brain, path):
    return next(rule for rule in brain["rules"] if rule["source_rule_path"] == path)


def finding_codes(result):
    return {item["code"] for item in result["findings"]}


class CampaignCriticTests(unittest.TestCase):
    def test_good_six_shape_corpus_has_no_findings(self):
        for path in sorted(FIXTURE_DIR.glob("*.json")):
            campaign = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(fixture=campaign["id"]):
                result = critique_campaign(campaign, brain_for(campaign))
                self.assertEqual(result["status"], "pass", result)
                self.assertEqual(result["findings"], [], result)

    def test_missing_mandatory_rule_is_critical_and_evidence_backed(self):
        campaign = load_fixture("fixture-document-only")
        brain = brain_for(campaign)
        brain["rules"] = [rule for rule in brain["rules"] if rule["source_rule_path"] != "rules.cta_text"]
        result = critique_campaign(campaign, brain)
        finding = next(item for item in result["findings"] if item["code"] == "MISSING_RULE")
        self.assertEqual(finding["severity"], "CRITICAL")
        self.assertTrue(finding["evidence_ids"])
        self.assertEqual(result["status"], "blocked")

    def test_wrong_cta_is_detected_as_lost_concrete_value(self):
        campaign = load_fixture("fixture-document-only")
        brain = brain_for(campaign)
        rule_for(brain, "rules.cta_text")["value"] = "Apply now"
        result = critique_campaign(campaign, brain)
        self.assertIn("WRONG_CTA", finding_codes(result))

    def test_wrong_handle_and_hashtag_are_detected(self):
        campaign = load_fixture("fixture-platform-specific")
        brain = brain_for(campaign)
        rule_for(brain, "posting.instagram.handle")["value"] = "@wrong.account"
        rule_for(brain, "posting.instagram.hashtags")["value"] = "#WrongTag"
        result = critique_campaign(campaign, brain)
        codes = finding_codes(result)
        self.assertIn("WRONG_HANDLE", codes)
        self.assertIn("WRONG_HASHTAG", codes)

    def test_duplicate_rule_is_warning_but_legitimate_variant_is_not_duplicate(self):
        campaign = load_fixture("fixture-document-only")
        brain = brain_for(campaign)
        duplicate = copy.deepcopy(rule_for(brain, "rules.cta_text"))
        duplicate["rule_id"] += "-duplicate"
        brain["rules"].append(duplicate)
        result = critique_campaign(campaign, brain)
        self.assertIn("DUPLICATE_RULE", finding_codes(result))

        multilingual = load_fixture("fixture-multilingual")
        variant_result = critique_campaign(multilingual, brain_for(multilingual))
        self.assertNotIn("DUPLICATE_RULE", finding_codes(variant_result))

    def test_contradiction_is_critical_without_conflict_marker(self):
        campaign = {
            "id": "critic-contradiction",
            "docs_text": "Duration must be 15-30 seconds. Duration must be 60-90 seconds.",
            "expected_evidence": [
                {"rule_path": "rules.duration", "quote": "Duration must be 15-30 seconds.", "mandatory": True},
                {"rule_path": "rules.duration", "quote": "Duration must be 60-90 seconds.", "mandatory": True},
            ],
        }
        evidence = [verify_quote(campaign, item["quote"]) | {"rule_path": item["rule_path"]} for item in campaign["expected_evidence"]]
        brain = {
            "brain_id": "brain-v1:contradiction",
            "evidence": {"verified": evidence},
            "rules": [
                {"rule_id": "rule-a", "source_rule_path": "rules.duration", "value": "15-30 seconds", "requirement_level": "mandatory", "evidence_ids": [evidence[0]["evidence_id"], "missing"], "scope": {}},
                {"rule_id": "rule-b", "source_rule_path": "rules.duration", "value": "60-90 seconds", "requirement_level": "mandatory", "evidence_ids": [evidence[1]["evidence_id"]], "scope": {}},
            ],
        }
        result = critique_campaign(campaign, brain)
        finding = next(item for item in result["findings"] if item["code"] == "CONTRADICTORY_RULE")
        self.assertEqual(finding["severity"], "CRITICAL")
        self.assertEqual(set(finding["evidence_ids"]), {evidence[0]["evidence_id"], evidence[1]["evidence_id"]})

    def test_inferred_rule_without_evidence_is_unsupported(self):
        campaign = {"id": "critic-inference", "description": "No supported rule here."}
        brain = {
            "brain_id": "brain-v1:inference",
            "evidence": {"verified": []},
            "rules": [{
                "rule_id": "rule-inferred", "source_rule_path": "rules.cta_text", "value": "Invented CTA",
                "interpretation_type": "inferred", "requirement_level": "mandatory", "evidence_ids": [], "scope": {},
            }],
        }
        result = critique_campaign(campaign, brain)
        self.assertIn("UNSUPPORTED_INFERENCE", finding_codes(result))
        self.assertEqual(result["status"], "blocked")

    def test_platform_scope_mismatch_is_detected(self):
        campaign = load_fixture("fixture-platform-specific")
        brain = brain_for(campaign)
        rule_for(brain, "posting.instagram.hashtags")["scope"]["platforms"] = []
        result = critique_campaign(campaign, brain)
        self.assertIn("PLATFORM_SCOPE_MISMATCH", finding_codes(result))

    def test_lost_value_and_missing_material_requirement_are_detected(self):
        campaign = load_fixture("fixture-material-heavy")
        brain = brain_for(campaign)
        rule_for(brain, "rules.duration")["value"] = "90-120 seconds"
        brain["rules"] = [rule for rule in brain["rules"] if rule["source_rule_path"] != "rules.source_policy"]
        result = critique_campaign(campaign, brain)
        codes = finding_codes(result)
        self.assertIn("LOST_VALUE", codes)
        self.assertIn("MISSING_MATERIAL_REQUIREMENT", codes)

    def test_output_is_deterministic_and_brain_is_unchanged(self):
        campaign = load_fixture("fixture-document-only")
        brain = brain_for(campaign)
        before = copy.deepcopy(brain)
        first = critique_campaign(campaign, brain)
        second = critique_campaign(campaign, dict(reversed(list(brain.items()))))
        self.assertEqual(first, second)
        self.assertEqual(brain, before)
        self.assertEqual(first["critic_id"].startswith("critic-v1:"), True)

    def test_normalization_exposes_critic_without_breaking_legacy_projection(self):
        campaign = load_fixture("fixture-document-only")
        normalized = normalize_ai_result(fixture_ai_item(campaign), campaign["id"], campaign)
        self.assertIn("campaign_critic", normalized)
        self.assertEqual(normalized["campaign_critic"]["status"], "pass")
        self.assertIn("rules", normalized)
        self.assertEqual(normalized["schema_version"], 2)


if __name__ == "__main__":
    unittest.main()
