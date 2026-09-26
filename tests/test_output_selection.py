import unittest

from core.output_selection import pairwise_distinctness, select_required_output_pair


CONTRACT = {
    "expected_count": 2,
    "tier_allocation": {"tier_1": 1, "tier_2": 1},
    "distinctness_profile": "default-v1",
}


def candidate(cid, tier, start, end, text, source="source-a", score=0.8):
    return {
        "candidate_id": cid,
        "tier": tier,
        "start": start,
        "end": end,
        "duration": end - start,
        "text": text,
        "source": source,
        "source_asset_id": source,
        "source_hash": source + "-hash",
        "score": score,
    }


class OutputSelectionTests(unittest.TestCase):
    def test_one_candidate_blocks_required_pair(self):
        result = select_required_output_pair([candidate("t1", "unknown", 0, 20, "one complete point")], CONTRACT)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "blocked_insufficient_output_contract")
        self.assertEqual(result["diagnostics"]["actual"], {"eligible": 1})

    def test_two_candidates_with_unknown_classification_are_valid(self):
        items = [
            candidate("a", "unknown", 0, 20, "first complete business point", score=0.9),
            candidate("b", "unknown", 30, 50, "second complete business point", score=0.8),
        ]
        result = select_required_output_pair(items, CONTRACT)
        self.assertTrue(result["ok"])
        self.assertEqual([item["distribution_slot"] for item in result["selected"]], ["tier_1", "tier_2"])
        self.assertTrue(result["diagnostics"]["classification_not_required"])

    def test_overlapping_pair_blocks_with_bounded_near_miss(self):
        items = [
            candidate("a", "unknown", 0, 30, "the same complete business point for founders", score=0.9),
            candidate("b", "unknown", 4, 28, "the same complete business point for founders", score=0.8),
        ]
        result = select_required_output_pair(items, CONTRACT)
        self.assertFalse(result["ok"])
        self.assertEqual(result["diagnostics"]["rejected_reasons"]["distinctness"], "no materially distinct candidate pair")
        self.assertLessEqual(len(result["diagnostics"]["near_misses"]), 3)

    def test_valid_pair_uses_score_not_audience_classification(self):
        items = [
            candidate("b", "tier_2", 30, 52, "college students learn a practical study system", score=0.7),
            candidate("a", "tier_1", 0, 22, "small business owners can improve cash flow", score=0.9),
        ]
        result = select_required_output_pair(items, CONTRACT)
        self.assertTrue(result["ok"])
        self.assertEqual([item["distribution_slot"] for item in result["selected"]], ["tier_1", "tier_2"])
        self.assertEqual([item["candidate_id"] for item in result["selected"]], ["a", "b"])

    def test_pairwise_evidence_rejects_same_candidate(self):
        item = candidate("same", "tier_1", 0, 20, "complete point")
        other = dict(item, tier="tier_2")
        evidence = pairwise_distinctness(item, other)
        self.assertFalse(evidence["distinct"])
        self.assertIn("same_candidate_id", evidence["reasons"])


if __name__ == "__main__":
    unittest.main()
