import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core.media_signals import candidate_signals, media_score_adjustment, source_quality_preflight


class MediaSignalsTest(unittest.TestCase):
    def test_fixture_speaker_heuristics(self):
        path = os.path.join(os.path.dirname(__file__), "fixtures", "media_signal_cases.json")
        with open(path, encoding="utf-8") as fh:
            cases = json.load(fh)
        for case in cases:
            result = candidate_signals(None, case["candidate"], case["transcript"])
            self.assertEqual(result["active_speaker"]["framing_recommendation"], case["expected_framing"], case["id"])

    def test_missing_source_is_explicitly_unavailable(self):
        result = candidate_signals("/does/not/exist.mp4", {"start": 0, "duration": 10}, None)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "source_unavailable")

    def test_preflight_records_audio_resolution_hash_and_density(self):
        with tempfile.NamedTemporaryFile() as fh:
            fh.write(b"fixture media")
            fh.flush()
            probe = {"streams": [{"codec_type": "video", "width": 1920, "height": 1080}, {"codec_type": "audio", "codec_name": "aac"}], "format": {"duration": "20"}}
            transcript = {"segments": [{"text": "one two three four five"}]}
            with patch("core.media_signals._probe", return_value=probe):
                result = source_quality_preflight(fh.name, transcript)
        self.assertTrue(result["available"])
        self.assertTrue(result["has_audio"])
        self.assertEqual(result["resolution_class"], "hd")
        self.assertEqual(result["speech_density_words_per_second"], 0.25)
        self.assertTrue(result["duplicate_hash"])
        self.assertTrue(result["has_video"])

    def test_media_score_adjustment_is_bounded_and_advisory(self):
        delta, reasons = media_score_adjustment({
            "available": True,
            "silence_voice_activity": {"available": True, "silence_ratio": 0.7},
            "scene_change": {"available": True, "scene_change_score": 0.8},
        })
        self.assertEqual(delta, -0.08)
        self.assertIn("high silence ratio", reasons)

    def test_unavailable_media_has_no_score_adjustment(self):
        self.assertEqual(media_score_adjustment({"available": False}), (0.0, []))


if __name__ == "__main__":
    unittest.main()
