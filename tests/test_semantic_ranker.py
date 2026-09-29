import json
import os
import unittest
from unittest import mock

from core.semantic_ranker import _normalize_model_results, rank_candidates, rank_candidates_with_metadata, rank_global_candidates, semantic_model_decision


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
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "deterministic", "CLIPPER_SEMANTIC_ENABLED": "true"}):
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

    def test_normalizes_single_model_result_with_mismatched_model_rank(self):
        candidate = {"rank": 7, "candidate_id": "c7"}
        parsed = {"results": [{
            "rank": 1, "decision": "render", "semantic_score": 80,
            "hook_score": 80, "context_score": 80, "payoff_score": 80,
            "completeness_score": 80, "campaign_relevance": "pass",
            "reason": "ok", "risks": []
        }]}
        normalized, reason = _normalize_model_results(parsed, [candidate])
        self.assertIsNone(reason)
        self.assertEqual(normalized[0]["rank"], 7)

    def test_normalizes_single_model_result_without_rank(self):
        candidates = [{"rank": 1, "start": 0, "end": 20, "duration": 20, "text": "A complete point."}]
        normalized, reason = _normalize_model_results({"decision": "render", "semantic_score": 80, "hook_score": 80, "context_score": 80, "payoff_score": 80, "completeness_score": 80, "campaign_relevance": "pass", "reason": "complete", "risks": []}, candidates)
        self.assertIsNone(reason)
        self.assertEqual(normalized[0]["rank"], 1)

    def test_model_cannot_override_local_structural_gate(self):
        candidate = {"rank": 1, "start": 0, "end": 4, "duration": 4, "text": "And this is unfinished"}
        plan = {"production": {"max_duration_seconds": 5}}
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "qwen", "CLIPPER_SEMANTIC_ENABLED": "true"}):
            with mock.patch("core.semantic_ranker._model_rank", return_value=([{"rank": 1, "decision": "render", "semantic_score": 99, "hook_score": 99, "context_score": 99, "payoff_score": 99, "completeness_score": 99, "campaign_relevance": "pass", "reason": "model", "risks": []}], None)):
                result = rank_candidates_with_metadata([candidate], plan)[0][0]
        self.assertEqual(result["semantic"]["decision"], "reject")
        self.assertIn("unfinished_sentence", result["semantic"]["risks"])
        self.assertTrue(result["semantic"]["hard_policy_gate"])

    def test_model_only_reject_is_not_a_hard_policy_gate(self):
        candidate = {"rank": 1, "start": 0, "end": 20, "duration": 20, "text": "A complete point for review."}
        plan = {"production": {"topic_terms": ["business"]}}
        model_result = [{"rank": 1, "decision": "reject", "semantic_score": 20, "hook_score": 20, "context_score": 20, "payoff_score": 20, "completeness_score": 20, "campaign_relevance": "fail", "reason": "model concern", "risks": ["model_concern"]}]
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "qwen", "CLIPPER_SEMANTIC_ENABLED": "true"}):
            with mock.patch("core.semantic_ranker._model_rank", return_value=(model_result, None)):
                result = rank_candidates_with_metadata([candidate], plan)[0][0]
        self.assertEqual(result["semantic"]["decision"], "reject")
        self.assertFalse(result["semantic"]["hard_policy_gate"])

    def test_malformed_model_decision_triggers_fallback(self):
        candidate = {"rank": 1, "start": 0, "end": 20, "duration": 20, "text": "A complete business lesson."}
        parsed = {"decision": None, "semantic_score": 90, "hook_score": 90, "context_score": 90, "payoff_score": 90, "completeness_score": 90, "campaign_relevance": "pass", "reason": "", "risks": []}
        normalized, reason = _normalize_model_results(parsed, [candidate])
        self.assertIsNone(normalized)
        self.assertEqual(reason, "model_invalid_decision")
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "deterministic", "CLIPPER_SEMANTIC_ENABLED": "true"}):
            ranked, runtime = rank_candidates_with_metadata([candidate], {"production": {"topic_terms": ["business"]}})
        self.assertEqual(runtime["engine"], "deterministic")
        self.assertIsNotNone(ranked[0]["semantic"]["decision"])

    def test_prefers_complete_problem_solution_candidate(self):
        plan = {"production": {"topic_terms": ["business"]}}
        candidates = [
            {"rank": 1, "start": 0, "end": 36, "duration": 36, "text": "Here is the biggest mistake in business. Most people ignore the problem, but the answer is to simplify the process. That means you can repeat it every week."},
            {"rank": 2, "start": 40, "end": 65, "duration": 25, "text": "And then we kept going until the end"},
        ]
        result = None
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "deterministic", "CLIPPER_SEMANTIC_ENABLED": "true"}):
            result = rank_candidates(candidates, plan)
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(result[0]["semantic"]["decision"], "render")
        self.assertGreaterEqual(result[0]["semantic"]["payoff_score"], 80)

    def test_campaign_max_duration_is_not_ignored_by_fallback(self):
        plan = {"production": {"max_duration_seconds": 5}}
        candidates = [{"rank": 1, "start": 0, "end": 5, "duration": 5, "text": "Complete point for the campaign."}]
        result = rank_candidates(candidates, plan)[0]
        self.assertNotEqual(result["semantic"]["decision"], "reject")


    def test_global_gate_skips_semantic_ai_for_clear_pair(self):
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_ENABLED": "auto"}):
            plan = {
                "ai_rules": {"confidence": 0.95},
                "output_contract": {"tier_allocation": {"tier_1": 1, "tier_2": 1}},
            }
            candidates = [
                {
                    "candidate_id": "t1-a",
                    "tier": "tier_1",
                    "source_asset_id": "source-a",
                    "source_hash": "hash-a",
                    "transcript_hash": "tx-a",
                    "start": 0,
                    "end": 32,
                    "duration": 32,
                    "score": 0.92,
                    "text": "Here is the clearest business lesson with a complete payoff.",
                    "reasons": ["clear opening beat", "complete ending", "payoff or takeaway"],
                },
                {
                    "candidate_id": "t2-b",
                    "tier": "tier_2",
                    "source_asset_id": "source-b",
                    "source_hash": "hash-b",
                    "transcript_hash": "tx-b",
                    "start": 40,
                    "end": 72,
                    "duration": 32,
                    "score": 0.90,
                    "text": "The strongest secondary audience example with a complete payoff.",
                    "reasons": ["clear opening beat", "complete ending", "payoff or takeaway"],
                },
            ]
            with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_ENABLED": "auto"}, clear=False):
                self.assertEqual(semantic_model_decision(candidates, plan, 15), (False, "deterministic_confident"))
            with mock.patch("core.semantic_ranker._model_rank", side_effect=AssertionError("semantic model should be skipped")):
                ranked, runtime = rank_global_candidates(candidates, plan, 15)
            self.assertEqual(runtime["decision"], "semantic_skipped")
            self.assertEqual(runtime["decision_reason"], "deterministic_confident")
            self.assertEqual(len(ranked), 2)

    def test_global_semantic_required_evaluates_full_pool(self):
        plan = {
            "ai_rules": {"confidence": 0.95},
            "output_contract": {"tier_allocation": {"tier_1": 1, "tier_2": 1}},
        }
        candidates = [
            {"candidate_id": f"c-{i}", "tier": "tier_1" if i < 6 else "tier_2", "source_asset_id": f"a-{i}", "source_hash": f"h-{i}", "start": i * 30, "end": i * 30 + 20, "duration": 20, "score": 0.90 - i * 0.001, "text": f"Business point {i}.", "_relevance_status": "uncertain"}
            for i in range(10)
        ]
        calls = []
        def fake_rank(items, plan):
            calls.append(items[0]["candidate_id"])
            item = dict(items[0])
            item["semantic"] = {"decision": "render", "semantic_score": 80, "hook_score": 80, "context_score": 80, "payoff_score": 80, "completeness_score": 80, "campaign_relevance": "pass", "reason": "model", "risks": []}
            item["score"] = 0.8
            return [item], {"schema_version": 1, "engine": "qwen", "fallback_used": False, "fallback_reason": None, "candidate_count": 1}
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_ENABLED": "true"}):
            with mock.patch("core.semantic_ranker.rank_candidates_with_metadata", side_effect=fake_rank):
                ranked, runtime = rank_global_candidates(candidates, plan, 2)
        self.assertEqual(len(calls), len(candidates))
        self.assertEqual(runtime["evaluated_count"], len(candidates))
        self.assertTrue(all(not item["semantic"].get("fallback_used") for item in ranked))

    def test_global_gate_keeps_semantic_ai_for_ambiguous_pair(self):
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_ENABLED": "auto"}):
            plan = {
                "ai_rules": {"confidence": 0.95},
                "output_contract": {"tier_allocation": {"tier_1": 1, "tier_2": 1}},
            }
            candidates = [
                {"candidate_id": "t1-a", "tier": "tier_1", "source_asset_id": "a", "start": 0, "end": 30, "duration": 30, "score": 0.74, "text": "Business point A."},
                {"candidate_id": "t1-b", "tier": "tier_1", "source_asset_id": "b", "start": 35, "end": 65, "duration": 30, "score": 0.70, "text": "Business point B."},
                {"candidate_id": "t2-a", "tier": "tier_2", "source_asset_id": "c", "start": 70, "end": 100, "duration": 30, "score": 0.76, "text": "Secondary point A."},
                {"candidate_id": "t2-b", "tier": "tier_2", "source_asset_id": "d", "start": 105, "end": 135, "duration": 30, "score": 0.71, "text": "Secondary point B."},
            ]
            with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_ENABLED": "auto"}, clear=False):
                self.assertEqual(semantic_model_decision(candidates, plan, 15), (True, "close_output_ranking"))

    def test_global_gate_keeps_semantic_ai_for_uncertain_relevance(self):
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_ENABLED": "auto"}):
            plan = {
                "ai_rules": {"confidence": 0.95},
                "output_contract": {"tier_allocation": {"tier_1": 1, "tier_2": 1}},
            }
            candidates = [
                {"candidate_id": "t1", "tier": "tier_1", "source_asset_id": "a", "start": 0, "end": 30, "duration": 30, "score": 0.95, "text": "Clear complete point.", "_relevance_status": "uncertain"},
                {"candidate_id": "t2", "tier": "tier_2", "source_asset_id": "b", "start": 40, "end": 70, "duration": 30, "score": 0.94, "text": "Another clear complete point."},
            ]
            self.assertEqual(
                semantic_model_decision(candidates, plan, 15),
                (True, "ambiguous_campaign_relevance"),
            )

    def test_global_gate_requires_semantic_ai_when_campaign_confidence_is_missing(self):
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_ENABLED": "auto"}):
            plan = {
                "output_contract": {"tier_allocation": {"tier_1": 1, "tier_2": 1}},
            }
            candidates = [
                {"candidate_id": "t1", "tier": "tier_1", "source_asset_id": "a", "start": 0, "end": 30, "duration": 30, "score": 0.95, "text": "Clear complete point."},
                {"candidate_id": "t2", "tier": "tier_2", "source_asset_id": "b", "start": 40, "end": 70, "duration": 30, "score": 0.94, "text": "Another clear complete point."},
            ]
            self.assertEqual(
                semantic_model_decision(candidates, plan, 15),
                (True, "campaign_confidence_missing"),
            )


