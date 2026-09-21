import unittest

from core.clip_candidates import select_candidates


class CandidateLimitTest(unittest.TestCase):
    def test_limit_two_returns_only_two_candidates(self):
        transcript = {"segments": [
            {"start": i * 20, "end": i * 20 + 20, "text": f"Here is the biggest lesson because this is useful number {i}."}
            for i in range(5)
        ]}
        candidates = select_candidates(transcript, min_seconds=20, max_seconds=20, limit=2)
        self.assertLessEqual(len(candidates), 2)
        self.assertEqual([item["rank"] for item in candidates], list(range(1, len(candidates) + 1)))


if __name__ == "__main__":
    unittest.main()
