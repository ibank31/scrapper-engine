"""Regression: preview-cleanup workflow must authenticate the way the API expects.

Root cause (2026-09-29): the scheduled `preview-cleanup` workflow sent
`x-github-token`, but `cleanupAuthorized()` in cloudflare/api.js only accepts
worker auth (`x-worker-token` / Bearer WORKER_TOKEN). Every scheduled run
therefore failed with 401 and stale previews were never cleaned.

This test pins the contract on both sides so workflow/API auth cannot drift
apart silently again.
"""

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "preview-cleanup.yml"
API_JS = REPO_ROOT / "cloudflare" / "api.js"


def _cleanup_step():
    doc = yaml.safe_load(WORKFLOW.read_text())
    steps = doc["jobs"]["cleanup"]["steps"]
    matches = [s for s in steps if "cleanup-previews" in str(s.get("run", ""))]
    assert matches, "cleanup-previews curl step not found in preview-cleanup.yml"
    return matches[0]


class PreviewCleanupAuthContractTests(unittest.TestCase):
    def test_workflow_sends_worker_token(self):
        step = _cleanup_step()
        run_script = step["run"]
        self.assertIn("x-worker-token", run_script)
        self.assertIn("secrets.CLIPPER_WORKER_TOKEN", str(step.get("env", {})))

    def test_workflow_does_not_send_github_token(self):
        step = _cleanup_step()
        run_script = step["run"]
        self.assertNotIn("x-github-token", run_script)

    def test_api_cleanup_gate_requires_worker_auth(self):
        src = API_JS.read_text()
        match = re.search(
            r"async function cleanupAuthorized\(request, env\) \{([^}]*)\}",
            src,
        )
        self.assertIsNotNone(match, "cleanupAuthorized not found in api.js")
        self.assertIn("workerAuthorized", match.group(1))


if __name__ == "__main__":
    unittest.main()
