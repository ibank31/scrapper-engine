import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from core import campaign_ai
from core.campaign_ai import normalize_ai_result, rules_fingerprint
from core.campaign_evidence import build_evidence_ledger, source_fingerprint, verify_ai_evidence
from worker.sync_campaigns import _cache_is_current, _headers


def valid_payload(campaign_ids=("c-1",)):
    return {"campaigns": [{
        "campaign_id": cid,
        "campaign_fit": {"score": 0.9, "label": "high", "reason": "matches"},
        "rules": {
            "source_policy": "campaign_defined", "platforms": ["tiktok"], "aspect_ratio": "9:16",
            "min_duration_seconds": 15, "max_duration_seconds": 45, "subtitle_required": False,
            "subtitle_style": "campaign_defined", "watermark_required": False,
            "third_party_watermark_allowed": False, "official_audio_required": False,
            "cta_required": False, "cta_text": None, "handles": [], "hashtags": [],
            "disclosures": [], "topic_terms": [], "allowed_content": [], "prohibited_content": [],
            "asset_sources": [], "posting_rules": [], "account_rules": [],
        },
        "ambiguities": [], "evidence": [{"rule_path": "rules.aspect_ratio", "quote": "9:16"}],
        "confidence": 0.8,
    } for cid in campaign_ids]}


class FakeResponse:
    def __init__(self, body, status_code=200, ok=True):
        self._body = body
        self.status_code = status_code
        self.ok = ok

    def json(self):
        return self._body


