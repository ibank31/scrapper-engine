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
    def test_examples_are_not_promoted_to_source_assets(self):
        text = "TikTok examples: https://www.tiktok.com/@creator/video/123"
        extracted = extract_document_references(text)
        self.assertEqual(extracted["urls"][0]["role"], "REFERENCE_ONLY")

    def test_direct_media_url_is_primary_source(self):
        self.assertEqual(
            classify_url("https://cdn.example.test/source.mp4", "Footage: https://cdn.example.test/source.mp4"),
            "PRIMARY_SOURCE",
        )

    def test_youtube_source_candidate_is_not_reference_only_without_context(self):
        self.assertEqual(
            classify_url(
                "https://www.youtube.com/watch?v=abc",
                "Music video: https://www.youtube.com/watch?v=abc",
            ),
            "PRIMARY_SOURCE_CANDIDATE",
        )

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

    def test_explicit_source_context_is_primary(self):
        self.assertEqual(
            classify_context("Source video: https://www.youtube.com/watch?v=abc", explicit_source=True),
            "PRIMARY_SOURCE",
        )

    def test_named_youtube_reference_requires_title_and_creator_verification(self):
        payload = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Dardan - Erinnerung (Official Video)",
                    "channel": "Dardan",
                }
            ]
        }

        calls = []

        def fake_runner(args, **kwargs):
            calls.append(args[-1])
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            campaign_title="Dardan Music Clipping",
            brand="Clipping Outlaws",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "verified_candidate")
        self.assertEqual(result["candidate"]["url"], "https://www.youtube.com/watch?v=abc123")
        self.assertGreaterEqual(result["candidate"]["channel_similarity"], 0.70)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("ytsearch"))

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

        def fake_runner(args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            campaign_title="Dardan Music Clipping",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "unresolved")

    def test_named_official_reference_accepts_exact_title_from_verified_publisher(self):
        payload = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Dardan - Erinnerung (Official Video)",
                    "channel": "Hypnotize Entertainment",
                    "channel_is_verified": True,
                }
            ]
        }

        def fake_runner(args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            campaign_title="Dardan Music Clipping",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "verified_candidate")
        self.assertTrue(result["candidate"]["channel_verified"])

    def test_named_youtube_reference_falls_back_to_campaign_context_after_weak_exact_search(self):
        calls = []

        payloads = [
            {"entries": [{"id": "weak", "title": "Unrelated upload", "channel": "Random"}]},
            {"entries": [{"id": "good", "title": "Dardan - Erinnerung (Official Video)", "channel": "Dardan"}]},
        ]

        def fake_runner(args, **kwargs):
            calls.append(args[-1])
            payload = payloads[len(calls) - 1]
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            campaign_title="Dardan Music Clipping",
            brand="Clipping Outlaws",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "verified_candidate")
        self.assertEqual(result["candidate"]["url"], "https://www.youtube.com/watch?v=good")
        self.assertEqual(len(calls), 2)

    def test_named_youtube_reference_rejects_weak_match(self):
        payload = {"entries": [{"id": "x", "title": "Unrelated video"}]}

        def fake_runner(args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=json.dumps(payload), stderr=""
            )

        result = resolve_named_youtube_reference(
            "Dardan - Erinnerung (Official Video)",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "unresolved")

    def test_named_youtube_reference_reports_malformed_metadata(self):
        def fake_runner(args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="not-json", stderr="")

        result = resolve_named_youtube_reference("A named video", runner=fake_runner)
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["reason"], "youtube_search_malformed_json")


if __name__ == "__main__":
    unittest.main()
