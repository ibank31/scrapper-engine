import unittest
from datetime import datetime, timezone

from core.campaign_priority import score_campaign, competition_proxy


class CampaignPriorityTest(unittest.TestCase):
    def test_recent_campaign_with_materials_ranks_above_stale_campaign(self):
        now = datetime(2026, 9, 21, tzinfo=timezone.utc)
        base = {
            "relevance": 0.9,
            "budget_left": 20000,
            "rate_per_1k": 4,
            "platforms": ["tiktok", "youtube"],
            "description": "Use provided official footage from the content bank.",
        }
        recent = score_campaign({**base, "updatedAt": "2026-09-20T00:00:00Z"}, now)
        stale = score_campaign({**base, "updatedAt": "2026-06-01T00:00:00Z"}, now)
        self.assertGreater(recent["score"], stale["score"])
        self.assertGreater(recent["priority_components"]["recency"], stale["priority_components"]["recency"])

    def test_proxy_is_explicitly_not_competitor_count(self):
        result = competition_proxy({"rate_per_1k": 8, "budget_left": 20000, "platforms": ["tiktok"]})
        self.assertEqual(result["label"], "competition proxy")
        self.assertIn("not competitor count", result["basis"])
        self.assertIn(result["risk"], {"low", "medium", "high"})

    def test_score_has_bounded_components(self):
        result = score_campaign({"relevance": 1, "budget_left": 999999, "rate_per_1k": 99})
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertTrue(all(0 <= value <= 1 for value in result["priority_components"].values()))


if __name__ == "__main__":
    unittest.main()
