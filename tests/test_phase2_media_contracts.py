import unittest

from core.sound_tags import merge_provider_evidence, normalize_sound_tags
from core.subtitle_delivery import attach_artifact_hash, resolve_subtitle_profile


class Phase2MediaContractTests(unittest.TestCase):
    def test_subtitle_modes_and_missing_transcript(self):
        burned = resolve_subtitle_profile("burned_in", transcript_available=True, required=True)
        self.assertTrue(burned["compliant"])
        missing = resolve_subtitle_profile("burned_in", transcript_available=False, required=True)
        self.assertFalse(missing["compliant"])
        none = resolve_subtitle_profile("none", transcript_available=False, required=False)
        self.assertTrue(none["compliant"])
        self.assertEqual(attach_artifact_hash(burned, "ass artifact")["artifact_hash"].__len__(), 64)

    def test_verified_cannot_be_created_without_evidence(self):
        item = normalize_sound_tags(platform="tiktok", policy="official", status="verified", track_id="track-1")
        self.assertEqual(item["status"], "manual_required")
        item = merge_provider_evidence(item, {"provider": "native", "track_id": "track-1"}, status="verified")
        self.assertEqual(item["status"], "verified")

    def test_invalid_status_is_manual_required(self):
        item = normalize_sound_tags(platform="instagram", policy="unsupported", status="wat", native_tags=["#ad", "#ad"])
        self.assertEqual(item["status"], "manual_required")
        self.assertEqual(item["native_tags"], ["#ad"])


if __name__ == "__main__":
    unittest.main()
