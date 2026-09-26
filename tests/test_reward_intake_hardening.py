import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from modules.reward_campaign import intake
from modules.reward_campaign.intake import _resolve_symbolic_asset


class RewardIntakeHardeningTests(unittest.TestCase):
    def test_symbolic_asset_resolves_from_explicit_campaign_mapping(self):
        plan = {
            "production": {
                "asset_mappings": {
                    "brandAsset": {"url": "https://cdn.example.test/brand.mp4"}
                }
            }
        }
        url, meta = _resolve_symbolic_asset(plan, "brandAsset")
        self.assertEqual(url, "https://cdn.example.test/brand.mp4")
        self.assertEqual(meta["mapping_source"], "campaign_plan")

    def test_symbolic_asset_resolves_normalized_key(self):
        plan = {
            "production": {
                "asset_mappings": {
                    "brand_asset": "https://cdn.example.test/brand.mp4"
                }
            }
        }
        url, _ = _resolve_symbolic_asset(plan, "brandAsset")
        self.assertEqual(url, "https://cdn.example.test/brand.mp4")

    def test_named_media_reference_enters_production_source_manifest(self):
        plan = {
            "job_id": "integration-test",
            "campaign": {"id": "campaign-1", "title": "Dardan Music Clipping", "brand": "Dardan"},
            "production": {"asset_urls": ["https://docs.google.com/document/d/test-document/edit"]},
            "source_of_truth": {"description": "", "requirements": []},
        }
        fixture_text = "Music video: Dardan - Erinnerung (Official Video)\nGenius lyrics: https://genius.com/example"
        resolved = {
            "status": "verified_candidate",
            "candidate": {
                "url": "https://www.youtube.com/watch?v=verified123",
                "title": "Dardan - Erinnerung (Official Video)",
                "channel": "Dardan",
                "channel_similarity": 1.0,
            },
        }

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(intake, "_reference_text", return_value=(fixture_text, None)), \
             patch.object(intake, "resolve_named_youtube_reference", return_value=resolved), \
             patch.object(intake, "google_drive_configured", return_value=False):
            with patch("sys.argv", ["reward_intake", "plan.json", "--workspace", tmp, "--no-download"]):
                with patch.object(intake, "read_json", return_value=plan):
                    with self.assertRaises(SystemExit) as exit_info:
                        intake.main()
            self.assertEqual(exit_info.exception.code, 0)

            manifests = list(Path(tmp).rglob("assets.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            discovery = manifest["discovery"]
            self.assertEqual(discovery["named_reference_count"], 1)
            self.assertEqual(discovery["discovered_media_sources"], 1)
            self.assertEqual(manifest["reference_manifest"][0]["reference_kind"], "NAMED_MEDIA")
            self.assertEqual(manifest["source_manifest"][0]["source_url"], "https://www.youtube.com/watch?v=verified123")
            self.assertEqual(manifest["asset_manifest"][0]["reference_role"], "PRIMARY_SOURCE_CANDIDATE")
            self.assertEqual(manifest["asset_manifest"][0]["status"], "READY_FOR_DOWNLOAD")

    def test_unknown_symbolic_asset_is_unresolved_without_inventing_url(self):
        url, meta = _resolve_symbolic_asset({"production": {}}, "brandAsset")
        self.assertIsNone(url)
        self.assertEqual(meta["mapping_key"], "brandasset")


if __name__ == "__main__":
    unittest.main()
