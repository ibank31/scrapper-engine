import unittest

from core.campaign_rules import compile_plan, plan_markdown
from core.output_contract import validate_output_contract, validate_plan_output_contract


class CampaignRulesTest(unittest.TestCase):
    def test_compiles_assets_and_constraints(self):
        detail = {
            "campaign": {
                "id": "demo-1",
                "title": "Demo clipping",
                "brand": "Demo",
                "status": "active",
                "socialPlatforms": ["tiktok", "instagram"],
                "description": (
                    "Use the provided video clips as the foundation. Official audio is required. "
                    "Create vertical 9:16 videos. No third-party watermarks. "
                    "Mandatory watermark: use the official brand watermark asset. "
                    "Minimum Floor: 5,000 views per video to qualify for review. "
                    "Tag @DemoBrand and put www.example.com in your bio."
                ),
            },
            "staticDetails": {
                "requirements": [{"text": "Use the supplied assets and do not use view bots.", "isMandatory": True}],
                "resources": [{"label": "Raw footage", "url": "https://dropbox.com/s/demo"}],
            },
        }
        plan = compile_plan(detail)
        prod = plan["production"]
        self.assertTrue(prod["provided_material_required"])
        self.assertTrue(prod["official_audio_required"])
        self.assertEqual(prod["aspect_ratio"], "9:16")
        self.assertTrue(prod["watermark_required"])
        self.assertTrue(prod["no_third_party_watermark"])
        self.assertEqual(prod["minimum_views"], 5000)
        self.assertIn("@DemoBrand", prod["required_handles"])
        self.assertIn("https://dropbox.com/s/demo", prod["asset_urls"])
        self.assertFalse(plan["automation_policy"]["publish_allowed"])
        self.assertTrue(any(g["id"] == "human_review" and g["required"] for g in plan["gates"]))

    def test_keeps_google_sheet_tracker_from_campaign_text(self):
        tracker = "https://docs.google.com/spreadsheets/d/abc123456789/edit?usp=sharing"
        plan = compile_plan({
            "campaign": {"title": "Tracker clipping", "description": f"Use the official tracker: {tracker}"},
            "staticDetails": {},
        })
        self.assertIn(tracker, plan["production"]["asset_urls"])

    def test_markdown_contains_gates(self):
        plan = compile_plan({"campaign": {"title": "Empty", "status": "active"}})
        markdown = plan_markdown(plan)
        self.assertIn("## Mandatory gates", markdown)
        self.assertIn("human_review", markdown)

    def test_extracts_clip_length_from_fetched_document(self):
        detail = {
            "campaign": {"title": "Ryan Zofay", "description": "Provided podcast footage."},
            "docs_text": "Raw footage supplied. Clip Length: 15–60 seconds. English content only.",
            "staticDetails": {},
        }
        production = compile_plan(detail)["production"]
        self.assertEqual(production["min_duration_seconds"], 15.0)
        self.assertEqual(production["max_duration_seconds"], 60.0)

    def test_compiled_plan_has_valid_default_output_contract(self):
        contract = compile_plan({"campaign": {"title": "Contract"}})["output_contract"]
        self.assertEqual(contract, {
            "version": "default-v1",
            "expected_count": 2,
            "tier_allocation": {"tier_1": 1, "tier_2": 1},
            "min_duration_seconds": 0,
            "max_duration_seconds": 0,
            "distinctness_profile": "default-v1",
        })
        self.assertEqual(validate_output_contract(contract), {"valid": True, "reason": None, "errors": []})
        self.assertEqual(validate_plan_output_contract({"output_contract": contract})["reason"], None)

    def test_output_contract_requires_exact_two_outputs_and_tiers(self):
        contract = compile_plan({"campaign": {}})["output_contract"]
        self.assertEqual(contract["expected_count"], 2)
        self.assertEqual(contract["tier_allocation"]["tier_1"], 1)
        self.assertEqual(contract["tier_allocation"]["tier_2"], 1)

    def test_output_contract_rejects_invalid_allocation_and_missing_allocation(self):
        contract = compile_plan({"campaign": {}})["output_contract"]
        invalid = {**contract, "tier_allocation": {"tier_1": 2, "tier_2": 0}}
        result = validate_output_contract(invalid)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")
        missing = {key: value for key, value in contract.items() if key != "tier_allocation"}
        result = validate_output_contract(missing)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")

    def test_output_contract_rejects_invalid_expected_count_and_allocation_total(self):
        contract = compile_plan({"campaign": {}})["output_contract"]
        result = validate_output_contract({**contract, "expected_count": 3})
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")
        result = validate_output_contract({**contract, "tier_allocation": {"tier_1": 2, "tier_2": 1}})
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")

    def test_output_contract_rejects_invalid_duration_range_and_distinctness(self):
        contract = compile_plan({"campaign": {}})["output_contract"]
        result = validate_output_contract({**contract, "min_duration_seconds": 20, "max_duration_seconds": 10})
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")
        result = validate_output_contract({key: value for key, value in contract.items() if key != "distinctness_profile"})
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")

    def test_output_contract_accepts_campaign_duration_override(self):
        plan = compile_plan({
            "campaign": {"description": "Clip duration 12–30 seconds."},
        })
        contract = plan["output_contract"]
        self.assertEqual(contract["min_duration_seconds"], 12.0)
        self.assertEqual(contract["max_duration_seconds"], 30.0)
        self.assertTrue(validate_plan_output_contract(plan)["valid"])

    def test_output_contract_rejects_malformed_or_missing_plan_contract(self):
        result = validate_plan_output_contract({})
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")
        result = validate_output_contract("not-an-object")
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "blocked_invalid_output_contract")


if __name__ == "__main__":
    unittest.main()
