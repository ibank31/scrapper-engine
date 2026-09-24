import unittest

from core.candidate_identity import (
    annotate_candidate,
    build_candidate_identity,
    classify_candidate_tier,
    deduplicate_source_records,
    normalize_source_asset_id,
)


class CandidateIdentityTests(unittest.TestCase):
    def setUp(self):
        self.transcript = {"segments": [{"start": 0, "end": 4, "text": "A complete moment."}]}
        self.candidate = {"start": 10, "end": 25, "duration": 15, "text": "A budgeting lesson for small business owners.", "reasons": ["complete ending"]}

    def test_identity_is_stable_and_includes_required_evidence(self):
        first = build_candidate_identity(self.candidate, "/tmp/clip.mp4", "source-hash", "transcript-hash", "rules-hash")
        second = build_candidate_identity(dict(self.candidate), "/tmp/clip.mp4", "source-hash", "transcript-hash", "rules-hash")
        self.assertEqual(first, second)
        self.assertTrue(first["candidate_id"].startswith("candidate-v1:"))
        self.assertEqual(first["source_asset_id"], "/tmp/clip.mp4")
        self.assertEqual(first["start"], 10.0)
        self.assertEqual(first["end"], 25.0)
        self.assertEqual(first["rules_hash"], "rules-hash")

    def test_source_url_normalization_removes_tracking_noise(self):
        self.assertEqual(
            normalize_source_asset_id("HTTPS://Example.com/video.mp4/?utm_source=test&part=1"),
            "https://example.com/video.mp4?part=1",
        )

    def test_explicit_audience_rules_classify_candidate(self):
        plan = {"production": {"audience_tiers": {
            "tier_1": {"terms": ["small business owners"]},
            "tier_2": {"terms": ["college students"]},
        }}}
        result = classify_candidate_tier(self.candidate, plan)
        self.assertEqual(result["tier"], "tier_1")
        self.assertEqual(result["classifier_version"], "audience-v1")
        self.assertEqual(result["reason"], "explicit_audience_terms_matched")

    def test_missing_or_ambiguous_audience_rules_are_unknown(self):
        self.assertEqual(classify_candidate_tier(self.candidate, {})["tier"], "unknown")
        plan = {"production": {"audience_tiers": {
            "tier_1": {"terms": ["business"]},
            "tier_2": {"terms": ["owners"]},
        }}}
        self.assertEqual(classify_candidate_tier(self.candidate, plan)["tier"], "unknown")

    def test_annotation_preserves_candidate_and_adds_tier_evidence(self):
        plan = {"rules_hash": "rules-hash", "production": {"audience_tiers": {
            "tier_1": {"terms": ["small business owners"]},
            "tier_2": {"terms": ["college students"]},
        }}}
        annotated = annotate_candidate(self.candidate, "/tmp/clip.mp4", "source-hash", self.transcript, plan)
        self.assertEqual(annotated["text"], self.candidate["text"])
        self.assertEqual(annotated["tier"], "tier_1")
        self.assertEqual(annotated["rules_hash"], "rules-hash")
        self.assertEqual(annotated["selection_rationale"], ["complete ending"])

    def test_source_deduplication_happens_before_limit_and_retains_evidence(self):
        records = [
            {"source": "/assets/first.mp4", "quality": {"duplicate_hash": "same"}},
            {"source": "/assets/copy.mp4", "quality": {"duplicate_hash": "same"}},
            {"source": "/assets/unique.mp4", "quality": {"duplicate_hash": "unique"}},
        ]
        selected, evidence = deduplicate_source_records(records, max_sources=2)
        self.assertEqual([item["source"] for item in selected], ["/assets/first.mp4", "/assets/unique.mp4"])
        duplicate = next(item for item in evidence if item["source"].endswith("copy.mp4"))
        self.assertEqual(duplicate["duplicate_of"], "/assets/first.mp4")
        self.assertTrue(duplicate["excluded_before_source_limit"])
        self.assertEqual(len(evidence), 3)


if __name__ == "__main__":
    unittest.main()
