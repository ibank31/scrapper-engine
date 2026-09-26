import json
import unittest
from pathlib import Path

from core.campaign_evidence import build_evidence_ledger, source_fingerprint, verify_ai_evidence
from worker.sync_campaigns import _apply_ai, _cache_is_current, _campaigns_needing_ai


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "campaigns"


def load_fixtures():
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            yield path.name, json.load(fh)


def current_cache(campaign_id="cached"):
    return {
        "rules_hash": source_fingerprint({"id": campaign_id, "description": "cached"}),
        "ai_rules_json": json.dumps({
            "schema_version": 2,
            "source_hash": "source-hash",
            "source_ledger": {"schema_version": 1},
            "evidence_contract": {
                "schema_version": 1,
                "verified": [],
                "unverified": [],
            },
            "rules": {"material_policy": {}},
            "campaign_fit": {"score": 0.9},
        }),
        "ai_rules_status": "pass",
        "ai_analyzed_at": "2026-09-26T00:00:00Z",
    }


class CampaignEvidenceAcceptanceTests(unittest.TestCase):
    def test_generic_fixtures_preserve_all_mandatory_evidence(self):
        for name, campaign in load_fixtures():
            with self.subTest(fixture=name):
                first = build_evidence_ledger(campaign)
                second = build_evidence_ledger(campaign)

                self.assertEqual(first["source_hash"], second["source_hash"])
                self.assertEqual(first["source_hash"], source_fingerprint(campaign))
                self.assertTrue(first["documents"])

                result = verify_ai_evidence(campaign, campaign["expected_evidence"])
                mandatory = [item for item in campaign["expected_evidence"] if item.get("mandatory")]
                self.assertEqual(len(result["unverified"]), 0)
                self.assertEqual(result["coverage"], 1.0)
                self.assertEqual(len(result["verified"]), len(campaign["expected_evidence"]))
                mandatory_quotes = {item["quote"] for item in mandatory}
                verified_quotes = {item["quote"] for item in result["verified"]}
                self.assertTrue(mandatory_quotes.issubset(verified_quotes))
                self.assertTrue(all(item["evidence_id"].startswith("evidence-v1:") for item in result["verified"]))

    def test_campaign_corpus_covers_distinct_rule_shapes(self):
        campaigns = {campaign["id"]: campaign for _, campaign in load_fixtures()}
        self.assertGreaterEqual(len(campaigns), 6)
        for fixture_id in (
            "fixture-document-only",
            "fixture-platform-specific",
            "fixture-restrictive-ambiguous",
            "fixture-conflicting-sources",
            "fixture-multilingual",
            "fixture-material-heavy",
        ):
            self.assertIn(fixture_id, campaigns)

        self.assertTrue(any(item["rule_path"].startswith("posting.") for item in campaigns["fixture-platform-specific"]["expected_evidence"]))
        self.assertTrue(any("ambiguity" in item["rule_path"] for item in campaigns["fixture-restrictive-ambiguous"]["expected_evidence"]))
        self.assertTrue(any("asset" in item["rule_path"] for item in campaigns["fixture-material-heavy"]["expected_evidence"]))
        self.assertTrue(any("duration" in item["rule_path"] for item in campaigns["fixture-conflicting-sources"]["expected_evidence"]))
        self.assertTrue(any("CTA" in item["quote"] for item in campaigns["fixture-multilingual"]["expected_evidence"]))

    def test_ledger_contains_provenance_metadata_and_declared_urls(self):
        campaign = {
            "id": "metadata-fixture",
            "description": "A rule-bearing description.",
            "source_urls": [{"url": "https://example.test/brief", "fetched_at": "2026-09-26T00:00:00Z"}],
            "source_metadata": {
                "": {
                    "source_url": "https://example.test/brief",
                    "source_timestamp": "2026-09-26T00:00:00Z",
                    "extraction_method": "html_text",
                    "source_priority": 95,
                }
            },
        }
        ledger = build_evidence_ledger(campaign)
        document = ledger["documents"][0]
        self.assertEqual(ledger["source_references"][0]["url"], "https://example.test/brief")
        self.assertEqual(document["source_url"], "https://example.test/brief")
        self.assertEqual(document["source_timestamp"], "2026-09-26T00:00:00Z")
        self.assertEqual(document["extraction_method"], "html_text")
        self.assertEqual(document["source_priority"], 95)
        self.assertEqual(document["span"], {"start": 0, "end": len("A rule-bearing description.")})
        evidence = verify_ai_evidence(campaign, [{"rule_path": "rules.example", "quote": "A rule-bearing description."}])
        self.assertEqual(evidence["verified"][0]["span"], {"start": 0, "end": len("A rule-bearing description.")})

    def test_document_only_change_changes_source_fingerprint(self):
        campaign = next(
            campaign for _, campaign in load_fixtures()
            if campaign["id"] == "fixture-document-only"
        )
        changed = dict(campaign, docs_text=campaign["docs_text"].replace("15-30", "30-60"))
        self.assertNotEqual(source_fingerprint(campaign), source_fingerprint(changed))

    def test_unverified_quote_is_explicit_not_silent_loss(self):
        campaign = next(load_fixtures())[1]
        result = verify_ai_evidence(
            campaign,
            campaign["expected_evidence"] + [
                {
                    "rule_path": "rules.cta_text",
                    "quote": "Invented rule that is not in the source.",
                }
            ],
        )
        expected_count = len(campaign["expected_evidence"])
        self.assertEqual(result["coverage"], expected_count / (expected_count + 1))
        self.assertEqual(len(result["unverified"]), 1)
        self.assertEqual(result["unverified"][0]["reason"], "quote_not_found_in_current_sources")

    def test_valid_cache_is_reused_and_legacy_cache_is_not(self):
        campaign = {"id": "cached", "description": "cached"}
        rh = source_fingerprint(campaign)
        valid = current_cache("cached")
        valid["rules_hash"] = rh

        self.assertTrue(_cache_is_current(valid, rh))
        target = {}
        _apply_ai(target, None, valid, rh)
        self.assertEqual(target["ai_rules"]["schema_version"], 2)

        legacy = {
            "rules_hash": rh,
            "ai_rules_json": json.dumps({"schema_version": 1, "rules": {"material_policy": {}}}),
        }
        self.assertFalse(_cache_is_current(legacy, rh))
        blocked = {}
        _apply_ai(blocked, None, legacy, rh)
        self.assertEqual(blocked["ai_rules"], {})
        self.assertEqual(blocked["ai_rules_status"], "needs_review")

    def test_targeted_migration_only_sends_requested_campaign_to_ai(self):
        campaigns = [
            {"id": "target", "description": "target"},
            {"id": "other", "description": "other"},
        ]
        existing = {}
        candidates = _campaigns_needing_ai(
            campaigns,
            existing,
            force_ai=False,
            target_ids={"target"},
        )
        self.assertEqual([item["id"] for item in candidates], ["target"])

    def test_targeted_migration_reuses_valid_non_target_cache_without_ai(self):
        campaigns = [
            {"id": "target", "description": "target"},
            {"id": "other", "description": "other"},
        ]
        target_hash = source_fingerprint(campaigns[0])
        other_hash = source_fingerprint(campaigns[1])
        other_cache = current_cache("other")
        other_cache["rules_hash"] = other_hash
        candidates = _campaigns_needing_ai(
            campaigns,
            {"other": other_cache},
            force_ai=False,
            target_ids={"target"},
        )
        self.assertEqual([item["id"] for item in candidates], ["target"])
        self.assertNotEqual(target_hash, other_hash)


if __name__ == "__main__":
    unittest.main()