class GeminiProviderTests(unittest.TestCase):
    def _candidate(self):
        return {"rank": 1, "start": 0, "end": 20, "duration": 20,
                "text": "A complete business lesson with a clear payoff."}

    def _gemini_ok(self, candidates, plan):
        return ([{"rank": 1, "decision": "render", "semantic_score": 88,
                  "hook_score": 85, "context_score": 90, "payoff_score": 87,
                  "completeness_score": 92, "campaign_relevance": "pass",
                  "reason": "gemini", "risks": []}], None)

    def test_explicit_gemini_provider_uses_gemini_engine(self):
        plan = {"production": {"topic_terms": ["business"]}}
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key", "CLIPPER_SEMANTIC_ENABLED": "true"}):
            with mock.patch("core.semantic_ranker._gemini_rank", side_effect=self._gemini_ok):
                ranked, runtime = rank_candidates_with_metadata([self._candidate()], plan)
        self.assertEqual(runtime["engine"], "gemini")
        self.assertFalse(runtime["fallback_used"])
        self.assertEqual(ranked[0]["semantic"]["semantic_score"], 88)

    def test_gemini_failure_falls_back_to_qwen(self):
        plan = {"production": {"topic_terms": ["business"]}}
        qwen_result = ([{"rank": 1, "decision": "review", "semantic_score": 70,
                         "hook_score": 70, "context_score": 70, "payoff_score": 70,
                         "completeness_score": 70, "campaign_relevance": "uncertain",
                         "reason": "qwen", "risks": []}], None)
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "auto", "GEMINI_API_KEY": "test-key", "CLIPPER_SEMANTIC_ENABLED": "true"}):
            with mock.patch("core.semantic_ranker._gemini_rank", return_value=(None, "gemini_rank_failed:Timeout")):
                with mock.patch("core.semantic_ranker._model_rank", return_value=qwen_result):
                    ranked, runtime = rank_candidates_with_metadata([self._candidate()], plan)
        self.assertEqual(runtime["engine"], "qwen")
        self.assertFalse(runtime["fallback_used"])

    def test_all_providers_failing_yields_deterministic(self):
        plan = {"production": {"topic_terms": ["business"]}}
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "auto", "GEMINI_API_KEY": "test-key", "CLIPPER_SEMANTIC_ENABLED": "true"}):
            with mock.patch("core.semantic_ranker._gemini_rank", return_value=(None, "gemini down")):
                with mock.patch("core.semantic_ranker._model_rank", return_value=(None, "qwen down")):
                    ranked, runtime = rank_candidates_with_metadata([self._candidate()], plan)
        self.assertEqual(runtime["engine"], "deterministic")
        self.assertTrue(runtime["fallback_used"])
        self.assertIsNotNone(ranked[0]["semantic"]["decision"])

    def test_disabled_provider_skips_all_models(self):
        plan = {"production": {"topic_terms": ["business"]}}
        with mock.patch.dict(os.environ, {"CLIPPER_SEMANTIC_PROVIDER": "deterministic", "GEMINI_API_KEY": "test-key"}):
            with mock.patch("core.semantic_ranker._gemini_rank", side_effect=AssertionError("gemini should be skipped")):
                with mock.patch("core.semantic_ranker._model_rank", side_effect=AssertionError("qwen should be skipped")):
                    ranked, runtime = rank_candidates_with_metadata([self._candidate()], plan)
        self.assertEqual(runtime["engine"], "deterministic")
        self.assertTrue(runtime["fallback_used"])

    def test_gemini_rank_normalizes_valid_json(self):
        from core import semantic_ranker
        payload = {"results": [{"rank": 1, "decision": "review", "semantic_score": 75,
                                "hook_score": 72, "context_score": 78, "payoff_score": 74,
                                "completeness_score": 80, "campaign_relevance": "uncertain",
                                "reason": "ok", "risks": ["r1"]}]}
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with mock.patch("core.campaign_ai._gemini_generate_with_schema", return_value=json.dumps(payload)):
                results, reason = semantic_ranker._gemini_rank(
                    [self._candidate()], {"production": {"topic_terms": ["business"]}})
        self.assertIsNone(reason)
        self.assertEqual(results[0]["decision"], "review")
        self.assertEqual(results[0]["risks"], ["r1"])

    def test_gemini_rank_reports_missing_key(self):
        from core import semantic_ranker
        env = dict(os.environ)
        env.pop("GEMINI_API_KEY", None)
        with mock.patch.dict(os.environ, env, clear=True):
            results, reason = semantic_ranker._gemini_rank(
                [self._candidate()], {"production": {}})
        self.assertIsNone(results)
        self.assertEqual(reason, "gemini_api_key_missing")

    def test_gemini_virality_fields_preserved_and_clamped(self):
        from core import semantic_ranker
        payload = {"results": [{"rank": 1, "decision": "render", "semantic_score": 80,
                                "hook_score": 70, "context_score": 75, "payoff_score": 72,
                                "completeness_score": 78, "campaign_relevance": "pass",
                                "reason": "ok", "risks": [],
                                "hook_sentence": "Nobody tells you this secret.",
                                "hook_score_3s": 92, "virality_score": 120,
                                "emotion_score": 80, "conflict_score": 75,
                                "quotability_score": 88, "value_score": 70,
                                "shareability_score": -5}]}
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with mock.patch("core.campaign_ai._gemini_generate_with_schema", return_value=json.dumps(payload)):
                results, reason = semantic_ranker._gemini_rank(
                    [self._candidate()], {"production": {"topic_terms": ["business"]}})
        self.assertIsNone(reason)
        item = results[0]
        self.assertEqual(item["hook_sentence"], "Nobody tells you this secret.")
        self.assertEqual(item["hook_score_3s"], 92)
        self.assertEqual(item["virality_score"], 100.0, "scores must clamp to 0-100")
        self.assertEqual(item["shareability_score"], 0.0)
        self.assertEqual(item["quotability_score"], 88)

    def test_gemini_virality_fields_optional_for_backward_compat(self):
        from core import semantic_ranker
        payload = {"results": [{"rank": 1, "decision": "review", "semantic_score": 75,
                                "hook_score": 72, "context_score": 78, "payoff_score": 74,
                                "completeness_score": 80, "campaign_relevance": "uncertain",
                                "reason": "ok", "risks": []}]}
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with mock.patch("core.campaign_ai._gemini_generate_with_schema", return_value=json.dumps(payload)):
                results, reason = semantic_ranker._gemini_rank(
                    [self._candidate()], {"production": {"topic_terms": ["business"]}})
        self.assertIsNone(reason)
        self.assertEqual(results[0]["decision"], "review")
        self.assertNotIn("hook_sentence", results[0])

    def test_gemini_invalid_virality_types_are_dropped_not_fatal(self):
        from core import semantic_ranker
        payload = {"results": [{"rank": 1, "decision": "render", "semantic_score": 80,
                                "hook_score": 70, "context_score": 75, "payoff_score": 72,
                                "completeness_score": 78, "campaign_relevance": "pass",
                                "reason": "ok", "risks": [],
                                "hook_sentence": 123, "virality_score": "high"}]}
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with mock.patch("core.campaign_ai._gemini_generate_with_schema", return_value=json.dumps(payload)):
                results, reason = semantic_ranker._gemini_rank(
                    [self._candidate()], {"production": {"topic_terms": ["business"]}})
        self.assertIsNone(reason)
        self.assertNotIn("hook_sentence", results[0])
        self.assertNotIn("virality_score", results[0])



if __name__ == "__main__":
    unittest.main()
