import unittest
from unittest import mock

import requests

from worker.run_job import claim_job


class WorkerClaimTest(unittest.TestCase):
    def test_claim_sends_dispatch_token_and_succeeds(self):
        with mock.patch("worker.run_job.api_call", return_value={}) as call:
            self.assertTrue(claim_job("https://api", "job-1", "worker", "dispatch-1"))
        call.assert_called_once_with(
            "https://api",
            "/api/jobs/job-1/claim",
            "worker",
            "POST",
            {"claim_token": "dispatch-1", "runner_id": "local:dispatch-1"},
        )

    def test_lost_claim_is_clean_noop(self):
        response = mock.Mock(status_code=409)
        error = requests.HTTPError("conflict", response=response)
        with mock.patch("worker.run_job.api_call", side_effect=error):
            self.assertFalse(claim_job("https://api", "job-1", "worker", "dispatch-1"))

    def test_unexpected_claim_error_is_not_hidden(self):
        response = mock.Mock(status_code=500)
        error = requests.HTTPError("server error", response=response)
        with mock.patch("worker.run_job.api_call", side_effect=error):
            with self.assertRaises(requests.HTTPError):
                claim_job("https://api", "job-1", "worker", "dispatch-1")


if __name__ == "__main__":
    unittest.main()
