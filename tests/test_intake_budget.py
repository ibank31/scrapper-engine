import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.reward_campaign import intake


class IntakeBudgetTests(unittest.TestCase):
    def test_metadata_priority_prefers_high_quality_master(self):
        high = {
            "id": "high",
            "name": "campaign_master_1080p_final.mp4",
            "mimeType": "video/mp4",
            "size": "500000000",
            "videoMediaMetadata": {"width": "1920", "height": "1080", "durationMillis": "90000"},
        }
        low = {
            "id": "low",
            "name": "preview_lowres.mp4",
            "mimeType": "video/mp4",
            "size": "20000000",
            "videoMediaMetadata": {"width": "640", "height": "360", "durationMillis": "5000"},
        }
        self.assertGreater(intake._asset_priority(high), intake._asset_priority(low))

    @patch("modules.reward_campaign.intake.shutil.disk_usage")
    def test_download_guard_defers_when_margin_is_not_available(self, disk_usage):
        disk_usage.return_value = shutil._ntuple_diskusage(20_000_000_000, 19_500_000_000, 500_000_000)
        status, reason = intake._download_guard("/tmp/asset.mp4", required_size=100_000_000, safety_margin=1_000_000_000)
        self.assertEqual((status, reason), ("deferred", "DEFERRED_DISK_BUDGET"))

    def test_youtube_download_is_atomic_and_removes_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = str(Path(tmp) / "asset.mp4")
            def fake_run(command, check, text, timeout):
                output_template = command[command.index("-o") + 1]
                output_path = Path(output_template.replace("%(ext)s", "mp4"))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"complete")
                return None
            with patch("modules.reward_campaign.intake._download_guard", return_value=("ready", None)), patch(
                "modules.reward_campaign.intake.subprocess.run", side_effect=fake_run
            ):
                status, error = intake.download_youtube("https://youtu.be/test", destination)
            self.assertEqual((status, error), ("downloaded", None))
            self.assertEqual(Path(destination).read_bytes(), b"complete")
            self.assertFalse(Path(destination + ".part").exists())
            self.assertFalse(any((Path(tmp) / ".youtube-tmp").rglob("*")))

    def test_youtube_failure_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = str(Path(tmp) / "asset.mp4")
            temp_dir = Path(tmp) / ".youtube-tmp" / "asset"
            temp_dir.mkdir(parents=True, exist_ok=True)
            (temp_dir / "source.part").write_bytes(b"partial")
            with patch("modules.reward_campaign.intake._download_guard", return_value=("ready", None)), patch(
                "modules.reward_campaign.intake.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["yt-dlp"])
            ):
                status, error = intake.download_youtube("https://youtu.be/test", destination)
            self.assertEqual(status, "failed")
            self.assertFalse(Path(destination + ".part").exists())
            self.assertFalse(any((Path(tmp) / ".youtube-tmp").rglob("*")))
            self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
