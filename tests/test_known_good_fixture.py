import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class KnownGoodFixtureTest(unittest.TestCase):
    def test_complete_local_trace_produces_pair_and_review_manifest(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory(prefix="known-good-test-") as folder:
            result = subprocess.run([sys.executable, "scripts/run_known_good_fixture.py", "--out", folder], cwd=root, capture_output=True, text=True, check=True)
            self.assertIn('"tier_1": 1', result.stdout)
            self.assertIn('"tier_2": 1', result.stdout)
            manifest = json.loads((Path(folder) / "review-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["fixture"], "known-good-v1")
            self.assertEqual(manifest["legal_basis"].startswith("synthetic"), True)
            self.assertEqual(manifest["selection"]["actual_selected"], {"tier_1": 1, "tier_2": 1})
            self.assertEqual([item["status"] for item in manifest["validation"]["results"]], ["pass", "pass"])
            self.assertEqual(manifest["review_manifest"]["status"], "pending_review")
            self.assertTrue(all(Path(item["artifact"]).exists() for item in manifest["review_manifest"]["items"]))


if __name__ == "__main__":
    unittest.main()
