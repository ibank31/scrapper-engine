#!/usr/bin/env python3
"""Gemini multimodal keyframe check regression tests.

For top candidates, Gemini actually *looks* at 3 frames (start/middle/end) and
returns a visual verdict. This is a verification signal only: it never changes
timestamps, never rejects a candidate, and any failure yields None.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.visual_moment import extract_keyframes, visual_verdict


def _make_video(path: str, seconds: float = 6.0) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x224466:s=640x360:d={seconds}:r=30",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


class VisualMomentTests(unittest.TestCase):
    def test_extract_keyframes_returns_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            video = os.path.join(temp, "src.mp4")
            _make_video(video)
            frames = extract_keyframes(video, 1.0, 5.0, count=3, out_dir=temp)
            self.assertEqual(len(frames), 3)
            for frame in frames:
                self.assertTrue(os.path.exists(frame), f"missing {frame}")
                self.assertGreater(os.path.getsize(frame), 0)

    def test_extract_keyframes_clamps_to_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            video = os.path.join(temp, "src.mp4")
            _make_video(video, seconds=4.0)
            frames = extract_keyframes(video, 0.0, 60.0, count=3, out_dir=temp)
            self.assertEqual(len(frames), 3)

    def test_extract_keyframes_failure_returns_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(extract_keyframes("/nonexistent/video.mp4", 0, 10, out_dir=temp), [])

    def test_verdict_normalizes_valid_response(self):
        from core import visual_moment
        payload = {"on_topic": True, "face_visible": False, "readable_text": True,
                   "visual_notes": "talking head, clean background"}
        with tempfile.TemporaryDirectory() as temp:
            frames = [os.path.join(temp, f"f{i}.jpg") for i in range(2)]
            for frame in frames:
                open(frame, "wb").write(b"\xff\xd8\xff\xd9")
            with mock.patch.object(visual_moment, "_generate_parts", return_value=json.dumps(payload)):
                verdict = visual_verdict(frames, "property campaign")
        self.assertTrue(verdict["on_topic"])
        self.assertFalse(verdict["face_visible"])
        self.assertEqual(verdict["visual_notes"], "talking head, clean background")

    def test_verdict_failure_returns_none(self):
        from core import visual_moment
        with tempfile.TemporaryDirectory() as temp:
            frame = os.path.join(temp, "f.jpg")
            open(frame, "wb").write(b"\xff\xd8\xff\xd9")
            with mock.patch.object(visual_moment, "_generate_parts", side_effect=RuntimeError("boom")):
                self.assertIsNone(visual_verdict([frame], "campaign"))

    def test_verdict_invalid_json_returns_none(self):
        from core import visual_moment
        with tempfile.TemporaryDirectory() as temp:
            frame = os.path.join(temp, "f.jpg")
            open(frame, "wb").write(b"\xff\xd8\xff\xd9")
            with mock.patch.object(visual_moment, "_generate_parts", return_value="nope"):
                self.assertIsNone(visual_verdict([frame], "campaign"))

    def test_verdict_with_no_frames_returns_none(self):
        self.assertIsNone(visual_verdict([], "campaign"))

    def test_verdict_never_rejects(self):
        # The verdict is advisory; the module must not expose a reject decision.
        from core import visual_moment
        payload = {"on_topic": False, "face_visible": False, "readable_text": False, "visual_notes": "off topic"}
        with tempfile.TemporaryDirectory() as temp:
            frame = os.path.join(temp, "f.jpg")
            open(frame, "wb").write(b"\xff\xd8\xff\xd9")
            with mock.patch.object(visual_moment, "_generate_parts", return_value=json.dumps(payload)):
                verdict = visual_verdict([frame], "campaign")
        self.assertNotIn("decision", verdict)
        self.assertNotIn("reject", json.dumps(verdict))


if __name__ == "__main__":
    unittest.main()
