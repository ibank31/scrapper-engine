import tempfile
import unittest
from pathlib import Path

from core.asset_gate import manifest_has_invalid_media, manifest_video_paths


class AssetGateTests(unittest.TestCase):
    def test_new_manifest_never_falls_back_to_invalid_workspace_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            raw = root / "assets" / "raw.mp4"
            raw.write_bytes(b"not-a-real-video")
            manifest = {
                "asset_manifest": [
                    {
                        "asset_kind": "video",
                        "downloaded": True,
                        "local_path": "assets/raw.mp4",
                        "status": "INVALID_MEDIA",
                        "media_validation": {"status": "fail", "issues": ["ffprobe_failed"]},
                    }
                ]
            }
            self.assertEqual(manifest_video_paths(root, manifest, extensions={".mp4"}), [])

    def test_new_manifest_keeps_only_validated_video_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            good = root / "assets" / "good.mp4"
            bad = root / "assets" / "bad.mp4"
            good.write_bytes(b"x")
            bad.write_bytes(b"y")
            manifest = {
                "asset_manifest": [
                    {
                        "asset_kind": "video",
                        "downloaded": True,
                        "local_path": "assets/good.mp4",
                        "status": "READY_FOR_PROCESSING",
                        "media_validation": {"status": "pass"},
                    },
                    {
                        "asset_kind": "video",
                        "downloaded": True,
                        "local_path": "assets/bad.mp4",
                        "status": "INVALID_MEDIA",
                        "media_validation": {"status": "fail"},
                    },
                ]
            }
            self.assertEqual(manifest_video_paths(root, manifest, extensions={".mp4"}), [good])

    def test_invalid_media_state_is_detected_for_worker_gate(self):
        self.assertTrue(
            manifest_has_invalid_media(
                {
                    "asset_manifest": [
                        {"asset_kind": "video", "status": "INVALID_MEDIA"}
                    ]
                }
            )
        )
        self.assertFalse(manifest_has_invalid_media({"asset_manifest": []}))

    def test_legacy_manifest_can_use_defensive_filesystem_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            raw = root / "assets" / "legacy.mp4"
            raw.write_bytes(b"legacy")
            manifest = {"asset_manifest": []}
            self.assertEqual(manifest_video_paths(root, manifest, extensions={".mp4"}), [raw])


if __name__ == "__main__":
    unittest.main()
