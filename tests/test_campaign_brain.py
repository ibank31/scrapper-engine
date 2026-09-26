import json
import unittest
from pathlib import Path

from core.campaign_ai import normalize_ai_result
from core.campaign_brain import evaluate_rule_preservation
from core.campaign_evidence import source_fingerprint

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "campaigns"


def load_fixtures():
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        yield json.loads(path.read_text(encoding="utf-8"))


def fixture_ai_item(campaign):
    annotations = []
    for expected in campaign.get("expected_evidence") or []:
        path = str(expected["rule_path"])
        quote = str(expected["quote"])
        low = quote.lower()
        languages = []
        if "english" in low:
            languages.append("en")
        elif any(token in low for token in ("gunak", "durasi", "detik", "wajib")):
            languages.append("id")
        platforms = [
            platform
            for platform in (
                "instagram", "tiktok", "youtube", "facebook",
                "x", "twitter", "linkedin", "threads"
            )
            if platform in path.lower()
        ]
        annotations.append({
            "rule_path": path,
            "value": quote,
            "requirement_level": "mandatory" if expected.get("mandatory") else "optional",
            "interpretation_type": "ambiguous" if "ambiguity" in path.lower() else "explicit",
            "scope": {
                "platforms": platforms,
                "languages": languages,
                "audiences": [],
            },
        })
    return {
        "campaign_fit": {"score": 0.9, "label": "high", "reason": "fixture"},
        "rules": {},
        "rule_annotations": annotations,
        "ambiguities": [],
        "evidence": list(campaign.get("expected_evidence") or []),
        "confidence": 0.95,
    }


