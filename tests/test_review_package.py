#!/usr/bin/env python3
"""Chat review package regression tests.

Stage 4: the machine produces the best clips, Punny sends the video straight
to chat with campaign, duration, English caption, CTA, hashtags, and rule
notes. Sorti replies approve/reject, and the decision is recorded. The package
must pace delivery (never flood chat) and must never auto-publish.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.review_package import build_review_package, format_chat_message


def _render_dir(temp: str, clips: int = 3) -> str:
    out = os.path.join(temp, "renders")
    os.makedirs(out, exist_ok=True)
    for rank in range(1, clips + 1):
        open(os.path.join(out, f"clip-{rank:03d}.mp4"), "wb").write(b"fake-video")
        meta = {"title": f"Title {rank}", "caption": f"Caption {rank}.",
                "cta": f"CTA {rank}.", "hashtags": ["tag1", "tag2"],
                "hook_text": f"Hook {rank}."}
        json.dump(meta, open(os.path.join(out, f"clip-{rank:03d}-meta.json"), "w"))
    return out


class ReviewPackageTests(unittest.TestCase):
    def test_package_collects_clips_with_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            package = build_review_package(_render_dir(temp), campaign_name="Demo Campaign")
            self.assertEqual(len(package["clips"]), 3)
            clip = package["clips"][0]
            self.assertEqual(clip["rank"], 1)
            self.assertEqual(clip["title"], "Title 1")
            self.assertTrue(clip["video_path"].endswith("clip-001.mp4"))
            self.assertEqual(package["campaign_name"], "Demo Campaign")

    def test_package_paces_into_batches(self):
        with tempfile.TemporaryDirectory() as temp:
            package = build_review_package(_render_dir(temp, clips=5), max_clips_per_batch=2)
            self.assertEqual(len(package["batches"]), 3)
            self.assertEqual([len(b) for b in package["batches"]], [2, 2, 1])

    def test_clips_without_meta_still_included(self):
        with tempfile.TemporaryDirectory() as temp:
            out = _render_dir(temp, clips=1)
            os.remove(os.path.join(out, "clip-001-meta.json"))
            package = build_review_package(out)
            self.assertEqual(len(package["clips"]), 1)
            self.assertIsNone(package["clips"][0]["title"])

    def test_empty_render_dir_gives_empty_package(self):
        with tempfile.TemporaryDirectory() as temp:
            package = build_review_package(os.path.join(temp, "empty"))
            self.assertEqual(package["clips"], [])
            self.assertEqual(package["batches"], [])

    def test_chat_message_contains_required_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            package = build_review_package(
                _render_dir(temp, clips=1), campaign_name="Demo Campaign",
                rule_notes=["No medical claims", "Keep original audio"])
            message = format_chat_message(package, batch_index=0)
            for expected in ["Demo Campaign", "Title 1", "Caption 1.", "CTA 1.",
                             "#tag1", "#tag2", "No medical claims", "Keep original audio"]:
                self.assertIn(expected, message, f"missing: {expected}")

    def test_chat_message_never_mentions_auto_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            package = build_review_package(_render_dir(temp, clips=1))
            message = format_chat_message(package, batch_index=0).lower()
            self.assertNotIn("auto-publish", message)
            self.assertNotIn("published", message)

    def test_chat_message_asks_for_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            package = build_review_package(_render_dir(temp, clips=1))
            message = format_chat_message(package, batch_index=0).lower()
            self.assertIn("setuju", message)

    def test_package_json_is_written(self):
        with tempfile.TemporaryDirectory() as temp:
            out = _render_dir(temp, clips=1)
            package = build_review_package(out)
            saved = os.path.join(out, "review-package.json")
            self.assertTrue(os.path.exists(saved))
            loaded = json.load(open(saved, encoding="utf-8"))
            self.assertEqual(len(loaded["clips"]), 1)


if __name__ == "__main__":
    unittest.main()
