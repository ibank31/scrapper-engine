#!/usr/bin/env python3
"""record_review regression tests: decisions are recorded locally and can be
posted to the API, but a recorded decision never triggers publishing."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from modules.clipping import record_review


class RecordReviewTests(unittest.TestCase):
    def test_approve_decision_builds_entry(self):
        entry = record_review.build_decision("prev-1", "approve")
        self.assertEqual(entry["action"], "approve")
        self.assertEqual(entry["preview_id"], "prev-1")
        self.assertFalse(entry["published"])

    def test_indonesian_setuju_maps_to_approve(self):
        entry = record_review.build_decision("prev-1", "setuju")
        self.assertEqual(entry["action"], "approve")

    def test_tolak_maps_to_reject(self):
        entry = record_review.build_decision("prev-1", "tolak", reason="hook lemah")
        self.assertEqual(entry["action"], "reject")
        self.assertEqual(entry["reason"], "hook lemah")

    def test_reject_requires_reason(self):
        with self.assertRaises(ValueError):
            record_review.build_decision("prev-1", "tolak")

    def test_unknown_decision_raises(self):
        with self.assertRaises(ValueError):
            record_review.build_decision("prev-1", "maybe")

    def test_local_log_appends_jsonl(self):
        with tempfile.TemporaryDirectory() as temp:
            log = os.path.join(temp, "decisions.jsonl")
            entry = record_review.build_decision("prev-2", "approve")
            record_review.append_local_log(entry, log)
            lines = open(log, encoding="utf-8").read().strip().split("\n")
            self.assertEqual(len(lines), 1)
            loaded = json.loads(lines[0])
            self.assertEqual(loaded["preview_id"], "prev-2")
            self.assertFalse(loaded["published"])

    def test_post_to_api_uses_review_token_header(self):
        entry = record_review.build_decision("prev-9", "approve")
        with mock.patch("urllib.request.urlopen") as urlopen:
            response = mock.Mock()
            response.read.return_value = b""
            urlopen.return_value = response
            with mock.patch("json.load", return_value={"ok": True}):
                record_review.post_to_api("https://example.com", entry, "tok123")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header("X-review-token"), "tok123")
        self.assertIn("/api/previews/prev-9/review", request.full_url)
        body = json.loads(request.data.decode())
        self.assertEqual(body["action"], "approve")

    def test_post_to_api_raises_on_http_error(self):
        import urllib.error
        entry = record_review.build_decision("prev-9", "approve")
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.HTTPError("u", 401, "unauthorized", {}, None)):
            with self.assertRaises(RuntimeError):
                record_review.post_to_api("https://example.com", entry, "bad")


if __name__ == "__main__":
    unittest.main()
