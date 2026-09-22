import unittest

from core.semantic_ranker import rank_candidates


class SemanticRankerTest(unittest.TestCase):
    def test_rejects_short_mid_thought_candidate(self):
        plan = {"production": {"topic_terms": ["business"]}}
        candidates = [{"rank": 1, "start": 0, "end": 5.4, "duration": 5.4, "text": "They're gonna guide you to become that future"}]
        result = rank_candidates(candidates, plan)[0]
        self.assertEqual(result["semantic"]["decision"], "reject")
        self.assertIn("short_clip", result["semantic"]["risks"])

    def test_prefers_complete_problem_solution_candidate(self):
        plan = {"production": {"topic_terms": ["business"]}}
        candidates = [
            {"rank": 1, "start": 0, "end": 36, "duration": 36, "text": "Here is the biggest mistake in business. Most people ignore the problem, but the answer is to simplify the process. That means you can repeat it every week."},
            {"rank": 2, "start": 40, "end": 65, "duration": 25, "text": "And then we kept going until the end"},
        ]
        result = rank_candidates(candidates, plan)
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(result[0]["semantic"]["decision"], "render")
        self.assertGreaterEqual(result[0]["semantic"]["payoff_score"], 80)

    def test_campaign_max_duration_is_not_ignored_by_fallback(self):
        plan = {"production": {"max_duration_seconds": 5}}
        candidates = [{"rank": 1, "start": 0, "end": 5, "duration": 5, "text": "Complete point for the campaign."}]
        result = rank_candidates(candidates, plan)[0]
        self.assertNotEqual(result["semantic"]["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
