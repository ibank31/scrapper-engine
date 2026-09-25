import tempfile
import unittest
from pathlib import Path

from core.media_validation import validate_video_file


class MediaValidationTests(unittest.TestCase):
    def test_missing_file_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_video_file(Path(tmp) / "missing.mp4")
        self.assertEqual(result["status"], "fail")
        self.assertIn("file_missing", result["issues"])

    def test_empty_file_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.mp4"
            path.write_bytes(b"")
            result = validate_video_file(path)
        self.assertEqual(result["status"], "fail")
        self.assertIn("empty_file", result["issues"])


if __name__ == "__main__":
    unittest.main()
