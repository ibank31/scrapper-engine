import unittest

from core.campaign_rules import compile_plan
from core.platform_profiles import PROFILE_VERSION, build_platform_profiles


class PlatformProfilesTests(unittest.TestCase):
    def test_document_only_rules_apply_to_all_platforms(self):
        profiles = build_platform_profiles(
            {"campaign": {"platforms": ["Instagram", "TikTok"]}},
            {"required_handles": ["@brand"], "hashtags": ["#Campaign"], "prohibited": ["spam"]},
            {"normalized_requirements": [{"text": "Use the approved opening phrase", "mandatory": True, "platform": "all"}]},
        )
        self.assertEqual(set(profiles), {"instagram", "tiktok"})
        self.assertEqual(profiles["instagram"]["version"], PROFILE_VERSION)
        self.assertEqual(profiles["tiktok"]["required_handles"], ["@brand"])
        self.assertIn("Use the approved opening phrase", profiles["instagram"]["required_phrases"])

    def test_platform_specific_override_is_scoped(self):
        profiles = build_platform_profiles(
            {"campaign": {"platforms": ["youtube", "ig"]}},
            {"platform_rules": {"youtube": {"caption_limit": 123, "subtitle_delivery": "native_caption_file"}}},
            {},
        )
        self.assertEqual(profiles["youtube"]["caption_limit"], 123)
        self.assertEqual(profiles["youtube"]["subtitle_delivery"], "native_caption_file")
        self.assertEqual(profiles["instagram"]["caption_limit"], 2200)

    def test_compile_plan_contains_profiles_and_evidence(self):
        plan = compile_plan({"campaign": {"id": "c1", "title": "Campaign", "platforms": ["youtube"]}, "staticDetails": {"requirements": [], "resources": []}})
        self.assertIn("youtube", plan["platform_profiles"])
        self.assertEqual(plan["platform_profile_version"], PROFILE_VERSION)
        self.assertIn("rule_evidence", plan["platform_profiles"]["youtube"])


if __name__ == "__main__":
    unittest.main()
