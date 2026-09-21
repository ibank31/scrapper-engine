import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from core import campaign_ai
from core.campaign_ai import normalize_ai_result, rules_fingerprint


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
                "rules": {"aspect_ratio": "9:16", "min_duration_seconds": "8", "max_duration_seconds": 45, "topic_terms": ["AI", "developer"], "hashtags": ["#shorts"]},
                "ambiguities": [], "confidence": 0.91,
            },
            "abc",
        )
        self.assertEqual(result["campaign_id"], "abc")
        self.assertEqual(result["rules"]["aspect_ratio"], "9:16")
        self.assertEqual(result["rules"]["min_duration_seconds"], 8)
        self.assertEqual(result["rules"]["max_duration_seconds"], 45)
        self.assertAlmostEqual(result["campaign_fit"]["score"], 0.82)
        self.assertAlmostEqual(result["confidence"], 0.91)

    def test_rules_fingerprint_changes_when_rules_change(self):
        base = {"id": "abc", "title": "Example", "brand": "Brand", "description": "Use official clips", "platforms": ["tiktok"], "type": "clipping", "requirements": [{"text": "9:16"}], "resources": [], "payouts": []}
        changed = dict(base)
        changed["requirements"] = [{"text": "16:9"}]
        self.assertNotEqual(rules_fingerprint(base), rules_fingerprint(changed))


if __name__ == "__main__":
    unittest.main()
