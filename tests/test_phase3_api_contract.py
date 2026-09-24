import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
API = (ROOT / "cloudflare" / "api.js").read_text(encoding="utf-8")
UI = (ROOT / "web" / "app.js").read_text(encoding="utf-8")


class Phase3ApiContractTests(unittest.TestCase):
    def test_channel_resolution_is_server_side_and_authenticated(self):
        self.assertIn("resolveBufferChannels(env)", API)
        self.assertIn('if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);', API)
        self.assertIn('channel_not_found', API)
        self.assertNotIn("body.channels || []", API)

    def test_preflight_has_no_create_post_mutation(self):
        preflight = API[API.index('parts[4] === "preflight"'):API.index('parts[3] === "buffer" && request.method === "POST"')]
        self.assertNotIn("createPost", preflight)
        self.assertIn("next_queue_slot", preflight)

    def test_mutation_requires_provider_id_and_schedule_evidence(self):
        mutation = API[API.index('parts[3] === "buffer" && request.method === "POST"'):]
        self.assertIn("!post.id || (!post.dueAt && !post.channelId)", mutation)
        self.assertIn('provider_state=\'unknown\'', mutation)
        self.assertIn('outcome === "all_succeeded"', mutation)

    def test_operation_routes_and_ui_show_partial_outcomes(self):
        self.assertIn('delivery_operations', API)
        self.assertIn('parts[3] === "operations"', API)
        self.assertIn('parts[3] === "retry"', API)
        self.assertIn('parts[3] === "reconcile"', API)
        self.assertIn('response.outcome', UI)
        self.assertIn('operation-reconcile-button', UI)
        self.assertIn('operation-retry-button', UI)


if __name__ == "__main__": unittest.main()
