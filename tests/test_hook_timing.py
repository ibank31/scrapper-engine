#!/usr/bin/env python3
"""Hook-first timing regression tests.

OpusClip's documented #1 defect is clips starting ~3s late, cutting the hook's
setup. pad_hook_start() moves the clip start earlier, snapped to a word
boundary so we never cut mid-word. trim_silence_edges() removes dead air at
clip edges using word timestamps. Neither may invent timestamps: every new
boundary comes from an actual word.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.hook_timing import candidate_words, pad_hook_start, trim_silence_edges


def _transcript():
    words = [
        {"start": 8.0, "end": 8.3, "word": "So"},
        {"start": 8.4, "end": 8.7, "word": "here"},
        {"start": 8.8, "end": 9.1, "word": "is"},
        {"start": 9.2, "end": 9.6, "word": "the"},
        {"start": 9.7, "end": 10.2, "word": "secret"},
        {"start": 10.5, "end": 11.0, "word": "Nobody"},
        {"start": 11.1, "end": 11.5, "word": "tells"},
        {"start": 11.6, "end": 12.0, "word": "you."},
    ]
    return {"segments": [{"start": 8.0, "end": 12.0, "text": "So here is the secret Nobody tells you.", "words": words}]}


class HookTimingTests(unittest.TestCase):
    def test_pad_moves_start_earlier_to_word_boundary(self):
        candidate = {"rank": 1, "start": 10.5, "end": 30.0, "duration": 19.5}
        adjusted, info = pad_hook_start(candidate, _transcript(), pad_seconds=2.0)
        # target 8.5 -> nearest word start at/after 8.5 within window is 8.8 ("is")
        self.assertEqual(adjusted["start"], 8.8)
        self.assertTrue(info["padded"])
        self.assertAlmostEqual(adjusted["duration"], 30.0 - 8.8, places=2)

    def test_pad_never_cuts_mid_word(self):
        candidate = {"rank": 1, "start": 10.5, "end": 30.0, "duration": 19.5}
        adjusted, _ = pad_hook_start(candidate, _transcript(), pad_seconds=1.0)
        words = candidate_words(_transcript(), 0.0, 30.0)
        starts = {round(w["start"], 2) for w in words}
        self.assertIn(round(adjusted["start"], 2), starts | {10.5})

    def test_pad_never_goes_below_zero(self):
        candidate = {"rank": 1, "start": 1.0, "end": 21.0, "duration": 20.0}
        adjusted, _ = pad_hook_start(candidate, _transcript(), pad_seconds=5.0)
        self.assertGreaterEqual(adjusted["start"], 0.0)

    def test_pad_respects_max_duration(self):
        candidate = {"rank": 1, "start": 10.5, "end": 30.0, "duration": 19.5}
        adjusted, info = pad_hook_start(candidate, _transcript(), pad_seconds=2.0, max_seconds=20.0)
        self.assertLessEqual(adjusted["duration"], 20.0 + 1e-6)

    def test_pad_noop_when_no_earlier_words(self):
        candidate = {"rank": 1, "start": 8.0, "end": 28.0, "duration": 20.0}
        adjusted, info = pad_hook_start(candidate, _transcript(), pad_seconds=2.0)
        self.assertEqual(adjusted["start"], 8.0)
        self.assertFalse(info["padded"])

    def test_pad_disabled_with_zero_seconds(self):
        candidate = {"rank": 1, "start": 10.5, "end": 30.0, "duration": 19.5}
        adjusted, info = pad_hook_start(candidate, _transcript(), pad_seconds=0.0)
        self.assertEqual(adjusted["start"], 10.5)
        self.assertFalse(info["padded"])

    def test_original_candidate_not_mutated(self):
        candidate = {"rank": 1, "start": 10.5, "end": 30.0, "duration": 19.5}
        pad_hook_start(candidate, _transcript(), pad_seconds=2.0)
        self.assertEqual(candidate["start"], 10.5)

    def test_trim_moves_edges_to_first_and_last_word(self):
        candidate = {"rank": 1, "start": 7.0, "end": 14.0, "duration": 7.0}
        adjusted, info = trim_silence_edges(candidate, _transcript())
        self.assertEqual(adjusted["start"], 8.0)
        self.assertEqual(adjusted["end"], 12.0)
        self.assertTrue(info["trimmed"])

    def test_trim_noop_when_edges_already_tight(self):
        candidate = {"rank": 1, "start": 8.0, "end": 12.0, "duration": 4.0}
        adjusted, info = trim_silence_edges(candidate, _transcript())
        self.assertEqual(adjusted["start"], 8.0)
        self.assertEqual(adjusted["end"], 12.0)
        self.assertFalse(info["trimmed"])

    def test_trim_noop_without_words(self):
        candidate = {"rank": 1, "start": 7.0, "end": 14.0, "duration": 7.0}
        adjusted, info = trim_silence_edges(candidate, {"segments": []})
        self.assertEqual(adjusted["start"], 7.0)
        self.assertFalse(info["trimmed"])


if __name__ == "__main__":
    unittest.main()
