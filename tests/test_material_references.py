import json
import subprocess
import unittest

from core.material_references import (
    classify_context,
    classify_url,
    extract_document_references,
    is_symbolic_reference,
    resolve_named_youtube_reference,
)


class MaterialReferenceTests(unittest.TestCase):
    def test_direct_media_and_drive_urls_are_primary_sources(self):
        extracted = extract_document_references(
            "Footage: https://cdn.example.test/source.mp4\nDrive: https://drive.google.com/file/d/abc/view"
        )
        self.assertEqual([item["role"] for item in extracted["urls"]], ["PRIMARY_SOURCE", "PRIMARY_SOURCE"])

    def test_youtube_url_without_source_context_is_candidate(self):
        self.assertEqual(
            classify_url("https://www.youtube.com/watch?v=abc", "Video: https://www.youtube.com/watch?v=abc"),
            "PRIMARY_SOURCE_CANDIDATE",
        )

    def test_examples_are_not_promoted_to_source_assets(self):
        text = "TikTok examples: https://www.tiktok.com/@creator/video/123"
        extracted = extract_document_references(text)
        self.assertEqual(extracted["urls"][0]["role"], "REFERENCE_ONLY")

    def test_official_music_video_is_named_source_candidate(self):
        text = "Music video: Dardan - Erinnerung (Official Video)"
        extracted = extract_document_references(text)
        self.assertEqual(len(extracted["named_media"]), 1)
        item = extracted["named_media"][0]
        self.assertEqual(item["role"], "PRIMARY_SOURCE_CANDIDATE")
        self.assertIn("Erinnerung", item["value"])

    def test_symbolic_asset_is_not_silently_accepted(self):
        self.assertTrue(is_symbolic_reference("brandAsset"))
        self.assertFalse(is_symbolic_reference("https://example.com/a.mp4"))
        extracted = extract_document_references("brandAsset")
        self.assertEqual(extracted["symbolic_assets"][0]["reference"], "brandAsset")

    def test_explicit_source_context_is_primary(self):
        self.assertEqual(
            classify_context("Source video: https://www.youtube.com/watch?v=abc", explicit_source=True),
            "PRIMARY_SOURCE",
        )

    def test_named_youtube_reference_requires_verification(self):
        payload = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Dardan - Erinnerung (Official Video)",
                    "channel": "Dardan",
                }
            ]
        }

        def fake_runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            campaign_title="Dardan Music Clipping",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "verified_candidate")
        self.assertEqual(result["candidate"]["url"], "https://www.youtube.com/watch?v=abc123")
        self.assertGreaterEqual(result["candidate"]["channel_similarity"], 0.55)

    def test_named_official_reference_rejects_unrelated_channel(self):
        payload = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Dardan - Erinnerung (Official Video)",
                    "channel": "Random Fan Uploads",
                }
            ]
        }

        def fake_runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            campaign_title="Dardan Music Clipping",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "unresolved")

    def test_named_official_reference_rejects_missing_channel_metadata(self):
        payload = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Dardan - Erinnerung (Official Video)",
                }
            ]
        }

        def fake_runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            campaign_title="Dardan Music Clipping",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "unresolved")

    def test_named_youtube_reference_rejects_weak_match(self):
        payload = {"entries": [{"id": "x", "title": "Unrelated video"}]}

        def fake_runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "unresolved")

    def test_named_youtube_reference_reports_malformed_metadata(self):
        def fake_runner(*args, **kwargs):
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="not-json", stderr="")

        result = resolve_named_youtube_reference("A named video", runner=fake_runner)
        self.assertEqual(result["status"], "unresolved")
        self.assertIn("youtube_search_error", result["reason"])


if __name__ == "__main__":
    unittest.main()
