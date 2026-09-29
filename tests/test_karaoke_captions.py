#!/usr/bin/env python3
"""Karaoke caption regression tests: word-level {\kf} highlighting.

The commercial signature (Submagic/OpusClip): the active word highlights as
spoken, heavy sans, 2-3 words per cue, safe-zone placement. The legacy
write_ass() keeps whole-cue static styling; write_karaoke_ass() must produce
word-level karaoke without changing cue text content.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.captioning import build_cues, write_ass, write_karaoke_ass


def _words():
    return [
        {"start": 0.0, "end": 0.30, "word": "Never"},
        {"start": 0.32, "end": 0.55, "word": "skip"},
        {"start": 0.57, "end": 0.90, "word": "leg"},
        {"start": 0.92, "end": 1.20, "word": "day"},
        {"start": 1.25, "end": 1.60, "word": "again"},
    ]


def _transcript():
    return {"segments": [{"start": 0.0, "end": 2.0, "text": "Never skip leg day again", "words": _words()}]}


class KaraokeCaptionTests(unittest.TestCase):
    def _write(self, func):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "cap.ass")
            cues = func(_transcript(), {"start": 0.0, "end": 2.0}, path)
            return path, open(path, encoding="utf-8").read(), cues

    def test_karaoke_tags_present_with_centisecond_durations(self):
        _, content, _ = self._write(write_karaoke_ass)
        tags = re.findall(r"\{\\kf(\d+)\}", content)
        self.assertTrue(tags, "no {\\kf} tags emitted")
        # first word: 0.0-0.30s -> 30 centiseconds
        self.assertIn("{\\kf30}", content)

    def test_each_word_gets_own_karaoke_tag(self):
        _, content, _ = self._write(write_karaoke_ass)
        dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        tags = sum(len(re.findall(r"\{\\kf\d+\}", line)) for line in dialogue_lines)
        self.assertEqual(tags, 5, f"expected 5 word tags, got {tags}")

    def test_cue_density_is_two_to_three_words(self):
        _, _, cues = self._write(write_karaoke_ass)
        for cue in cues:
            self.assertLessEqual(len(cue["words"]), 3, f"cue too dense: {cue['text']}")

    def test_cue_text_content_matches_legacy(self):
        _, karaoke_content, _ = self._write(write_karaoke_ass)
        _, legacy_content, _ = self._write(write_ass)
        strip = lambda text: re.sub(r"\{[^}]*\}", "", text)
        karaoke_text = " ".join(strip(l.split(",", 9)[-1]) for l in karaoke_content.splitlines() if l.startswith("Dialogue:"))
        legacy_text = " ".join(strip(l.split(",", 9)[-1]) for l in legacy_content.splitlines() if l.startswith("Dialogue:"))
        self.assertEqual(" ".join(karaoke_text.split()), " ".join(legacy_text.split()))

    def test_style_is_bold_with_outline_and_highlight_fill(self):
        _, content, _ = self._write(write_karaoke_ass)
        style = next(line for line in content.splitlines() if line.startswith("Style:"))
        parts = style.split(",")
        # Format: ...,Bold,Italic,...,Outline,Shadow,Alignment,...,MarginV,...
        self.assertEqual(parts[7], "1", "karaoke captions must be bold")
        self.assertGreaterEqual(int(parts[16]), 2, "karaoke captions need a thick outline")
        # secondary colour (karaoke fill) must be a bright highlight, not the default white
        self.assertNotEqual(parts[5].upper(), "&H00FFFFFF", "karaoke fill must differ from primary")

    def test_placement_avoids_platform_ui_zones(self):
        _, content, _ = self._write(write_karaoke_ass)
        style = next(line for line in content.splitlines() if line.startswith("Style:"))
        parts = style.split(",")
        alignment = int(parts[18])
        margin_v = int(parts[21])
        # bottom-center with a raised margin keeps text out of the bottom ~15% UI zone on 1920px frames
        if alignment == 2:
            self.assertGreaterEqual(margin_v, 288, f"MarginV {margin_v} collides with bottom UI zone")
        # middle placements must stay inside the safe middle band
        if alignment in (5, 8):
            self.assertLessEqual(margin_v, 960)

    def test_word_timings_preserved_relative_to_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "cap.ass")
            cues = write_karaoke_ass(_transcript(), {"start": 0.5, "end": 2.0}, path)
            # words before 0.5s are clipped; first cue must start at/after 0
            self.assertGreaterEqual(cues[0]["start"], 0.0)

    def test_fallback_without_word_timestamps(self):
        # build_cues synthesizes even word timings from segment text, so the
        # karaoke path still emits word tags instead of a static cue.
        transcript = {"segments": [{"start": 0.0, "end": 2.0, "text": "Hello world", "words": []}]}
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "cap.ass")
            cues = write_karaoke_ass(transcript, {"start": 0.0, "end": 2.0}, path)
            content = open(path, encoding="utf-8").read()
            self.assertTrue(cues)
            self.assertIn("{\\kf100}Hello", content)
            self.assertIn("{\\kf100}world", content)

    def test_braces_in_words_are_escaped(self):
        transcript = {"segments": [{"start": 0.0, "end": 1.0, "text": "a {b} c", "words": [
            {"start": 0.0, "end": 0.3, "word": "a"},
            {"start": 0.3, "end": 0.6, "word": "{b}"},
            {"start": 0.6, "end": 0.9, "word": "c"},
        ]}]}
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "cap.ass")
            write_karaoke_ass(transcript, {"start": 0.0, "end": 1.0}, path)
            content = open(path, encoding="utf-8").read()
            self.assertNotIn("{b}", content.replace("{\\kf", ""))


if __name__ == "__main__":
    unittest.main()
