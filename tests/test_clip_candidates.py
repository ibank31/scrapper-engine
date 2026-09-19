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


if __name__ == "__main__":
    unittest.main()
