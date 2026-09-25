import json
import os
import tempfile
import unittest
from unittest import mock

from core.clip_candidates import segment_transcript, select_candidates


class ClipCandidatesTest(unittest.TestCase):
    def test_word_timestamps_form_sentence_units_at_punctuation_and_pauses(self):
        transcript = {"segments": [{"start": 0, "end": 5, "words": [
            {"start": 0, "end": 1, "word": "Here"},
            {"start": 1, "end": 2, "word": "is"},
            {"start": 2, "end": 3, "word": "the"},
            {"start": 3, "end": 4, "word": "lesson."},
            {"start": 5.5, "end": 6.5, "word": "Now"},
            {"start": 6.5, "end": 7.5, "word": "we"},
            {"start": 7.5, "end": 8.5, "word": "apply"},
        ]}]}
        units = segment_transcript(transcript)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0]["text"], "Here is the lesson.")
        self.assertEqual(units[1]["text"], "Now we apply")

    def test_selects_ranked_non_overlapping_windows(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 10, "text": "Here is the biggest mistake because most people miss the problem."},
                {"start": 10, "end": 25, "text": "The solution is simple and the result is 50 percent better."},
                {"start": 25, "end": 40, "text": "First, follow this step and finally measure the result."},
                {"start": 80, "end": 95, "text": "A short unrelated sentence."},
            ]
        }
        candidates = select_candidates(transcript, min_seconds=20, max_seconds=60, limit=5)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rank"], 1)
        self.assertGreaterEqual(candidates[0]["score"], 0)
        self.assertTrue(candidates[0]["end"] <= 60)

    def test_bounds_long_punctuation_free_whisper_run_to_editorial_window(self):
        words = []
        for index in range(90):
            start = index * 0.5
            words.append({"start": start, "end": start + 0.45, "word": "business" if index % 5 else "because"})
        transcript = {"segments": [{"start": 0, "end": 45, "words": words}]}
        candidates = select_candidates(transcript, min_seconds=20, max_seconds=35, limit=3)
        self.assertTrue(candidates)
        self.assertTrue(all(20 <= item["duration"] <= 35 for item in candidates))

    def test_rewards_complete_payoff_over_keyword_only_excerpt(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 10, "text": "Here is the secret most people ask about?"},
                {"start": 10, "end": 24, "text": "The answer is to simplify the process."},
                {"start": 24, "end": 40, "text": "So that means you can repeat it every week."},
                {"start": 50, "end": 60, "text": "Here is the biggest mistake."},
                {"start": 60, "end": 70, "text": "Most people miss it."},
            ]
        }
        candidates = select_candidates(transcript, min_seconds=20, max_seconds=45, limit=5)
        self.assertTrue(candidates)
        self.assertIn("payoff or takeaway", candidates[0]["reasons"])
        self.assertIn("complete ending", candidates[0]["reasons"])

    def test_short_source_can_still_produce_a_candidate(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 2.5, "text": "This is the key lesson."},
                {"start": 2.5, "end": 5.0, "text": "So you can repeat it every week."},
            ]
        }
        candidates = select_candidates(transcript, min_seconds=3, max_seconds=60, limit=2)
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(candidates[0]["duration"], 5.0)

    def test_bridges_short_pause_but_not_long_silence(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 8, "text": "Here is the first part of the business lesson."},
                {"start": 10, "end": 18, "text": "The answer is to simplify the process."},
                {"start": 30, "end": 45, "text": "Unrelated later segment."},
            ]
        }
        candidates = select_candidates(transcript, min_seconds=15, max_seconds=20, limit=2)
        self.assertEqual(len(candidates), 2)
        self.assertIn((0.0, 18.0), {(item["start"], item["end"]) for item in candidates})
        self.assertNotIn((0.0, 45.0), {(item["start"], item["end"]) for item in candidates})

    def test_evaluation_corpus_has_expected_candidate_shapes(self):
        path = os.path.join(os.path.dirname(__file__), "fixtures", "semantic_cases.json")
        with open(path, encoding="utf-8") as fh:
            cases = json.load(fh)
        self.assertGreaterEqual(len(cases), 4)
        self.assertTrue(all(case.get("candidate", {}).get("text") for case in cases))

    def test_visual_fallback_handles_non_speech_source_when_subtitles_are_optional(self):
        transcript = {"segments": []}
        with tempfile.NamedTemporaryFile() as source, mock.patch(
            "core.clip_candidates.source_quality_preflight",
            return_value={"available": True, "duration_seconds": 90, "duplicate_hash": "abc"},
        ), mock.patch(
            "core.clip_candidates.candidate_signals",
            return_value={"available": True, "scene_change": {"available": True, "scene_change_score": 0.8}},
        ):
            candidates = select_candidates(
                transcript,
                min_seconds=10,
                max_seconds=45,
                limit=2,
                source_path=source.name,
                plan={"production": {"subtitle_required": False}},
            )
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(10 <= item["duration"] <= 45 for item in candidates))
        self.assertIn("visual fallback", candidates[0]["reasons"][0])

    def test_media_adjustment_does_not_change_candidate_interval(self):
        transcript = {"segments": [
            {"start": 0, "end": 10, "text": "Here is the biggest business problem."},
            {"start": 10, "end": 25, "text": "The answer is a complete solution."},
        ]}
        with tempfile.NamedTemporaryFile() as source, mock.patch("core.clip_candidates.source_quality_preflight", return_value={"available": True}), mock.patch(
            "core.clip_candidates.candidate_signals",
            return_value={"available": True, "silence_voice_activity": {"available": True, "silence_ratio": 0.7}, "scene_change": {"available": True, "scene_change_score": 0.0}},
        ):
            candidates = select_candidates(transcript, min_seconds=20, max_seconds=30, limit=1, source_path=source.name)
        self.assertEqual((candidates[0]["start"], candidates[0]["end"]), (0.0, 25.0))
        self.assertEqual(candidates[0]["media_score_adjustment"], -0.12)


if __name__ == "__main__":
    unittest.main()
