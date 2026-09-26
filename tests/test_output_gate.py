import unittest

from core.output_gate import evaluate_output_pair, evaluate_render_pair


class OutputGateTests(unittest.TestCase):
    def test_partial_render_is_blocked_before_validation(self):
        result = evaluate_output_pair([{"tier": "tier_1"}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "render_pair_incomplete")


    def test_render_gate_does_not_require_validation_results(self):
        result = evaluate_render_pair([{}, {}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence"], {"expected_count": 2, "rendered_count": 2})

    def test_render_gate_blocks_partial_render_without_validation_context(self):
        result = evaluate_render_pair([{}], 2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "render_pair_incomplete")

    def test_two_rendered_outputs_require_two_validation_records(self):
        result = evaluate_output_pair([{}, {}], [{"status": "pass"}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "validation_pair_incomplete")

    def test_one_failed_validation_blocks_entire_pair(self):
        result = evaluate_output_pair([{}, {}], [{"status": "pass"}, {"status": "fail"}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "validation_pair_failed")

    def test_valid_pair_retains_aggregate_evidence(self):
        result = evaluate_output_pair([{"tier": "tier_1"}, {"tier": "tier_2"}], [{"status": "pass"}, {"status": "needs_review"}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence"]["expected_count"], 2)
        self.assertEqual(result["evidence"]["validation_statuses"], ["pass", "needs_review"])


if __name__ == "__main__":
    unittest.main()
