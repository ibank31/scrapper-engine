#!/usr/bin/env python3
"""English clip metadata regression tests.

Per finished clip, one Gemini call produces a title, caption, CTA, and
hashtags in English for the review chat. Generation must never raise and must
never fabricate campaign claims: output is descriptive, and any failure yields
None so the pipeline continues without metadata.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.clip_metadata import generate_clip_metadata


class ClipMetadataTests(unittest.TestCase):
    def _clip(self):
        return {"rank": 1, "start": 8.8, "end": 30.0, "duration": 21.2,
                "text": "Nobody tells you this secret about rental property.",
                "hook_sentence": "Nobody tells you this secret."}

    def test_valid_response_is_normalized(self):
        from core import clip_metadata
        payload = {"title": "The Rental Secret Nobody Tells You",
                   "caption": "Nobody tells you this secret about rental property. Watch till the end.",
                   "cta": "Follow for more property tips.",
                   "hashtags": ["realestate", "propertytips", "investing", "passiveincome", "landlord"],
                   "hook_text": "Nobody tells you this secret."}
        with mock.patch.object(clip_metadata, "_generate", return_value=json.dumps(payload)):
            meta = generate_clip_metadata(self._clip(), "RentalProperty OS")
        self.assertEqual(meta["title"], "The Rental Secret Nobody Tells You")
        self.assertEqual(len(meta["hashtags"]), 5)
        self.assertTrue(meta["caption"])

    def test_title_is_capped_at_60_chars(self):
        from core import clip_metadata
        payload = {"title": "x" * 90, "caption": "cap", "cta": "cta",
                   "hashtags": ["a"], "hook_text": "hook"}
        with mock.patch.object(clip_metadata, "_generate", return_value=json.dumps(payload)):
            meta = generate_clip_metadata(self._clip(), "Campaign")
        self.assertLessEqual(len(meta["title"]), 60)

    def test_hashtags_are_cleaned_and_capped(self):
        from core import clip_metadata
        payload = {"title": "t", "caption": "c", "cta": "cta",
                   "hashtags": ["#RealEstate", "a b", "", "ok", "two", "three", "four"],
                   "hook_text": "h"}
        with mock.patch.object(clip_metadata, "_generate", return_value=json.dumps(payload)):
            meta = generate_clip_metadata(self._clip(), "Campaign")
        self.assertLessEqual(len(meta["hashtags"]), 5)
        for tag in meta["hashtags"]:
            self.assertNotIn("#", tag)
            self.assertNotIn(" ", tag)

    def test_generation_failure_returns_none(self):
        from core import clip_metadata
        with mock.patch.object(clip_metadata, "_generate", side_effect=RuntimeError("boom")):
            self.assertIsNone(generate_clip_metadata(self._clip(), "Campaign"))

    def test_invalid_json_returns_none(self):
        from core import clip_metadata
        with mock.patch.object(clip_metadata, "_generate", return_value="not json"):
            self.assertIsNone(generate_clip_metadata(self._clip(), "Campaign"))

    def test_missing_title_falls_back_to_hook(self):
        from core import clip_metadata
        payload = {"caption": "cap", "cta": "cta", "hashtags": ["a"], "hook_text": "hook"}
        with mock.patch.object(clip_metadata, "_generate", return_value=json.dumps(payload)):
            meta = generate_clip_metadata(self._clip(), "Campaign")
        self.assertEqual(meta["title"], "Nobody tells you this secret.")

    def test_no_campaign_name_is_fine(self):
        from core import clip_metadata
        payload = {"title": "t", "caption": "c", "cta": "cta", "hashtags": ["a"], "hook_text": "h"}
        with mock.patch.object(clip_metadata, "_generate", return_value=json.dumps(payload)):
            meta = generate_clip_metadata(self._clip(), "")
        self.assertEqual(meta["title"], "t")


if __name__ == "__main__":
    unittest.main()
