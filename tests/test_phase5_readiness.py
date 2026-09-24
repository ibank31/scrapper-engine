import unittest

from core.pilot_evidence import build_pilot_evidence
from core.staging_matrix import CASES, run_failure_matrix


class Phase5ReadinessTests(unittest.TestCase):
    def test_failure_matrix_is_complete_and_provider_off(self):
        result = run_failure_matrix()
        self.assertTrue(result["ok"])
        self.assertFalse(result["provider_mutation_enabled"])
        self.assertEqual([item["case"] for item in result["cases"]], list(CASES))
        self.assertTrue(all(item["status"] == "pass" for item in result["cases"]))

    def test_provider_mutation_enabled_matrix_is_blocked(self):
        result = run_failure_matrix(provider_mutation_enabled=True)
        self.assertFalse(result["ok"])
        self.assertTrue(all(item["status"] == "blocked" for item in result["cases"]))

    def test_pilot_requires_evidence_and_human_confirmation(self):
        values = {"job_id": "job-1", "run_id": "run-1", "rules_hash": "rules", "source_hashes": ["source"], "operation_keys": ["op"], "provider_ids": ["post"], "due_times": ["time"], "terminal_states": ["scheduled"], "rollback_evidence": {"available": True}}
        ready = build_pilot_evidence(human_confirmation=False, **values)
        self.assertEqual(ready["status"], "ready_for_human_confirmation")
        confirmed = build_pilot_evidence(human_confirmation=True, **values)
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(build_pilot_evidence(human_confirmation=False, mutation_executed=True, **values)["status"], "blocked_confirmation_required")


if __name__ == "__main__": unittest.main()
