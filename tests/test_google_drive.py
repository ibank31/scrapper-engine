import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import google_drive


class FakeResponse:
    def __init__(self, body=None, status_code=200, content=b"", chunks=None):
        self._body = body
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = json.dumps(body or {})
        self.content = content
        self._chunks = chunks or []

    def json(self):
        return self._body

    def iter_content(self, chunk_size=0):
        return iter(self._chunks)


class GoogleDriveTests(unittest.TestCase):
    def test_extracts_file_folder_and_query_ids(self):
        self.assertEqual(google_drive.extract_drive_id("https://drive.google.com/drive/folders/folder_ABC-123?usp=sharing"), "folder_ABC-123")
        self.assertEqual(google_drive.extract_drive_id("https://drive.google.com/file/d/file_ABC-123/view"), "file_ABC-123")
        self.assertEqual(google_drive.extract_drive_id("https://drive.google.com/open?id=file_ABC-123"), "file_ABC-123")

    def test_lists_only_downloadable_media(self):
        responses = [
            FakeResponse({"access_token": "access"}),
            FakeResponse({"files": [
                {"id": "video", "name": "clip.mp4", "mimeType": "video/mp4", "capabilities": {"canDownload": True}},
                {"id": "doc", "name": "rules.txt", "mimeType": "text/plain", "capabilities": {"canDownload": True}},
                {"id": "blocked", "name": "private.mp4", "mimeType": "video/mp4", "capabilities": {"canDownload": False}},
            ]}),
        ]
        with patch.dict(os.environ, {"GOOGLE_DRIVE_REFRESH_TOKEN": "refresh", "GOOGLE_OAUTH_CLIENT_ID": "client", "GOOGLE_OAUTH_CLIENT_SECRET": "secret"}), patch("core.google_drive.requests.post", side_effect=responses[:1]), patch("core.google_drive.requests.request", side_effect=responses[1:]):
            files = google_drive.GoogleDriveClient().list_media("folder")
        self.assertEqual([item["id"] for item in files], ["video"])

    def test_downloads_stream_to_file(self):
        responses = [
            FakeResponse({"access_token": "access"}),
            FakeResponse(content=b"abc", chunks=[b"a", b"bc"]),
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"GOOGLE_DRIVE_REFRESH_TOKEN": "refresh", "GOOGLE_OAUTH_CLIENT_ID": "client", "GOOGLE_OAUTH_CLIENT_SECRET": "secret"}), patch("core.google_drive.requests.post", side_effect=responses[:1]), patch("core.google_drive.requests.request", side_effect=responses[1:]):
            path = Path(tmp) / "clip.mp4"
            size = google_drive.GoogleDriveClient().download_file("file", str(path))
            self.assertEqual(size, 3)
            self.assertEqual(path.read_bytes(), b"abc")

    def test_download_file_resolves_shortcut_target(self):
        responses = [
            FakeResponse({"access_token": "access"}),
            FakeResponse({"id": "shortcut", "mimeType": "application/vnd.google-apps.shortcut", "shortcutDetails": {"targetId": "target", "targetMimeType": "video/mp4"}}),
            FakeResponse(content=b"abc", chunks=[b"abc"]),
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"GOOGLE_DRIVE_REFRESH_TOKEN": "refresh", "GOOGLE_OAUTH_CLIENT_ID": "client", "GOOGLE_OAUTH_CLIENT_SECRET": "secret"}), patch("core.google_drive.requests.post", side_effect=responses[:1]), patch("core.google_drive.requests.request", side_effect=responses[1:]):
            path = Path(tmp) / "clip.mp4"
            status, error = google_drive.download_file_oauth("https://drive.google.com/file/d/shortcut/view", str(path))
            self.assertEqual((status, error), ("downloaded", None))
            self.assertEqual(path.read_bytes(), b"abc")


if __name__ == "__main__":
    unittest.main()