class CampaignBrainTests(unittest.TestCase):
    def test_existing_six_shape_corpus_preserves_declared_rules(self):
        for campaign in load_fixtures():
            with self.subTest(fixture=campaign["id"]):
                item = fixture_ai_item(campaign)
                first = normalize_ai_result(item, campaign["id"], campaign)
                second = normalize_ai_result(item, campaign["id"], campaign)
                brain = first["campaign_brain"]
                evaluation = evaluate_rule_preservation(campaign, brain)

                self.assertEqual(evaluation["status"], "pass", evaluation)
                self.assertEqual(evaluation["critical_rule_preservation"], 1.0)
                self.assertEqual(evaluation["mandatory_rule_preservation"], 1.0)
                self.assertEqual(evaluation["silent_rule_loss"], 0)
                self.assertEqual(evaluation["false_mandatory"], [])
                self.assertTrue(all(rule.get("evidence_ids") for rule in brain["rules"]))
                self.assertTrue(brain["brain_id"].startswith("brain-v1:"))
                self.assertEqual(brain["source_hash"], source_fingerprint(campaign))
                self.assertEqual(brain["brain_id"], second["campaign_brain"]["brain_id"])

    def test_platform_scope_is_preserved_per_rule(self):
        campaign = {"id": "scope", "platforms": ["instagram", "tiktok"]}
        item = {
            "campaign_fit": {"score": 0.9, "label": "high", "reason": "fixture"},
            "rules": {},
            "rule_annotations": [
                {
                    "rule_path": "posting.instagram.hashtags",
                    "value": "#One",
                    "requirement_level": "mandatory",
                    "interpretation_type": "explicit",
                    "scope": {"platforms": [], "languages": [], "audiences": []},
                },
                {
                    "rule_path": "posting.tiktok.hashtags",
                    "value": "#Two",
                    "requirement_level": "mandatory",
                    "interpretation_type": "explicit",
                    "scope": {"platforms": [], "languages": [], "audiences": []},
                },
            ],
            "ambiguities": [],
            "evidence": [
                {"rule_path": "posting.instagram.hashtags", "quote": "#One"},
                {"rule_path": "posting.tiktok.hashtags", "quote": "#Two"},
            ],
            "confidence": 0.9,
        }
        brain = normalize_ai_result(item, campaign["id"], campaign)["campaign_brain"]
        rules = {rule["source_rule_path"]: rule for rule in brain["rules"]}
        self.assertEqual(rules["posting.instagram.hashtags"]["scope"]["platforms"], ["instagram"])
        self.assertEqual(rules["posting.tiktok.hashtags"]["scope"]["platforms"], ["tiktok"])

    def test_conflicting_sources_are_preserved_not_resolved(self):
        campaign = next(
            campaign for campaign in load_fixtures()
            if campaign["id"] == "fixture-conflicting-sources"
        )
        brain = normalize_ai_result(
            fixture_ai_item(campaign), campaign["id"], campaign
        )["campaign_brain"]
        conflict = next(
            item for item in brain["conflicts"] if item["rule_path"] == "rules.duration"
        )
        self.assertEqual(conflict["status"], "unresolved")
        self.assertEqual(len(conflict["evidence_ids"]), 2)

    def test_multilingual_variants_are_distinct(self):
        campaign = next(
            campaign for campaign in load_fixtures()
            if campaign["id"] == "fixture-multilingual"
        )
        brain = normalize_ai_result(
            fixture_ai_item(campaign), campaign["id"], campaign
        )["campaign_brain"]
        cta_rules = [
            rule for rule in brain["rules"]
            if rule["source_rule_path"] == "rules.cta_text"
        ]
        self.assertEqual(len(cta_rules), 2)
        self.assertEqual(
            {tuple(rule["scope"]["languages"]) for rule in cta_rules},
            {("en",), ("id",)},
        )
        self.assertTrue(
            any(item["rule_path"] == "rules.cta_text" for item in brain["variants"])
        )

    def test_unavailable_ai_does_not_create_false_boolean_rules(self):
        campaign = {"id": "unknown", "description": "No subtitle rule here."}
        item = {
            "campaign_fit": {
                "score": None,
                "label": "unknown",
                "reason": "AI analysis unavailable",
            },
            "rules": {
                "subtitle_required": False,
                "watermark_required": False,
                "official_audio_required": False,
                "cta_required": False,
            },
            "ambiguities": ["CRITICAL: unavailable"],
            "evidence": [],
            "confidence": 0.0,
        }
        brain = normalize_ai_result(item, campaign["id"], campaign)["campaign_brain"]
        self.assertEqual(brain["rules"], [])

    def test_cta_text_can_bind_to_cta_requirement_evidence(self):
        campaign = {
            "id": "cta-alias",
            "description": 'All pieces of content should have "Follow and meet Ryan for more @....."',
        }
        item = {
            "campaign_fit": {"score": 0.9, "label": "high", "reason": "fixture"},
            "rules": {
                "cta_required": True,
                "cta_text": "Follow and meet Ryan for more @.....",
            },
            "rule_annotations": [],
            "ambiguities": [],
            "evidence": [{
                "rule_path": "rules.cta_required",
                "quote": 'All pieces of content should have "Follow and meet Ryan for more @....."',
            }],
            "confidence": 0.9,
        }
        brain = normalize_ai_result(item, campaign["id"], campaign)["campaign_brain"]
        cta = next(
            rule for rule in brain["rules"]
            if rule["source_rule_path"] == "rules.cta_text"
        )
        self.assertEqual(cta["status"], "supported")
        self.assertTrue(cta["evidence_ids"])

    def test_unverified_rule_is_not_supported(self):
        campaign = {"id": "unsupported", "description": "Approved clips only."}
        item = {
            "campaign_fit": {"score": 0.9, "label": "high", "reason": "fixture"},
            "rules": {"source_policy": "approved clips only"},
            "rule_annotations": [],
            "ambiguities": [],
            "evidence": [],
            "confidence": 0.9,
        }
        rules = normalize_ai_result(
            item, campaign["id"], campaign
        )["campaign_brain"]["rules"]
        self.assertEqual(rules[0]["status"], "unsupported")
        self.assertEqual(rules[0]["evidence_ids"], [])


if __name__ == "__main__":
    unittest.main()
