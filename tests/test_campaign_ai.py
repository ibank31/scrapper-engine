import unittest

from core.campaign_ai import normalize_ai_result, rules_fingerprint


class CampaignAITests(unittest.TestCase):
    def test_normalize_ai_result(self):
        result = normalize_ai_result(
            {
                "campaign_fit": {"score": 0.82, "label": "high", "reason": "good fit"},
                "rules": {
                    "aspect_ratio": "9:16",
                    "min_duration_seconds": "8",
                    "max_duration_seconds": 45,
                    "topic_terms": ["AI", "developer"],
                    "hashtags": ["#shorts"],
                },
                "ambiguities": [],
                "confidence": 0.91,
            },
            "abc",
        )
        self.assertEqual(result["campaign_id"], "abc")
        self.assertEqual(result["rules"]["aspect_ratio"], "9:16")
        self.assertEqual(result["rules"]["min_duration_seconds"], 8)
        self.assertEqual(result["rules"]["max_duration_seconds"], 45)
        self.assertAlmostEqual(result["campaign_fit"]["score"], 0.82)
        self.assertAlmostEqual(result["confidence"], 0.91)

    def test_rules_fingerprint_changes_when_rules_change(self):
        base = {
            "id": "abc",
            "title": "Example",
            "brand": "Brand",
            "description": "Use official clips",
            "platforms": ["tiktok"],
            "type": "clipping",
            "requirements": [{"text": "9:16"}],
            "resources": [],
            "payouts": [],
        }
        changed = dict(base)
        changed["requirements"] = [{"text": "16:9"}]
        self.assertNotEqual(rules_fingerprint(base), rules_fingerprint(changed))


if __name__ == "__main__":
    unittest.main()
