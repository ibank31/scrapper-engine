import json
import os
import unittest
from unittest import mock

from core.semantic_ranker import _normalize_model_results, rank_candidates, rank_candidates_with_metadata


class SemanticRankerTest(unittest.TestCase):
    def test_evaluation_corpus_decisions_and_risks(self):
        path = os.path.join(os.path.dirname(__file__), "fixtures", "semantic_cases.json")
        with open(path, encoding="utf-8") as fh:
            cases = json.load(fh)
        for case in cases:
            result = rank_candidates([case["candidate"]], case["plan"])[0]["semantic"]
            self.assertEqual(result["decision"], case["expected_decision"], case["id"])
            if case.get("expected_risk"):
                self.assertIn(case["expected_risk"], result["risks"], case["id"])

    def test_rejects_short_mid_thought_candidate(self):
        plan = {"production": {"topic_terms": ["business"]}}
        candidates = [{"rank": 1, "start": 0, "end": 5.4, "duration": 5.4, "text": "They're gonna guide you to become that future"}]
        result = rank_candidates(candidates, plan)[0]
        self.assertEqual(result["semantic"]["decision"], "reject")
        self.assertIn("short_clip", result["semantic"]["risks"])

    def test_fallback_runtime_is_explicit(self):
        previous = os.environ.get("CLIPPER_SEMANTIC_ENABLED")
        os.environ["CLIPPER_SEMANTIC_ENABLED"] = "false"
        try:
            ranked, runtime = rank_candidates_with_metadata(
                [{"rank": 1, "start": 0, "end": 20, "duration": 20, "text": "A complete business lesson."}],
                {"production": {"topic_terms": ["business"]}},
            )
        finally:
            if previous is None:
                os.environ.pop("CLIPPER_SEMANTIC_ENABLED", None)
            else:
                os.environ["CLIPPER_SEMANTIC_ENABLED"] = previous
        self.assertEqual(runtime["engine"], "deterministic")
        self.assertTrue(runtime["fallback_used"])
        self.assertEqual(runtime["fallback_reason"], "model_disabled_or_path_missing")
        self.assertEqual(ranked[0]["semantic"]["fallback_reason"], runtime["fallback_reason"])

    def test_normalizes_single_model_result_without_rank(self):
        candidates = [{"rank": 1, "start": 0, "end": 20, "duration": 20, "text": "A complete point."}]
        normalized, reason = _normalize_model_results({"decision": "render", "semantic_score": 80}, candidates)
        self.assertIsNone(reason)
        self.assertEqual(normalized[0]["rank"], 1)

    def test_model_cannot_override_local_structural_gate(self):
        candidate = {"rank": 1, "start": 0, "end": 4, "duration": 4, "text": "And this is unfinished"}
        plan = {"production": {"max_duration_seconds": 5}}
        with mock.patch("core.semantic_ranker._model_rank", return_value=([{"rank": 1, "decision": "render", "semantic_score": 99, "hook_score": 99, "context_score": 99, "payoff_score": 99, "completeness_score": 99, "campaign_relevance": "pass", "reason": "model", "risks": []}], None)):
            result = rank_candidates_with_metadata([candidate], plan)[0][0]
        self.assertEqual(result["semantic"]["decision"], "reject")
        self.assertIn("unfinished_sentence", result["semantic"]["risks"])

    def test_prefers_complete_problem_solution_candidate(self):
        plan = {"production": {"topic_terms": ["business"]}}
        candidates = [
            {"rank": 1, "start": 0, "end": 36, "duration": 36, "text": "Here is the biggest mistake in business. Most people ignore the problem, but the answer is to simplify the process. That means you can repeat it every week."},
            {"rank": 2, "start": 40, "end": 65, "duration": 25, "text": "And then we kept going until the end"},
        ]
        result = rank_candidates(candidates, plan)
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(result[0]["semantic"]["decision"], "render")
        self.assertGreaterEqual(result[0]["semantic"]["payoff_score"], 80)

    def test_campaign_max_duration_is_not_ignored_by_fallback(self):
        plan = {"production": {"max_duration_seconds": 5}}
        candidates = [{"rank": 1, "start": 0, "end": 5, "duration": 5, "text": "Complete point for the campaign."}]
        result = rank_candidates(candidates, plan)[0]
        self.assertNotEqual(result["semantic"]["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
