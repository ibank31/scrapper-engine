import os
import tempfile
import unittest

from core.captioning import build_cues, clean_words, write_srt
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

    def test_crop_expression_escapes_function_commas(self):
        expression = _piecewise([0, 10, 20], 2, 0)
        self.assertIn("\\,", expression)

    def test_editorial_gate_rejects_incomplete_short_clip(self):
        issues = editorial_checks({"duration": 5.4, "text": "They're gonna help guide you"})
        self.assertTrue(any("too short" in issue for issue in issues))
        self.assertTrue(any("mid-thought" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
