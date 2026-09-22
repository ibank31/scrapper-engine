import unittest

from core.campaign_exclusions import excluded_campaign_terms, is_excluded_campaign


class CampaignExclusionsTest(unittest.TestCase):
    def test_blocks_explicit_gambling_campaign(self):
        campaign = {
            "title": "INOUT Games — Viral Game Clips",
            "category": "gambling",
            "description": "Create real money gameplay clips and promote boosted RTP access.",
        }
        terms = excluded_campaign_terms(campaign)
        self.assertTrue(is_excluded_campaign(campaign))
        self.assertIn("gambling", terms)
        self.assertIn("real money", terms)
        self.assertIn("boosted rtp", terms)

    def test_blocks_operator_and_deposit_match_language(self):
        campaign = {
            "title": "Shuffle Streamers - Clipping",
            "requirements": [{"text": 'Caption: "Get a $1,000 deposit match on Shuffle"'}],
        }
        terms = excluded_campaign_terms(campaign)
        self.assertIn("shuffle streamers", terms)
        self.assertIn("deposit match", terms)

    def test_does_not_match_best_or_business_money_language(self):
        campaign = {
            "title": "Business Founder Clips",
            "description": "Share the best moments about money management and entrepreneurship.",
        }
        self.assertEqual(excluded_campaign_terms(campaign), [])
        self.assertFalse(is_excluded_campaign(campaign))

    def test_blocks_poker_and_slots_but_not_video_games(self):
        self.assertTrue(is_excluded_campaign({"title": "Coinpoker Logo General Campaign"}))
        self.assertTrue(is_excluded_campaign({"title": "WatchMeWin Slots Campaign"}))
        self.assertFalse(is_excluded_campaign({"title": "Roblox Gaming Clips"}))


if __name__ == "__main__":
    unittest.main()
