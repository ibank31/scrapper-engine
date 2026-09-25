import tempfile
import unittest
from pathlib import Path

from core.campaign_rules import compile_plan
from modules.reward_campaign.intake import _record, _reference_urls, _source_type


class CampaignIntakeTest(unittest.TestCase):
    def test_normalizes_string_and_object_requirements(self):
        plan = compile_plan({
            "campaign": {"title": "Demo", "description": "Use provided raw assets."},
            "staticDetails": {"requirements": ["Include demographic information", {"text": "Use official audio", "isMandatory": True}]},
        })
        normalized = plan["source_of_truth"]["normalized_requirements"]
        self.assertEqual(normalized[0]["id"], "demographic_information")
        self.assertEqual(normalized[1]["id"], "official_audio")

    def test_doc_url_parser_is_safe_without_network(self):
        self.assertEqual(_reference_urls("https://example.com/not-a-doc"), [])

    def test_source_type_keeps_drive_folder_distinct(self):
        self.assertEqual(_source_type("https://drive.google.com/drive/folders/folder_ABC"), "google_drive_folder")
        self.assertEqual(_source_type("https://drive.google.com/file/d/file_ABC/view"), "google_drive")
        self.assertEqual(_source_type("https://youtu.be/video_ABC"), "youtube")

    def test_record_contains_traceable_source_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(b"clip")
            record = _record(path, tmp, "https://example.com/clip.mp4", "direct_media")
        self.assertTrue(record["source_id"])
        self.assertEqual(record["source_reference"], record["url"])
        self.assertEqual(record["status"], "downloaded")
        self.assertEqual(record["bytes"], 4)


if __name__ == "__main__":
    unittest.main()
