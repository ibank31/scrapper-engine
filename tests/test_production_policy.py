import unittest

from core.production_policy import enrich_candidate, score_production_candidate


class ProductionPolicyTest(unittest.TestCase):
    def test_complete_compact_candidate_beats_generic_long_setup(self):
        strong = {"duration": 24, "text": "Why did he refuse? The answer is simple. So that means nobody saw it coming."}
        weak = {"duration": 58, "text": "Hello everyone, today we are going to talk about what happened before the story really begins"}
        strong_delta, _ = score_production_candidate(strong)
        weak_delta, _ = score_production_candidate(weak)
        self.assertGreater(strong_delta, weak_delta)

    def test_policy_preserves_candidate_and_adds_internal_reasons(self):
        item = {"score": 0.6, "duration": 30, "text": "What happened? The answer is finally clear."}
        result = enrich_candidate(item)
        self.assertIn("production_quality_adjustment", result)
        self.assertTrue(result["production_quality_reasons"])
        self.assertEqual(item["score"], 0.6)

    def test_campaign_bounds_remain_authoritative(self):
        plan = {"production": {"min_duration_seconds": 7, "max_duration_seconds": 15}}
        delta, reasons = score_production_candidate({"duration": 30, "text": "What happened? The answer is clear."}, plan)
        self.assertLess(delta, 0)
        self.assertIn("outside production duration bounds", reasons)


if __name__ == "__main__":
    unittest.main()
