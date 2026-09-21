import json
import os
import unittest
from unittest.mock import patch

from core.campaign_ai import normalize_ai_result, rules_fingerprint
from core import campaign_ai


class FakeGeminiResponse:
    ok = True
    status_code = 200

    def json(self):
        return {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps({"campaigns": [{
                    "campaign_id": "c-1",
                    "campaign_fit": {"score": 0.9, "label": "high", "reason": "matches"},
                    "rules": {"platforms": ["tiktok"], "min_duration_seconds": "15"},
                    "confidence": 0.8,
                }]})}]}
            }]
        }


class CampaignAITests(unittest.TestCase):
    def test_gemini_reads_required_environment_key_and_normalizes_response(self):
        campaign = {"id": "c-1", "title": "Demo", "platforms": ["tiktok"]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}, clear=False), patch(
            "core.campaign_ai.requests.post", return_value=FakeGeminiResponse()
        ) as post:
            result = campaign_ai.analyze_campaigns([campaign], batch_size=1)

        self.assertEqual(result["c-1"]["rules"]["min_duration_seconds"], 15)
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["x-goog-api-key"], "test-secret")
        self.assertNotIn("test-secret", post.call_args.args[0])

    def test_missing_gemini_key_fails_without_local_model_fallback(self):
        campaign = {"id": "c-1", "title": "Demo"}
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError):
                campaign_ai.analyze_campaigns([campaign])

    def test_normalize_ai_result(self):
        result = normalize_ai_result(
            {
                "campaign_fit": {"score": 0.82, "label": "high", "reason": "good fit"},
                "rules": {
                    "aspect_ratio": "9:16",
                    "min_duration_seconds": "8",
                    "max_duration_seconds": 45,
                    "topic_terms": ["AI", "developer"],
                    "hashtags": ["#shorts"],
                },
                "ambiguities": [],
                "confidence": 0.91,
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
        base = {
            "id": "abc",
            "title": "Example",
            "brand": "Brand",
            "description": "Use official clips",
            "platforms": ["tiktok"],
            "type": "clipping",
            "requirements": [{"text": "9:16"}],
            "resources": [],
            "payouts": [],
        }
        changed = dict(base)
        changed["requirements"] = [{"text": "16:9"}]
        self.assertNotEqual(rules_fingerprint(base), rules_fingerprint(changed))


if __name__ == "__main__":
    unittest.main()
