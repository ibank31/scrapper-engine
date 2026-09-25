import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.fetch import FetchError, download_stream


class _FakeResponse:
    def __init__(self, chunks, status_code=200, headers=None):
        self._chunks = list(chunks)
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size=1024 * 1024):
        yield from self._chunks

    def close(self):
        self.closed = True


class FetchStreamTests(unittest.TestCase):
    def test_stream_writes_to_target_without_buffering_whole_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "asset.mp4"
            response = _FakeResponse([b"abc", b"def"])
            with patch("core.fetch._get_stream", return_value=response):
                size = download_stream("https://example.test/video.mp4", str(target), retries=1)
            self.assertEqual(size, 6)
            self.assertEqual(target.read_bytes(), b"abcdef")
            self.assertTrue(response.closed)
            self.assertFalse((Path(str(target) + ".part")).exists())

    def test_stream_rejects_declared_byte_budget_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "asset.mp4"
            response = _FakeResponse([b"abc"], headers={"Content-Length": "10"})
            with patch("core.fetch._get_stream", return_value=response):
                with self.assertRaises(FetchError):
                    download_stream("https://example.test/video.mp4", str(target), retries=1, max_bytes=5)
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".part").exists())

    def test_stream_rejects_unknown_length_after_limit_is_crossed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "asset.mp4"
            response = _FakeResponse([b"abc", b"def"])
            with patch("core.fetch._get_stream", return_value=response):
                with self.assertRaises(FetchError):
                    download_stream("https://example.test/video.mp4", str(target), retries=1, max_bytes=5)
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".part").exists())


if __name__ == "__main__":
    unittest.main()