class CampaignAITests(unittest.TestCase):
    def test_openrouter_is_hard_locked_to_free_router(self):
        self.assertEqual(campaign_ai.OPENROUTER_MODEL, "openrouter/free")
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "a-paid-model"}, clear=False):
            self.assertEqual(campaign_ai.OPENROUTER_MODEL, "openrouter/free")

    def test_openrouter_request_uses_free_router_even_if_env_requests_paid_model(self):
        campaign = {"id": "c-free-lock", "title": "Free lock test"}
        openrouter_body = {
            "choices": [{"message": {"content": json.dumps(valid_payload(("c-free-lock",)))}}]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-secret",
                "OPENROUTER_API_KEY": "openrouter-secret",
                "OPENROUTER_MODEL": "a-paid-model",
            },
            clear=False,
        ), patch(
            "core.campaign_ai._gemini_generate",
            side_effect=campaign_ai.GeminiApiError("HTTP 429: quota"),
        ), patch(
            "core.campaign_ai.requests.post",
            return_value=FakeResponse(openrouter_body),
        ) as post:
            result = campaign_ai.analyze_campaigns([campaign], batch_size=1)

        self.assertEqual(result["c-free-lock"]["confidence"], 0.8)
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["model"], "openrouter/free")
        self.assertEqual(request_payload["response_format"]["type"], "json_schema")
        self.assertTrue(request_payload["response_format"]["json_schema"]["strict"])
        self.assertEqual(
            request_payload["response_format"]["json_schema"]["schema"],
            campaign_ai.GEMINI_RESPONSE_SCHEMA,
        )
        self.assertTrue(request_payload["provider"]["require_parameters"])

    def test_ai_router_falls_back_to_openrouter_when_gemini_fails(self):
        campaign = {"id": "c-router", "title": "Router test"}
        openrouter_body = {
            "choices": [{"message": {"content": json.dumps(valid_payload(("c-router",)))}}]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-secret",
                "OPENROUTER_API_KEY": "openrouter-secret",
                "OPENROUTER_MODEL": "openrouter/free",
            },
            clear=False,
        ), patch(
            "core.campaign_ai._gemini_generate",
            side_effect=campaign_ai.GeminiApiError("HTTP 429: quota"),
        ), patch(
            "core.campaign_ai.requests.post",
            return_value=FakeResponse(openrouter_body),
        ) as post:
            result = campaign_ai.analyze_campaigns([campaign], batch_size=1)

        self.assertEqual(result["c-router"]["confidence"], 0.8)
        self.assertEqual(post.call_args.args[0], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer openrouter-secret")

    def test_ai_router_falls_back_when_primary_returns_invalid_json(self):
        campaign = {"id": "c-router-json", "title": "Router JSON test"}
        openrouter_body = {
            "choices": [{"message": {"content": json.dumps(valid_payload(("c-router-json",)))}}]
        }
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-secret", "OPENROUTER_API_KEY": "openrouter-secret"},
            clear=False,
        ), patch(
            "core.campaign_ai._gemini_generate",
            return_value="not valid json",
        ), patch(
            "core.campaign_ai.requests.post",
            return_value=FakeResponse(openrouter_body),
        ):
            result = campaign_ai.analyze_campaigns([campaign], batch_size=1)

        self.assertEqual(result["c-router-json"]["confidence"], 0.8)

    def test_gemini_reads_key_uses_schema_and_normalizes_response(self):
        campaign = {"id": "c-1", "title": "Demo", "platforms": ["tiktok"]}
        body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(valid_payload())}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), patch(
            "core.campaign_ai.requests.post", return_value=FakeResponse(body)
        ) as post:
            result = campaign_ai.analyze_campaigns([campaign], batch_size=1)

        self.assertEqual(result["c-1"]["rules"]["min_duration_seconds"], 15)
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["x-goog-api-key"], "test-secret")
        self.assertNotIn("test-secret", post.call_args.args[0])
        generation = post.call_args.kwargs["json"]["generationConfig"]
        self.assertEqual(generation["responseMimeType"], "application/json")
        self.assertEqual(generation["responseSchema"], campaign_ai.GEMINI_RESPONSE_SCHEMA)

    def test_live_analyze_binds_campaign_source_for_evidence_contract(self):
        campaign = {"id": "c-evidence", "title": "Demo", "description": "Use aspect ratio 9:16", "platforms": ["tiktok"]}
        body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(valid_payload(("c-evidence",)))}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), patch(
            "core.campaign_ai.requests.post", return_value=FakeResponse(body)
        ):
            result = campaign_ai.analyze_campaigns([campaign], batch_size=1)
        self.assertEqual(result["c-evidence"]["source_hash"], source_fingerprint(campaign))
        self.assertEqual(result["c-evidence"]["evidence_contract"]["coverage"], 1.0)
        self.assertEqual(len(result["c-evidence"]["evidence_contract"]["verified"]), 1)

    def test_campaign_sync_uses_api_bearer_and_github_auth_headers(self):
        headers = _headers("worker-secret", "github-ephemeral")
        self.assertEqual(headers["authorization"], "Bearer worker-secret")
        self.assertEqual(headers["x-worker-token"], "worker-secret")
        self.assertEqual(headers["x-github-token"], "github-ephemeral")

    def test_legacy_campaign_ai_cache_is_stale_without_evidence_contract(self):
        campaign_hash = "same-rules-hash"
        legacy = {
            "rules_hash": campaign_hash,
            "ai_rules_json": json.dumps({
                "schema_version": 1,
                "rules": {"material_policy": {"schema_version": 1}},
            }),
        }
        self.assertFalse(_cache_is_current(legacy, campaign_hash))

    def test_current_campaign_ai_cache_requires_evidence_contract(self):
        campaign_hash = "same-rules-hash"
        current = {
            "rules_hash": campaign_hash,
            "ai_rules_json": json.dumps({
                "schema_version": 2,
                "source_hash": "source-hash",
                "source_ledger": {"schema_version": 1},
                "evidence_contract": {"schema_version": 1, "verified": [], "unverified": []},
                "rules": {"material_policy": {}},
            }),
        }
        self.assertTrue(_cache_is_current(current, campaign_hash))

    def test_json_fence_is_accepted(self):
        text = "```json\n" + json.dumps(valid_payload()) + "\n```"
        self.assertEqual(campaign_ai._json_from_text(text)["campaigns"][0]["campaign_id"], "c-1")

    def test_invalid_and_truncated_json_are_rejected(self):
        with self.assertRaises(campaign_ai.GeminiJsonError):
            campaign_ai._json_from_text("not json")
        with self.assertRaisesRegex(campaign_ai.GeminiJsonError, "truncated"):
            campaign_ai._json_from_text('{"campaigns": [')

    def test_no_candidate_and_non_stop_finish_reason_are_classified(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), patch(
            "core.campaign_ai.requests.post", return_value=FakeResponse({"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})
        ):
            with self.assertRaises(campaign_ai.GeminiSafetyError):
                campaign_ai._gemini_generate("safe test")

        body = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), patch(
            "core.campaign_ai.requests.post", return_value=FakeResponse(body)
        ):
            with self.assertRaisesRegex(campaign_ai.GeminiJsonError, "truncated"):
                campaign_ai._gemini_generate("safe test")

    def test_http_errors_and_missing_key_do_not_expose_secret(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), patch(
            "core.campaign_ai.requests.post", return_value=FakeResponse({}, status_code=429, ok=False)
        ):
            with self.assertRaisesRegex(campaign_ai.GeminiApiError, "HTTP 429") as ctx:
                campaign_ai._gemini_generate("safe test")
        self.assertNotIn("test-secret", str(ctx.exception))

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError):
                campaign_ai.analyze_campaigns([{"id": "c-1", "title": "Demo"}])

    def test_diagnostics_are_bounded_and_do_not_include_prompt_or_key(self):
        body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(valid_payload())}]}}]}
        output = io.StringIO()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), patch(
            "core.campaign_ai.requests.post", return_value=FakeResponse(body)
        ), redirect_stdout(output):
            campaign_ai._gemini_generate("private campaign prompt")
        diagnostic = output.getvalue()
        self.assertIn("candidate_count=1", diagnostic)
        self.assertIn("finish_reason=STOP", diagnostic)
        self.assertNotIn("private campaign prompt", diagnostic)
        self.assertNotIn("test-secret", diagnostic)


    def test_transient_503_retries_then_succeeds(self):
        campaign = {"id": "c-1", "title": "Demo"}
        body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(valid_payload())}]}}]}
        responses = [
            FakeResponse({"error": {"message": "temporarily overloaded"}}, status_code=503, ok=False),
            FakeResponse(body),
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret", "GEMINI_MAX_RETRIES": "2", "GEMINI_RETRY_BASE_SECONDS": "0.1"}, clear=False), patch(
            "core.campaign_ai.requests.post", side_effect=responses
        ) as post, patch("core.campaign_ai.time.sleep") as sleep:
            result = campaign_ai.analyze_campaigns([campaign], batch_size=1)
        self.assertEqual(result["c-1"]["confidence"], 0.8)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()

    def test_non_transient_400_does_not_retry(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret", "GEMINI_MAX_RETRIES": "2"}, clear=False), patch(
            "core.campaign_ai.requests.post",
            return_value=FakeResponse({"error": {"message": "bad request"}}, status_code=400, ok=False),
        ) as post, patch("core.campaign_ai.time.sleep") as sleep:
            with self.assertRaisesRegex(campaign_ai.GeminiApiError, "HTTP 400"):
                campaign_ai._gemini_generate("safe test")
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_failed_batch_isolated_and_following_batch_survives(self):
        campaigns = [{"id": "c-1", "title": "One"}, {"id": "c-2", "title": "Two"}]
        with patch(
            "core.campaign_ai._gemini_generate",
            side_effect=[campaign_ai.GeminiApiError("HTTP 503"), json.dumps(valid_payload(("c-2",)))],
        ):
            result = campaign_ai.analyze_campaigns(campaigns, batch_size=1)
        self.assertEqual(result["c-1"]["confidence"], 0.0)
        self.assertIn("CRITICAL:", result["c-1"]["ambiguities"][0])
        self.assertEqual(result["c-2"]["confidence"], 0.8)

    def test_batch_size_one_and_two_call_each_batch(self):
        campaigns = [{"id": "c-1", "title": "One"}, {"id": "c-2", "title": "Two"}]
        with patch("core.campaign_ai._gemini_generate", side_effect=[json.dumps(valid_payload(("c-1",))), json.dumps(valid_payload(("c-2",)))]) as generate:
            result = campaign_ai.analyze_campaigns(campaigns, batch_size=1)
        self.assertEqual(len(result), 2)
        self.assertEqual(generate.call_count, 2)

        with patch("core.campaign_ai._gemini_generate", return_value=json.dumps(valid_payload(("c-1", "c-2")))) as generate:
            result = campaign_ai.analyze_campaigns(campaigns, batch_size=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(generate.call_count, 1)

    def test_normalize_ai_result(self):
        result = normalize_ai_result(
            {
                "campaign_fit": {"score": 0.82, "label": "high", "reason": "good fit"},
                "rules": {"aspect_ratio": "9:16", "min_duration_seconds": "8", "max_duration_seconds": 45, "topic_terms": ["AI", "developer"], "hashtags": ["#shorts"], "audience_tiers": {"tier_1": {"terms": ["founders"]}, "tier_2": {"terms": ["students"]}}},
                "ambiguities": [], "confidence": 0.91,
            },
            "abc",
        )
        self.assertEqual(result["campaign_id"], "abc")
        self.assertEqual(result["rules"]["aspect_ratio"], "9:16")
        self.assertEqual(result["rules"]["min_duration_seconds"], 8)
        self.assertEqual(result["rules"]["max_duration_seconds"], 45)
        self.assertEqual(result["rules"]["audience_tiers"]["tier_1"]["terms"], ["founders"])
        self.assertAlmostEqual(result["campaign_fit"]["score"], 0.82)
        self.assertAlmostEqual(result["confidence"], 0.91)

    def test_evidence_ledger_has_stable_source_identity(self):
        campaign = {
            "id": "ryan-regression",
            "description": "Follow and meet Ryan for more @.....",
            "requirements": [{"text": "Clip Length: 15-60 seconds"}],
            "docs_text": "Instagram: @ryan.zofay @thezofayexperiencepodcast\\nTikTok: @ryanzofay\\n#RyanZofay #ryanzofayexperiencepodcast",
        }
        first = build_evidence_ledger(campaign)
        second = build_evidence_ledger(campaign)
        self.assertEqual(first["source_hash"], second["source_hash"])
        self.assertEqual(first["source_hash"], source_fingerprint(campaign))
        self.assertEqual(len(first["documents"]), 3)

    def test_ai_evidence_verification_rejects_quote_not_in_source(self):
        campaign = {"id": "ryan-regression", "description": "Follow and meet Ryan for more @....."}
        evidence = [
            {"rule_path": "posting.cta", "quote": "Follow and meet Ryan for more @....."},
            {"rule_path": "posting.hashtag", "quote": "#invented-tag"},
        ]
        result = verify_ai_evidence(campaign, evidence)
        self.assertEqual(result["coverage"], 0.5)
        self.assertEqual(len(result["verified"]), 1)
        self.assertEqual(result["verified"][0]["status"], "verified")
        self.assertEqual(result["unverified"][0]["reason"], "quote_not_found_in_current_sources")
        self.assertTrue(result["verified"][0]["evidence_id"].startswith("evidence-v1:"))

    def test_normalize_ai_result_attaches_verified_evidence_and_source_hash(self):
        campaign = {
            "id": "ryan-regression",
            "description": "Follow and meet Ryan for more @.....",
            "docs_text": "#RyanZofay",
        }
        item = valid_payload(("ryan-regression",))["campaigns"][0]
        item["evidence"] = [
            {"rule_path": "posting.cta", "quote": "Follow and meet Ryan for more @....."},
            {"rule_path": "posting.hashtag", "quote": "#RyanZofay"},
        ]
        result = normalize_ai_result(item, "ryan-regression", campaign)
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["source_hash"], source_fingerprint(campaign))
        self.assertEqual(result["evidence_contract"]["coverage"], 1.0)
        self.assertEqual(len(result["evidence_contract"]["verified"]), 2)
        self.assertFalse(result["evidence_contract"]["unverified"])
        self.assertEqual(result["source_ledger"]["campaign_id"], "ryan-regression")

    def test_rules_fingerprint_changes_when_rules_change(self):
        base = {"id": "abc", "title": "Example", "brand": "Brand", "description": "Use official clips", "platforms": ["tiktok"], "type": "clipping", "requirements": [{"text": "9:16"}], "resources": [], "payouts": []}
        changed = dict(base)
        changed["requirements"] = [{"text": "16:9"}]
        self.assertNotEqual(rules_fingerprint(base), rules_fingerprint(changed))

    def test_document_only_rule_changes_fingerprint_and_prompt_payload(self):
        base = {"id": "abc", "title": "Example", "description": "Use official clips", "docs_text": "Clip Length: 15-30 seconds", "requirements": []}
        changed = dict(base, docs_text="Clip Length: 30-60 seconds")
        self.assertNotEqual(rules_fingerprint(base), rules_fingerprint(changed))
        prompt = campaign_ai._prompt([changed])
        self.assertIn("Clip Length: 30-60 seconds", prompt)


if __name__ == "__main__":
    unittest.main()
