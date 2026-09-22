import unittest

from core.campaign_rules import compile_plan, plan_markdown


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


if __name__ == "__main__":
    unittest.main()
