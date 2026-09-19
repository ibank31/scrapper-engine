import os
import tempfile
import unittest

from core.job_workspace import create_workspace, sha256_file, slug


class JobWorkspaceTest(unittest.TestCase):
    def test_workspace_is_isolated_and_created(self):
        with tempfile.TemporaryDirectory() as root:
            ws = create_workspace(root, {"campaign": {"id": "demo/1", "title": "Demo"}})
            self.assertTrue(os.path.isdir(ws["assets"]))
            self.assertTrue(os.path.isdir(ws["outputs"]))
            self.assertTrue(os.path.isdir(ws["review"]))
            self.assertEqual(ws["job_id"], "demo-1")

    def test_slug_and_checksum(self):
        self.assertEqual(slug("Hello / World"), "Hello-World")
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b"clip")
            path = fh.name
        try:
            self.assertEqual(len(sha256_file(path)), 64)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
