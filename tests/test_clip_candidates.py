import unittest

from core.clip_candidates import select_candidates


class ClipCandidatesTest(unittest.TestCase):
    def test_selects_ranked_non_overlapping_windows(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 10, "text": "Here is the biggest mistake because most people miss the problem."},
                {"start": 10, "end": 25, "text": "The solution is simple and the result is 50 percent better."},
                {"start": 25, "end": 40, "text": "First, follow this step and finally measure the result."},
                {"start": 80, "end": 95, "text": "A short unrelated sentence."},
            ]
        }
        candidates = select_candidates(transcript, min_seconds=20, max_seconds=60, limit=5)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rank"], 1)
        self.assertGreaterEqual(candidates[0]["score"], 0)
        self.assertTrue(candidates[0]["end"] <= 60)

    def test_rewards_complete_payoff_over_keyword_only_excerpt(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 10, "text": "Here is the secret most people ask about?"},
                {"start": 10, "end": 24, "text": "The answer is to simplify the process."},
                {"start": 24, "end": 40, "text": "So that means you can repeat it every week."},
                {"start": 50, "end": 60, "text": "Here is the biggest mistake."},
                {"start": 60, "end": 70, "text": "Most people miss it."},
            ]
        }
        candidates = select_candidates(transcript, min_seconds=20, max_seconds=45, limit=5)
        self.assertTrue(candidates)
        self.assertIn("payoff or takeaway", candidates[0]["reasons"])
        self.assertIn("complete ending", candidates[0]["reasons"])

    def test_short_source_can_still_produce_a_candidate(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 2.5, "text": "This is the key lesson."},
                {"start": 2.5, "end": 5.0, "text": "So you can repeat it every week."},
            ]
        }
        candidates = select_candidates(transcript, min_seconds=3, max_seconds=60, limit=2)
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(candidates[0]["duration"], 5.0)


if __name__ == "__main__":
    unittest.main()
