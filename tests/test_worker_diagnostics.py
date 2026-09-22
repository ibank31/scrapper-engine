import unittest

from worker.run_job import _candidate_audit_reason


class WorkerDiagnosticsTest(unittest.TestCase):
    def test_zero_candidate_reason_is_actionable(self):
        reason = _candidate_audit_reason(
            {
                "transcribed": 2,
                "raw_candidates": 1,
                "semantic_rejects": 1,
                "hard_policy_rejects": 1,
                "relevance_blocks": 0,
            },
            source_count=2,
            usable_count=2,
        )
        self.assertIn("sources=2", reason)
        self.assertIn("usable_sources=2", reason)
        self.assertIn("transcribed=2", reason)
        self.assertIn("raw_candidates=1", reason)
        self.assertIn("hard_policy_rejects=1", reason)
        self.assertIn("relevance_blocks=0", reason)


if __name__ == "__main__":
    unittest.main()
