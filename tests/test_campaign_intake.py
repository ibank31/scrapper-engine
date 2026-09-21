import unittest

from core.campaign_rules import compile_plan
from modules.reward_campaign.intake import _reference_urls


class CampaignIntakeTest(unittest.TestCase):
    def test_normalizes_string_and_object_requirements(self):
        plan = compile_plan({
            "campaign": {"title": "Demo", "description": "Use provided raw assets."},
            "staticDetails": {"requirements": ["Include demographic information", {"text": "Use official audio", "isMandatory": True}]},
        })
        normalized = plan["source_of_truth"]["normalized_requirements"]
        self.assertEqual(normalized[0]["id"], "demographic_information")
        self.assertEqual(normalized[1]["id"], "official_audio")

    def test_doc_url_parser_is_safe_without_network(self):
        self.assertEqual(_reference_urls("https://example.com/not-a-doc"), [])


if __name__ == "__main__":
    unittest.main()
