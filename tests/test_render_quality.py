import os
import tempfile
import unittest

from core.captioning import build_cues, clean_words, is_emphasis_word, write_ass, write_srt
from core.clip_candidates import candidates_are_near_duplicates, select_distinct_candidates
from core.visual_crop import _piecewise
from modules.clipping.validate import editorial_checks


class RenderQualityTest(unittest.TestCase):
    def test_clean_words_removes_fillers_and_adjacent_duplicates(self):
        words = [
            {"start": 0, "end": 0.2, "word": "Um"},
            {"start": 0.2, "end": 0.5, "word": "I"},
            {"start": 0.5, "end": 0.8, "word": "I"},
            {"start": 0.8, "end": 1.1, "word": "worked"},
        ]
        self.assertEqual([w["word"] for w in clean_words(words)], ["I", "worked"])

    def test_cues_are_short(self):
        transcript = {"segments": [{"start": 0, "end": 8, "words": [
            {"start": i * 0.5, "end": i * 0.5 + 0.4, "word": word}
            for i, word in enumerate("I worked fifty one weeks out of fifty two weeks this year".split())
        ]}]}
        cues = build_cues(transcript, 0, 8, max_words=5, max_chars=30)
        self.assertTrue(cues)
        self.assertTrue(all(len(cue["text"].split()) <= 5 for cue in cues))
        self.assertTrue(all(len(cue["text"]) <= 30 for cue in cues))

    def test_srt_is_written(self):
        transcript = {"segments": [{"start": 0, "end": 2, "words": [
            {"start": 0, "end": 0.4, "word": "Hello"},
            {"start": 0.4, "end": 0.8, "word": "world"},
        ]}]}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "captions.srt")
            write_srt(transcript, {"start": 0, "end": 2}, path)
            self.assertIn("Hello world", open(path, encoding="utf-8").read())

    def test_ass_captions_have_safe_profile_and_limited_emphasis(self):
        transcript = {"segments": [{"start": 0, "end": 3, "words": [
            {"start": 0, "end": 0.7, "word": "This"},
            {"start": 0.7, "end": 1.4, "word": "is"},
            {"start": 1.4, "end": 2.1, "word": "a"},
            {"start": 2.1, "end": 3, "word": "free"},
        ]}]}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "captions.ass")
            write_ass(transcript, {"start": 0, "end": 3}, path)
            rendered = open(path, encoding="utf-8").read()
            self.assertIn("PlayResX: 1080", rendered)
            self.assertIn("&HE9A7FF&", rendered)
            self.assertIn("&HFFEB66&", rendered)
            self.assertIn("Fontsize, PrimaryColour", rendered)
            self.assertEqual(rendered.count("&HE9A7FF&"), 1)
        self.assertTrue(is_emphasis_word("free"))
        self.assertTrue(is_emphasis_word("$500"))
        self.assertFalse(is_emphasis_word("the"))

    def test_distinct_preview_filter_removes_overlapping_windows(self):
        first = {"source": "source-a.mp4", "start": 10, "end": 45, "score": 0.9, "text": "The big reveal is free and nobody expected it"}
        duplicate = {"source": "source-a.mp4", "start": 12, "end": 47, "score": 0.8, "text": "The big reveal is free and nobody expected it"}
        different = {"source": "source-a.mp4", "start": 60, "end": 95, "score": 0.7, "text": "Here is the lesson and the answer changes everything"}
        self.assertTrue(candidates_are_near_duplicates(first, duplicate))
        self.assertEqual(select_distinct_candidates([first, duplicate, different], 2), [first, different])

    def test_crop_expression_escapes_function_commas(self):
        expression = _piecewise([0, 10, 20], 2, 0)
        self.assertIn("\\,", expression)

    def test_editorial_gate_only_rejects_incomplete_short_clip_for_duration(self):
        issues = editorial_checks({"duration": 5.4, "text": "They're gonna help guide you"})
        self.assertTrue(any("too short" in issue for issue in issues))
        self.assertFalse(any("mid-thought" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
