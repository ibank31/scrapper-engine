import unittest
from pathlib import Path

from core.recovery_policy import capacity_preflight, classify_provider_error, jittered_delay, retry_decision, stuck_operation_alert
from core.retention_safety import media_reachability_contract, operation_requires_retention, retention_decision

ROOT = Path(__file__).parents[1]
API = (ROOT / "cloudflare" / "api.js").read_text(encoding="utf-8")


class Phase4PureContractTests(unittest.TestCase):
    def test_retention_keeps_active_and_review_dependencies(self):
        self.assertTrue(operation_requires_retention("unknown"))
        self.assertFalse(operation_requires_retention("published"))
        result = retention_decision(preview_status="rejected", object_key="x.mp4", operations=[{"operation_key": "op", "provider_state": "scheduled"}], now_iso="now")
        self.assertTrue(result["retain"])
        self.assertEqual(result["reason"], "active_delivery_dependency")

    def test_reachability_contract_requires_https_video_and_ranges(self):
        self.assertTrue(media_reachability_contract(url="https://example.test/a.mp4", content_type="video/mp4", content_length=10, accepts_ranges=True)["ok"])
        self.assertFalse(media_reachability_contract(url="http://example.test/a.mp4", content_type="text/plain", content_length=0, accepts_ranges=False)["ok"])

    def test_recovery_classification_and_bounded_jitter(self):
        self.assertEqual(classify_provider_error(http_status=429), "throttled")
        self.assertEqual(classify_provider_error(timeout=True), "unknown_outcome")
        self.assertTrue(retry_decision("transient", 1)["retryable"])
        self.assertFalse(retry_decision("transient", 3)["retryable"])
        self.assertEqual(jittered_delay("op", 2), jittered_delay("op", 2))
        self.assertTrue(stuck_operation_alert(provider_state="unknown", updated_age_seconds=901)["alert"])

    def test_capacity_guard_blocks_full_channel_and_budget(self):
        result = capacity_preflight(selected_channels=1, channel_capacity={"c": 10}, channel_usage={"c": 10}, request_count=3000, request_budget=3000, requested_channel_ids=["c"])
        self.assertFalse(result["ok"])
        self.assertEqual({failure["code"] for failure in result["failures"]}, {"scheduled_capacity_exhausted", "request_budget_exhausted"})


class Phase4ApiContractTests(unittest.TestCase):
    def test_cleanup_is_dependency_aware_and_audited(self):
        self.assertIn("retention_events", API)
        self.assertIn("active_delivery_dependency", API)
        self.assertIn("retained_previews", API)
        self.assertIn("deletablePreviews", API)

    def test_media_probe_and_request_budget_exist(self):
        self.assertIn('parts[3] === "media-probe"', API)
        self.assertIn("accept_ranges", API)
        self.assertIn("provider_request_ledger", API)
        self.assertIn("capacity_preflight_failed", API)
        self.assertIn('parts[2] === "alerts"', API)
        self.assertIn("retry_budget_exhausted", API)

    def test_rerender_creates_new_lineage_and_clears_approval(self):
        self.assertIn("parent_preview_id", API)
        self.assertIn("render_revision", API)
        self.assertIn("rerender_requested", API)
        self.assertIn("approval_artifact_hash=NULL", API)
        self.assertIn("stale_generation", API)


if __name__ == "__main__": unittest.main()
